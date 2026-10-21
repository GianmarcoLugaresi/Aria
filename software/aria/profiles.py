"""Versioni di Aria (Leggera / Media / Pesante) e scelta del chatbot, dalle Impostazioni dell'app.

Le scelte stanno in `settings.json`, accanto a config.yaml:  {"profile": "media", "llm_model": null}
  profile    = leggera | media | pesante | personalizzata; "media" non cambia nulla: e' la configurazione di config.yaml cosi' com'e'
  stt_model  = (solo "personalizzata") modello di riconoscimento vocale MLX Whisper, repo Hugging Face
  llm_model  = chatbot (Ollama) scelto a mano al posto di quello della versione; null = quello della versione
`config.load()` applica le impostazioni sopra config.yaml (vedi apply_settings): il file di configurazione dell'utente non viene mai riscritto.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import re

SETTINGS_FILE = "settings.json"
DEFAULT_PROFILE = "media"

CUSTOM = "personalizzata"

# Modelli di riconoscimento vocale scelti dalle Impostazioni (formato MLX Whisper, repo Hugging Face), dal piu' piccolo al piu' grande.
#   wer = errore sulle parole in % [audio pulito, rumoroso, volume basso]; sec = secondi per frase: MISURATI qui su 54 frasi italiane
#   (stessa registrazione per tutti, voci sintetiche: indicativo). None = non misurato su questo Mac.
APPLE_STT = "apple:speech"                                  # il riconoscimento integrato nel Mac (nessun download: lo da' il sistema)
STT_CATALOG: list[dict] = [
    {"repo": APPLE_STT, "label": "Apple (integrato nel Mac)", "mb": 0, "wer": None, "sec": 0.1,
     "note": "Quello del Mac: non scarica nulla e non pesa sulla RAM di Aria, 0,1 s a frase. Sulle tue registrazioni vere va quasi alla pari di Whisper large-v3 (sbaglia frasi diverse)."},
    {"repo": "mlx-community/whisper-tiny-mlx", "label": "Whisper tiny", "mb": 74, "wer": None, "sec": None,
     "note": "Il piu' piccolo: solo per prova, di solito sbaglia moltissimo."},
    {"repo": "mlx-community/whisper-base-mlx", "label": "Whisper base", "mb": 144, "wer": [18, 50, 48], "sec": 0.1,
     "note": "Velocissimo ma con rumore sbaglia circa meta' delle parole."},
    {"repo": "mlx-community/whisper-small-mlx-q4", "label": "Whisper small (4 bit)", "mb": 197, "wer": [10, 31, 27], "sec": 0.2,
     "note": "Quello della versione Leggera."},
    {"repo": "mlx-community/whisper-large-v3-turbo-q4", "label": "Whisper large-v3-turbo (4 bit)", "mb": 464, "wer": [6, 9, 7], "sec": 0.55,
     "note": "Quello della versione Media: il miglior rapporto tra precisione e peso tra quelli misurati."},
    {"repo": "mlx-community/whisper-small-mlx", "label": "Whisper small", "mb": 481, "wer": None, "sec": None,
     "note": "Come small a 4 bit, senza compressione: un po' piu' preciso, piu' pesante."},
    {"repo": "mlx-community/whisper-medium-mlx", "label": "Whisper medium", "mb": 1525, "wer": None, "sec": None,
     "note": "Via di mezzo, ma piu' pesante e lento del turbo senza esserne migliore: non conviene."},
    {"repo": "mlx-community/whisper-large-v3-turbo", "label": "Whisper large-v3-turbo", "mb": 1614, "wer": None, "sec": None,
     "note": "Il turbo senza compressione a 4 bit: in teoria un filo piu' preciso, 3 volte piu' pesante."},
    {"repo": "mlx-community/whisper-large-v3-mlx", "label": "Whisper large-v3", "mb": 3084, "wer": [4, 9, 7], "sec": 0.8,
     "note": "Quello della versione Pesante. Misurato: NON e' piu' preciso del turbo a 4 bit (nella stessa prova 1 / 2 / 8 %) ed e' piu' lento e 6 volte piu' pesante."},
]
STT_NAMES = {c["repo"]: c["label"] for c in STT_CATALOG}
STT_MB = {c["repo"]: c["mb"] for c in STT_CATALOG}                         # dimensioni dei pesi, misurate dal registro Hugging Face (ottobre 2026)

# Chatbot. Un "riferimento" (ref) dice dove vive il modello:  "mlx:<repo Hugging Face>" = DENTRO Aria (Apple MLX, nessun Ollama);
# un nome senza prefisso ("gemma3:4b") = un modello di Ollama, se l'utente lo ha. Tutti a 4 bit, solo testo.
LLM_CATALOG: list[dict] = [
    {"ref": "mlx:mlx-community/gemma-3-1b-it-4bit", "label": "Gemma 3 1B", "gb": 0.77,
     "note": "Minuscolo e velocissimo, ma un modello cosi' piccolo scrive un italiano povero e perde il filo: solo per prova."},
    {"ref": "mlx:mlx-community/gemma-3-text-4b-it-4bit", "label": "Gemma 3 4B", "gb": 2.6,
     "note": "Quello di Aria (versioni Leggera e Media): il piu' piccolo con un italiano buono."},
    {"ref": "mlx:mlx-community/gemma-4-e4b-it-4bit", "label": "Gemma 4 E4B", "gb": 4.7,
     "note": "Provato a fondo: piu' veloce (50 parole al secondo contro 30), piu' leggero di Gemma 2 9B e capisce meglio i comandi; conversa un po' meglio. Scarica 5,2 GB."},
    {"ref": "mlx:mlx-community/gemma-2-9b-it-4bit", "label": "Gemma 2 9B", "gb": 5.2,
     "note": "Quello della versione Pesante: scrive meglio, ma e' piu' lento e occupa il doppio."},
    {"ref": "mlx:mlx-community/gemma-3-text-12b-it-4bit", "label": "Gemma 3 12B", "gb": 7.2,
     "note": "Molto pesante: con 16 GB di RAM chiudi tutto il resto."},
]
LLM_NAMES = {c["ref"]: c["label"] for c in LLM_CATALOG}
LLM_GB = {c["ref"]: c["gb"] for c in LLM_CATALOG}
DEFAULT_LLM = "mlx:mlx-community/gemma-3-text-4b-it-4bit"
OLLAMA_URL = "http://127.0.0.1:11434/v1"


def is_mlx_ref(ref: str | None) -> bool:
    return bool(ref) and ref.startswith("mlx:")


def llm_label(ref: str) -> str:
    return LLM_NAMES.get(ref) or (ref[4:] if is_mlx_ref(ref) else ref)


def llm_ref_from_text(text: str) -> str:
    """Quello che l'utente scrive in "Altro chatbot": con i due punti e' un nome di Ollama (llama3.1:8b), con una barra un repo MLX (org/nome)."""
    t = (text or "").strip()
    if t.startswith("mlx:") or ":" in t or "/" not in t:
        return t
    return "mlx:" + t


_REPO_RE = re.compile(r"^(?:[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*|apple:speech)$")
_OLLAMA_RE = re.compile(r"^[A-Za-z0-9][\w.-]*(/[A-Za-z0-9][\w.-]*)?(:[\w.-]+)?$")


def valid_repo(name: str) -> bool:
    return bool(_REPO_RE.match(name or ""))


def valid_ollama_name(name: str) -> bool:
    return bool(_OLLAMA_RE.match(name or ""))


def estimate_ram_gb(stt_mb: float | None, llm_gb: float) -> float:
    """Stima prudente della memoria in uso: 1,65 GB fissi (librerie e voce) + pesi del riconoscimento + pesi del chatbot + 0,3 GB di cache e conversazione.
    Taratura: con Whisper turbo 4 bit + Gemma 3 4B MLX da' 5,0 GB; la misura vera del backend (footprint) e' 4,3 GB, piu' 0,1 dell'app."""
    return round(1.65 + (500 if stt_mb is None else stt_mb) / 1000 + llm_gb + 0.3, 1)


# "stt"/"llm" = None -> si usa quello di config.yaml (la versione Media e' la configurazione attuale, qualunque sia)
PROFILES: dict[str, dict] = {
    "leggera": {
        "label": "Leggera",
        "summary": "Riconoscimento vocale piu' leggero e 3 volte piu' veloce, ma meno preciso: sbaglia piu' parole, soprattutto con rumore o volume basso.",
        "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-small-mlx-q4", "prompt": False},
        "llm": DEFAULT_LLM, "llm_gb": 2.6, "ram_gb": 4.1, "measured": False,
    },
    "media": {
        "label": "Media",
        "summary": "La configurazione attuale di Aria: buon equilibrio tra precisione, velocita' e memoria.",
        "stt": None, "llm": None, "llm_gb": 2.6, "ram_gb": 4.4, "measured": True,
    },
    "pesante": {
        "label": "Pesante",
        "summary": "Un chatbot piu' grande, che scrive meglio, e Whisper large-v3 (precisione pari al turbo della Media, ma piu' lento). Usa circa 10 GB di memoria: chiudi le altre app.",
        "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-large-v3-mlx", "prompt": False},
        "llm": "mlx:mlx-community/gemma-2-9b-it-4bit", "llm_gb": 5.2, "ram_gb": 10.0, "measured": True,
    },
}

# modelli che "ragionano" prima di rispondere (secondi di attesa): con Ollama si spegne con reasoning_effort=none
_REASONING = re.compile(r"(gemma[-_ ]?4|qwen[-_ ]?3|qwq|deepseek[-_ ]?r1|gpt[-_ ]?oss|magistral)", re.I)


# modelli che VEDONO le immagini (quindi leggono lo schermo da soli): la famiglia Gemma 4 e i modelli «visione» piu' noti; gli altri (Gemma 2, Gemma 3 «text»…) no
_VISION = re.compile(r"(gemma[-_ ]?4|gemma[-_ ]?3n|paligemma|qwen[-_ ]?2(?:\.5)?[-_ ]?vl|qwen[-_ ]?3[-_ ]?vl|llava|pixtral|smolvlm|idefics|moondream|minicpm[-_ ]?v|llama[-_ ]?3\.2[-_ ]?\d+b[-_ ]?vision|mistral[-_ ]?small[-_ ]?3)", re.I)


def has_vision(ref: str | None) -> bool:
    """True se il chatbot capisce anche le immagini. «gemma-3-text-…» e' la variante SOLO testo di Gemma 3."""
    r = (ref or "")
    if re.search(r"-text-|gemma-2|gemma-3-1b", r, re.I):
        return False
    return bool(_VISION.search(r))


def vision_tag(ref: str | None) -> str:
    """Per l'elenco dei chatbot nelle Impostazioni: quali leggono anche le immagini (solo quelli «dentro Aria»: la visione gira con MLX)."""
    if not (is_mlx_ref(ref) and has_vision(ref)):
        return ""
    from . import i18n, ui_en
    return ui_en.VISION_TAG if i18n.is_en() else " · vede le immagini"


# ---- i testi mostrati nelle Impostazioni, nella lingua in uso (l'inglese sta in ui_en.py; chi manca ricade sull'italiano)
def stt_note(c: dict) -> str:
    from . import i18n, ui_en
    return ui_en.STT_NOTES.get(c["repo"], c["note"]) if i18n.is_en() else c["note"]


def stt_display_label(repo: str) -> str:
    from . import i18n, ui_en
    return (ui_en.STT_LABELS.get(repo) if i18n.is_en() else None) or STT_NAMES.get(repo, repo)


def llm_note(c: dict) -> str:
    from . import i18n, ui_en
    return ui_en.LLM_NOTES.get(c["ref"], c["note"]) if i18n.is_en() else c["note"]


def profile_text(pid: str) -> tuple[str, str]:
    """(nome, descrizione) di una versione nella lingua in uso."""
    from . import i18n, ui_en
    if i18n.is_en() and pid in ui_en.PROFILES:
        return ui_en.PROFILES[pid]
    return PROFILES[pid]["label"], PROFILES[pid]["summary"]


def power_text(pid: str) -> tuple[str, str]:
    """(nome, cosa fa) di una funzione nella lingua in uso."""
    from . import i18n, ui_en
    if i18n.is_en() and pid in ui_en.POWERS:
        return ui_en.POWERS[pid]
    return POWERS[pid]


def needs_no_think(model: str) -> bool:
    return bool(_REASONING.search(model or ""))


def is_embedding_model(name: str, family: str = "") -> bool:
    n = (name or "").lower()
    return "embed" in n or "rerank" in n or (family or "").lower() in {"bert", "nomic-bert"}


def settings_path(config_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), SETTINGS_FILE)


def load_settings(config_path: str | None) -> dict:
    if not config_path:
        return {}
    try:
        with open(settings_path(config_path), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


PRESERVED_KEYS = ("workspace", "powers", "wake_phrase", "language")           # chiavi che non riguardano versione/modelli: non si perdono quando si salva una scelta di modelli


def save_settings(config_path: str, settings: dict) -> None:
    for k in PRESERVED_KEYS:
        if k not in settings and k in load_settings(config_path):
            settings = {**settings, k: load_settings(config_path)[k]}
    p = settings_path(config_path)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


# I "poteri" di Aria: ognuno si accende e si spegne dalle Impostazioni (tutti accesi di default). id -> (nome, cosa fa)
POWERS: dict[str, tuple[str, str]] = {
    "shortcuts": ("Scorciatoie di macOS", "Esegue le tue Scorciatoie a voce, chiedendo sempre conferma prima."),
    "reminders": ("Promemoria", "Crea promemoria nell'app Promemoria e te li legge."),
    "calendar": ("Calendario", "Aggiunge eventi in Calendario e ti dice cosa hai in agenda."),
    "music": ("Musica e volume", "Controlla Musica (o Spotify) e il volume del Mac."),
    "apps": ("App e siti", "Apre le app installate, i siti e le ricerche (YouTube, Google, Mappe…)."),
    "documents": ("Documenti", "Legge e risponde a domande sui PDF e i documenti Word della cartella di Aria."),
    "briefing": ("Briefing del mattino", "Meteo, impegni, promemoria e notizie in un colpo solo."),
    "screen_mac": ("Guardare lo schermo: OCR del Mac",
                   "Legge i testi che hai sullo schermo e ti dice dove sono («dov'è il pulsante Esporta?», «riassumi questa pagina»). Usa il riconoscimento testo di macOS: "
                   "0,3 secondi, nessuna memoria in più, va con qualunque chatbot. Non capisce immagini e icone senza scritta. Spento se accendi l'altra."),
    "screen_model": ("Guardare lo schermo: un modello che vede",
                     "Un modello con la visione integrata guarda lo schermo: capisce anche icone, immagini e come è fatta la pagina, e può darti un parere. Ci mette qualche secondo e usa "
                     "circa 4 GB di memoria in più mentre risponde. Spento se accendi l'altra."),
}
POWERS["screen_point"] = ("Indicare le cose sullo schermo",
                          "Quando ti dice dove sta un pulsante o una scritta (con l'OCR del Mac), lo evidenzia con un riquadro luminoso che pulsa per qualche secondo. Non blocca i clic: continui a lavorare.")
POWERS["screen_ax"] = ("Trovare pulsanti e icone con precisione (Accessibilità)",
                       "Per «dov'è il pulsante X?» usa l'Accessibilità di macOS: legge i pulsanti, le icone senza scritta e i menu dell'app che hai davanti e dice dov'è con la posizione esatta, anche senza guardare lo schermo. "
                       "Serve il permesso «Accessibilità» per Aria (macOS lo chiede).")
POWERS["voice_natural"] = ("Voce più naturale (Qwen3-TTS)",
                           "Una voce più umana e fedele: non taglia né mangia le parole (nelle prove 13 frasi su 18 perfette contro 10 della voce di prima) e va a frasi intere, senza pause a pezzetti. "
                           "Usa circa 1,8 GB di memoria in più mentre è accesa; la prima volta scarica da sola il modello (~0,9 GB) e nel frattempo parla la voce di prima. "
                           "Ogni voce dell'elenco ha la sua versione naturale (scegli dall'elenco, come sempre), e in più «Aria», «Chiara», «Elena» e «Marco» (uomo): dì «cambia voce» per sentirle.")
POWERS["battery_rest"] = ("Riposo a batteria",
                          "Quando il Mac va a batteria e lo schermo è spento da un minuto, Aria smette di ascoltare e il Mac può andare in stop: col microfono aperto non ci andrebbe mai da solo. "
                          "Riprende appena riaccendi lo schermo, attacchi l'alimentatore o premi ⌥ Spazio. Spento = ascolta sempre (consuma molta più batteria).")
# acceso solo se lo decidi tu (gli altri poteri sono accesi di default): guardare lo schermo chiede un permesso di macOS
POWERS_OFF_BY_DEFAULT = {"screen_mac", "screen_model", "voice_natural"}                    # (screen_point e' acceso: serve solo quando lo schermo e' gia' acceso)
POWER_EXCLUSIVE = {"screen_mac": "screen_model", "screen_model": "screen_mac"}          # una sola lettura dello schermo alla volta


def get_powers(config_path: str | None) -> dict[str, bool]:
    saved = load_settings(config_path).get("powers")
    saved = saved if isinstance(saved, dict) else {}
    return {k: bool(saved.get(k, k not in POWERS_OFF_BY_DEFAULT)) for k in POWERS}


def set_power(config_path: str, name: str, enabled: bool) -> None:
    if name not in POWERS:
        raise KeyError(name)
    cur = load_settings(config_path)
    powers = cur.get("powers") if isinstance(cur.get("powers"), dict) else {}
    powers[name] = bool(enabled)
    if enabled and name in POWER_EXCLUSIVE:                          # accendere un modo di leggere lo schermo spegne l'altro
        powers[POWER_EXCLUSIVE[name]] = False
    cur["powers"] = powers
    p = settings_path(config_path)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def get_workspace(config_path: str | None) -> str | None:
    return load_settings(config_path).get("workspace") or None


def set_workspace(config_path: str, path: str | None) -> None:
    """Salva (o toglie, con None) la cartella di Aria, lasciando intatto il resto delle impostazioni."""
    cur = load_settings(config_path)
    if path:
        cur["workspace"] = path
    else:
        cur.pop("workspace", None)
    p = settings_path(config_path)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def get_language(config_path: str | None) -> str | None:
    """La lingua scelta nelle Impostazioni («it» o «en»), oppure None se non e' stata scelta."""
    from . import i18n
    return i18n.clean(load_settings(config_path).get("language"))


def set_language(config_path: str, code: str | None) -> None:
    """Salva (o toglie, con None: si torna a config.yaml e alla lingua del sistema) la lingua, lasciando intatto il resto delle impostazioni."""
    from . import i18n
    cur = load_settings(config_path)
    c = i18n.clean(code)
    if c:
        cur["language"] = c
    else:
        cur.pop("language", None)
    p = settings_path(config_path)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


_WAKE_RE = re.compile(r"^[a-zàèéìòù']{2,12}(?: [a-zàèéìòù']{2,12}){1,2}$")


def clean_wake_phrase(text: str | None) -> str | None:
    """«Hey Aria», «Ciao Aria», «Ehi Aria»… -> in minuscolo; None se non va bene (servono 2-3 parole: una sola parola scatterebbe a ogni frase che la contiene)."""
    t = re.sub(r"[,.;:!?«»\"“”]", " ", (text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t if _WAKE_RE.match(t) else None


def get_wake_phrase(config_path: str | None) -> str | None:
    return clean_wake_phrase(load_settings(config_path).get("wake_phrase"))


def set_wake_phrase(config_path: str, phrase: str | None) -> None:
    """Salva (o toglie, con None: torna quella di config.yaml) la frase con cui si chiama Aria."""
    cur = load_settings(config_path)
    if phrase:
        cur["wake_phrase"] = phrase
    else:
        cur.pop("wake_phrase", None)
    p = settings_path(config_path)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def stt_repo(stt_cfg: dict) -> str:
    """Repo Hugging Face dei pesi di un riconoscimento vocale (mlx-whisper: il modello; faster-whisper: Systran/faster-whisper-<nome>)."""
    m = (stt_cfg or {}).get("model", "")
    if (stt_cfg or {}).get("kind") == "apple":
        return APPLE_STT
    if (stt_cfg or {}).get("kind") == "faster-whisper" and "/" not in m:
        return f"Systran/faster-whisper-{m}"
    return m


def resolve(profile_id: str, base_cfg: dict) -> dict:
    """Quali pezzi usa una versione: {'stt': {...}, 'llm': 'nome'}; i pezzi None della versione vengono da config.yaml."""
    prof = PROFILES[profile_id]
    brain = (base_cfg.get("brains") or [{}])[0]
    cfg_llm = brain.get("llm") or {}
    cfg_ref = ("mlx:" + cfg_llm.get("model", "")) if cfg_llm.get("kind") == "mlx-lm" else cfg_llm.get("model", "")
    return {"stt": copy.deepcopy(prof["stt"] or brain.get("stt") or {}), "llm": prof["llm"] or cfg_ref}


def apply_llm(brain: dict, ref: str) -> None:
    """Imposta il chatbot di un "cervello" dal riferimento: mlx:<repo> = dentro Aria, altrimenti Ollama. Mantiene temperatura e lunghezza."""
    old = brain.get("llm") or {}
    keep = {k: old[k] for k in ("temperature", "max_tokens", "top_p", "min_p", "repetition_penalty") if k in old}
    if is_mlx_ref(ref):
        new = {"kind": "mlx-lm", "model": ref[4:], **keep}
        if needs_no_think(ref):
            new["chat_template_kwargs"] = {"enable_thinking": False}
        brain["llm"] = new
        return
    if old.get("kind") == "mlx-lm" or not old.get("base_url"):          # si arriva da un chatbot interno: serve l'indirizzo di Ollama
        new = {"base_url": OLLAMA_URL, "model": ref, **keep}
    else:
        new = {k: v for k, v in old.items() if k != "kind"}
        new["model"] = ref
    extra = dict(new.get("extra_body") or {})
    if needs_no_think(ref):                                              # i modelli che "ragionano" si zittiscono, gli altri non ricevono il parametro
        extra["reasoning_effort"] = "none"
    else:
        extra.pop("reasoning_effort", None)
    new["extra_body"] = extra
    brain["llm"] = new


def apply_settings(cfg: dict, settings: dict | None) -> dict:
    """Sovrappone le scelte dell'utente al primo "cervello" (quello dell'app). Senza settings, o con la versione Media, non cambia nulla."""
    s = settings or {}
    pid = s.get("profile") or DEFAULT_PROFILE
    wake = clean_wake_phrase(s.get("wake_phrase"))
    if wake and isinstance(cfg.get("wake"), dict):
        cfg["wake"]["phrase"] = wake                                           # la frase scelta nelle Impostazioni vale piu' di quella di config.yaml
    if not cfg.get("brains"):
        return cfg
    brain = cfg["brains"][0]
    tts = brain.get("tts")
    if isinstance(tts, dict) and tts.get("kind") == "pocket" and sys.platform == "darwin":  # la voce puo' diventare «naturale» (Qwen3-TTS, serve MLX: solo Mac con chip Apple) dalle Impostazioni, a caldo: Pocket resta il ripiego
        brain["tts"] = {**tts, "kind": "natural"}
    if pid == CUSTOM:                                       # scelti a mano: riconoscimento vocale e chatbot (quelli mancanti restano di config.yaml)
        if s.get("stt_model") == APPLE_STT:
            from .stt import apple_helper_path
            if os.path.exists(apple_helper_path()):                                  # senza il programma di supporto resta il riconoscimento di prima
                brain["stt"] = {"kind": "apple"}
        elif s.get("stt_model"):
            brain["stt"] = {"kind": "mlx-whisper", "model": s["stt_model"], "prompt": False}
        if s.get("llm_model"):
            apply_llm(brain, s["llm_model"])
        cfg["profile"] = CUSTOM
        return cfg
    if pid not in PROFILES:
        return cfg
    prof = PROFILES[pid]
    if prof["stt"]:
        brain["stt"] = copy.deepcopy(prof["stt"])
    llm = s.get("llm_model") or prof["llm"]
    if llm:
        apply_llm(brain, llm)
    cfg["profile"] = pid
    return cfg
