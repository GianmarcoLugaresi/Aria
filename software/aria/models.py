"""Gestione dei modelli dalle Impostazioni dell'app: cosa e' installato, scaricare una versione, applicare la scelta.

    python -m aria.models status   --config config.yaml [--extra-stt REPO] [--extra-llm RIF]
    python -m aria.models download --config config.yaml leggera|media|pesante|personalizzata [--stt REPO] [--llm NOME]   -> righe JSON di avanzamento
    python -m aria.models apply    --config config.yaml leggera|media|pesante|personalizzata [--stt REPO] [--llm NOME]   -> scrive settings.json (se i pezzi ci sono)
    python -m aria.models remove   --config config.yaml stt|llm IDENTIFICATIVO                     -> toglie un modello dal Mac (mai quello in uso, mai l'ultimo)
    python -m aria.models workspace --config config.yaml status|set PERCORSO|clear                 -> la cartella dove Aria puo' scrivere e leggere file
    python -m aria.models power    --config config.yaml status|NOME on|off                         -> accende/spegne un potere di Aria (promemoria, musica...)

--stt = modello di riconoscimento vocale (MLX Whisper, repo Hugging Face); --llm = chatbot: "mlx:org/nome" = dentro Aria (nessun Ollama),
un nome senza prefisso ("gemma3:4b") = un modello di Ollama.
Se --stt e' diverso da quello della versione scelta, la scelta diventa "personalizzata".
Parte leggera di proposito (niente torch/mlx): l'app la lancia ogni volta che apre le Impostazioni.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")        # con la rete lenta il trasferimento "xet" a volte si blocca

from . import config as cfgmod                           # noqa: E402
from . import profiles as P                              # noqa: E402
from . import workspace as W                             # noqa: E402

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
OLLAMA_REGISTRY = "https://registry.ollama.ai"
MARGIN_GB = 1.5                                          # spazio libero da lasciare dopo il download
MLX_WEIGHTS = ("weights.npz", "weights.safetensors", "model.safetensors")


def emit(**kw) -> None:
    print(json.dumps(kw, ensure_ascii=False), flush=True)


# ------------------------------------------------------------------------------------ cosa c'e' installato
def installed_llms(client=None) -> list[dict] | None:
    """Chatbot presenti in Ollama [{name, gb, params, heavy, reasoning}], ordinati per nome; None se Ollama non risponde."""
    import httpx
    try:
        r = (client or httpx).get(OLLAMA + "/api/tags", timeout=4.0)
        r.raise_for_status()
        models = r.json().get("models", [])
    except Exception:                                    # noqa: BLE001
        return None
    out = []
    for m in models:
        name = m.get("name") or m.get("model") or ""
        det = m.get("details") or {}
        if not name or P.is_embedding_model(name, det.get("family", "")):
            continue
        gb = (m.get("size") or 0) / 1e9
        out.append({"name": name, "gb": round(gb, 1), "params": det.get("parameter_size"), "heavy": gb >= 8.0,
                    "reasoning": P.needs_no_think(name)})
    return sorted(out, key=lambda x: x["name"].lower())


def _snapshot_dir(repo: str) -> str | None:
    try:
        from huggingface_hub import snapshot_download
        return snapshot_download(repo, local_files_only=True)
    except Exception:                                    # noqa: BLE001
        return None


def mlx_whisper_problem(repo: str) -> str | None:
    """None se il repo scaricato e' un MLX Whisper utilizzabile, altrimenti il motivo (in italiano)."""
    d = _snapshot_dir(repo)
    if not d:
        return "non e' scaricato"
    cfg = os.path.join(d, "config.json")
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        return "manca config.json: non e' un modello MLX Whisper"
    if not isinstance(c, dict) or "n_audio_state" not in c:
        return "non e' nel formato MLX Whisper (cerca un modello 'mlx-community/whisper-…')"
    if not any(os.path.exists(os.path.join(d, w)) for w in MLX_WEIGHTS):
        return "mancano i pesi del modello"
    return None


def stt_installed(stt_cfg: dict) -> bool:
    """True se i pesi del riconoscimento vocale sono gia' nella cache di Hugging Face e utilizzabili (nessun accesso alla rete)."""
    repo = P.stt_repo(stt_cfg)
    if not repo:
        return False
    if (stt_cfg or {}).get("kind") == "apple":
        from .stt import apple_helper_path
        return os.path.exists(apple_helper_path(stt_cfg))                  # niente da scaricare: basta il programma di supporto
    d = _snapshot_dir(repo)
    if not d:
        return False
    if (stt_cfg or {}).get("kind") == "mlx-whisper":
        return mlx_whisper_problem(repo) is None
    for root, _dirs, files in os.walk(d):
        for f in files:
            try:
                if os.path.getsize(os.path.join(root, f)) > 1_000_000:     # un file grosso = i pesi (non solo config.json)
                    return True
            except OSError:
                pass
    return False


def mlx_lm_installed(repo: str) -> bool:
    """True se i pesi di un chatbot MLX (tutti i pezzi) sono nella cache di Hugging Face."""
    d = _snapshot_dir(repo)
    if not d or not os.path.exists(os.path.join(d, "config.json")):
        return False
    idx = os.path.join(d, "model.safetensors.index.json")
    try:
        if os.path.exists(idx):
            with open(idx, "r", encoding="utf-8") as f:
                files = set(json.load(f)["weight_map"].values())
            return bool(files) and all(os.path.exists(os.path.join(d, w)) for w in files)
        single = os.path.join(d, "model.safetensors")
        return os.path.exists(single) and os.path.getsize(single) > 1_000_000
    except (OSError, ValueError, KeyError):
        return False


def mlx_lm_problem(repo: str) -> str | None:
    """None se il repo scaricato e' un chatbot MLX che Aria sa usare, altrimenti il motivo (in italiano)."""
    d = _snapshot_dir(repo)
    if not d:
        return "non e' scaricato"
    try:
        with open(os.path.join(d, "config.json"), "r", encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        return "manca config.json: non e' un modello di linguaggio MLX"
    mt = (c.get("model_type") if isinstance(c, dict) else None) or ((c.get("text_config") or {}).get("model_type") if isinstance(c, dict) else None)
    if not mt:
        return "non e' un modello di linguaggio MLX"
    if not mlx_lm_installed(repo):
        return "il download e' incompleto"
    try:
        import importlib.util
        from mlx_lm import utils as U                    # type: ignore
        mt = getattr(U, "MODEL_REMAPPING", {}).get(mt, mt)
        if importlib.util.find_spec(f"mlx_lm.models.{mt}") is None:
            return f"il tipo di modello '{mt}' non e' supportato da Aria"
    except ImportError:
        pass                                             # mlx_lm non c'e': non si puo' controllare
    return None


def llm_ready(ref: str, ollama: list[dict] | None) -> bool:
    """Il chatbot c'e' ed e' usabile: MLX = pesi in cache; Ollama = presente nell'elenco (che richiede Ollama acceso)."""
    return mlx_lm_installed(ref[4:]) if P.is_mlx_ref(ref) else _llm_known(ref, ollama)


def disk_free_gb(path: str | None = None) -> float:
    return shutil.disk_usage(path or os.path.expanduser("~")).free / 1e9


def ram_total_gb() -> float | None:
    try:
        return round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2 ** 30, 1)
    except (ValueError, OSError, AttributeError):
        return None


def _llm_known(name: str, llms: list[dict] | None) -> bool:
    if not llms:
        return False
    return any(m["name"] == name or m["name"] == name + ":latest" or (":" not in name and m["name"].startswith(name + ":")) for m in llms)


def _mlx(repo: str) -> dict:
    if repo == P.APPLE_STT:
        return {"kind": "apple"}
    return {"kind": "mlx-whisper", "model": repo, "prompt": False}


def _target(base: dict, profile: str, stt: str | None = None, llm: str | None = None) -> dict:
    """Cosa serve davvero per una scelta: {'profile', 'stt': {cfg}, 'llm': nome, 'preset_llm'}. Un riconoscimento diverso dalla versione = personalizzata."""
    if profile == P.CUSTOM:
        media = P.resolve("media", base)
        return {"profile": P.CUSTOM, "stt": _mlx(stt) if stt else media["stt"], "llm": llm or media["llm"], "preset_llm": None}
    r = P.resolve(profile, base)
    if stt and stt != P.stt_repo(r["stt"]):
        return _target(base, P.CUSTOM, stt, llm or r["llm"])
    return {"profile": profile, "stt": r["stt"], "llm": llm or r["llm"], "preset_llm": r["llm"]}


def _remove_flags(entries: list[dict], key: str, active: str) -> None:
    """Segna ogni modello installato come rimovibile o no: non quello in uso, non l'ultimo rimasto."""
    n_inst = sum(1 for m in entries if m["installed"] and m[key] != P.APPLE_STT)
    for m in entries:
        m["block"] = None
        if not m["installed"]:
            continue
        if m[key] == P.APPLE_STT and m[key] != active:                    # il riconoscimento del Mac e' del sistema: non si toglie, e non conta come «un modello scaricato»
            m["block"], m["removable"] = "integrato nel Mac", False
            continue
        if m[key] == active:
            m["block"] = "in uso"
        elif n_inst <= 1:
            m["block"] = "ultimo installato"
        m["removable"] = m["block"] is None


def status(config_path: str, llms="auto", extra_stt: str | None = None, extra_llm: str | None = None) -> dict:
    base = cfgmod.load(config_path, settings=False)
    settings = P.load_settings(config_path)
    llms = installed_llms() if llms == "auto" else llms
    profs = []
    for pid, prof in P.PROFILES.items():
        r = P.resolve(pid, base)
        repo = P.stt_repo(r["stt"])
        s_inst, l_inst = stt_installed(r["stt"]), llm_ready(r["llm"], llms)
        s_mb = P.STT_MB.get(repo)
        if P.is_mlx_ref(r["llm"]):
            l_gb = P.LLM_GB.get(r["llm"], prof["llm_gb"])
        else:
            l_gb = next((m["gb"] for m in (llms or []) if m["name"] == r["llm"]), prof["llm_gb"])
        need = (0 if s_inst else (s_mb or 0)) + (0 if l_inst else l_gb * 1000)
        profs.append({
            "id": pid, "label": prof["label"], "summary": prof["summary"], "ram_gb": prof["ram_gb"], "measured": prof["measured"],
            "stt": {"name": repo, "label": P.STT_NAMES.get(repo, repo), "mb": s_mb, "installed": s_inst},
            "llm": {"name": r["llm"], "label": P.llm_label(r["llm"]), "mb": round(l_gb * 1000), "installed": l_inst},
            "need_mb": round(need),
        })
    pid = settings.get("profile")
    active = pid if pid in P.PROFILES or pid == P.CUSTOM else P.DEFAULT_PROFILE
    t = _target(base, active, settings.get("stt_model") if active == P.CUSTOM else None,
                settings.get("llm_model") if active == P.CUSTOM else (settings.get("llm_model") or None))
    active_stt = P.stt_repo(t["stt"])

    stt_models, seen = [], set()
    for c in P.STT_CATALOG:
        seen.add(c["repo"])
        stt_models.append({**c, "installed": stt_installed(_mlx(c["repo"])), "custom": False})
    for repo in [x for x in (extra_stt, settings.get("stt_model"), active_stt) if x]:   # quelli scelti a mano e non in elenco
        if repo not in seen:
            seen.add(repo)
            cfg_ = t["stt"] if repo == active_stt else _mlx(repo)
            stt_models.append({"repo": repo, "label": repo, "mb": None, "wer": None, "sec": None, "note": "Modello scelto da te.",
                               "installed": stt_installed(cfg_), "custom": True})
    _remove_flags(stt_models, "repo", active_stt)

    llm_models, seen = [], set()
    for c in P.LLM_CATALOG:
        seen.add(c["ref"])
        llm_models.append({"ref": c["ref"], "source": "mlx", "label": c["label"] + P.vision_tag(c["ref"]), "gb": c["gb"], "note": c["note"], "heavy": c["gb"] >= 7.0,
                           "reasoning": False, "installed": mlx_lm_installed(c["ref"][4:]), "custom": False})
    for m in (llms or []):
        seen.add(m["name"])
        llm_models.append({"ref": m["name"], "source": "ollama", "label": m["name"], "gb": m["gb"], "note": "Installato con Ollama.",
                           "heavy": m["heavy"], "reasoning": m["reasoning"], "installed": True, "custom": False})
    for ref in [x for x in (extra_llm, settings.get("llm_model"), t["llm"]) if x]:
        if ref not in seen:
            seen.add(ref)
            llm_models.append({"ref": ref, "source": "mlx" if P.is_mlx_ref(ref) else "ollama", "label": P.llm_label(ref) + P.vision_tag(ref), "gb": None,
                               "note": "Modello scelto da te.", "heavy": False, "reasoning": P.needs_no_think(ref),
                               "installed": llm_ready(ref, llms), "custom": True})
    _remove_flags(llm_models, "ref", t["llm"])
    return {
        "profiles": profs, "stt_models": stt_models, "llm_models": llm_models, "installed_llms": llms or [],
        "ollama": llms is not None, "ollama_installed": _ollama_present(),
        "active_profile": active, "active_stt": active_stt, "active_llm": t["llm"],
        "disk_free_gb": round(disk_free_gb(), 1), "ram_total_gb": ram_total_gb(),
        "workspace": workspace_status(config_path),
        "powers": powers_status(config_path),
        "wake_phrase": _wake_status(config_path),
    }


def _wake_status(config_path: str) -> str:
    try:
        from . import config as C
        return C.load(config_path).get("wake", {}).get("phrase", "hey aria")
    except Exception:                                    # noqa: BLE001
        return P.get_wake_phrase(config_path) or "hey aria"


def wake_set(config_path: str, phrase: str) -> dict:
    p = P.clean_wake_phrase(phrase)
    if not p:
        return {"ok": False, "error": "Scrivi due o tre parole, ad esempio «Hey Aria» o «Ciao Aria»: con una parola sola si sveglierebbe ogni volta che la senti in una frase."}
    P.set_wake_phrase(config_path, p)
    return {"ok": True, "wake_phrase": p}


# ------------------------------------------------------------------------------------ la cartella di Aria
def _screen_hint(name: str, config_path: str) -> str:
    """Il testo sotto gli interruttori dello schermo, con lo stato vero: c'e' il programma, c'e' il modello, quali modelli vedono."""
    import importlib.util
    import os
    from . import screen as S
    if name == "screen_mac":
        return "" if os.path.exists(S.OCR_HELPER) else " ⚠︎ Manca il programma che legge lo schermo: rilancia l'installazione."
    chat = P.load_settings(config_path).get("llm_model")
    model = (chat[4:] if chat and P.has_vision(chat) and P.is_mlx_ref(chat) else S.DEFAULT_VISION)
    try:
        ready = mlx_lm_installed(model)
    except Exception:                                                                    # noqa: BLE001
        ready = False
    out = (f" Modelli che vedono le immagini: Gemma 4 (E4B, 12B). Non vedono: Gemma 2 9B e Gemma 3 (1B, 4B, 12B). Userà {P.llm_label('mlx:' + model)}: "
           + ("già sul Mac." if ready else "da scaricare (sceglilo tra i chatbot e premi «Scarica»)."))
    if importlib.util.find_spec("mlx_vlm") is None:
        out += " ⚠︎ Manca il componente di visione: rilancia l'installazione."
    return out


def _voice_hint() -> str:
    try:
        from .tts import QwenTTS
        q = QwenTTS({})
        ready = q.downloaded()
    except Exception:                                                      # noqa: BLE001
        return ""
    import importlib.util
    if importlib.util.find_spec("mlx_audio") is None:
        return " ⚠︎ Manca il componente della voce: rilancia l'installazione."
    return " Il modello è già sul Mac: parte in una quindicina di secondi." if ready else " Il modello (~0,9 GB) non c'è ancora: lo scarica da sola, in background, appena la accendi."


def powers_status(config_path: str) -> list[dict]:
    """I poteri di Aria sul Mac con il loro interruttore: [{id, label, hint, enabled}]."""
    on = P.get_powers(config_path)
    return [{"id": k, "label": v[0], "hint": v[1] + (_screen_hint(k, config_path) if k in ("screen_mac", "screen_model") else _voice_hint() if k == "voice_natural" else ""), "enabled": on[k]} for k, v in P.POWERS.items()]


def power_set(config_path: str, name: str, enabled: bool) -> dict:
    if name not in P.POWERS:
        return {"ok": False, "error": f"funzione sconosciuta: {name}"}
    P.set_power(config_path, name, enabled)
    return {"ok": True, "powers": powers_status(config_path)}


def workspace_status(config_path: str) -> dict:
    """{path, valid, error, files}: la cartella scelta e se e' ancora utilizzabile (puo' essere stata spostata o cancellata)."""
    root = P.get_workspace(config_path)
    if not root:
        return {"path": None, "valid": False, "error": None, "files": 0}
    try:
        p = W.check_root(root)
        return {"path": p, "valid": True, "error": None, "files": len(W.Workspace(p).list())}
    except W.WorkspaceError as e:
        return {"path": root, "valid": False, "error": str(e), "files": 0}


def workspace_set(config_path: str, path: str) -> dict:
    """Sceglie la cartella di Aria: solo se e' una cartella adatta (non di sistema, non la Home, scrivibile)."""
    try:
        p = W.check_root(path)
    except W.WorkspaceError as e:
        return {"ok": False, "error": str(e)}
    P.set_workspace(config_path, p)
    return {"ok": True, **workspace_status(config_path)}


def workspace_clear(config_path: str) -> dict:
    P.set_workspace(config_path, None)
    return {"ok": True, **workspace_status(config_path)}


def _ollama_present() -> bool:
    try:
        from . import ollama
        return ollama.installed()
    except Exception:                                    # noqa: BLE001
        return False


# ------------------------------------------------------------------------------------ download
def _dir_size(path: str) -> int:
    total = 0
    try:
        for f in os.listdir(path):
            try:
                total += os.path.getsize(os.path.join(path, f))
            except OSError:
                pass
    except OSError:
        pass
    return total


def hf_total_bytes(repo: str) -> int:
    """Peso totale di un repo Hugging Face (chiede alla rete). Solleva se il modello non esiste."""
    from huggingface_hub import HfApi
    info = HfApi().model_info(repo, files_metadata=True)
    return int(sum((s.size or 0) for s in info.siblings))


def ollama_size_bytes(name: str, client=None) -> int | None:
    """Peso di un chatbot dal registro di Ollama (None se non lo trova)."""
    import httpx
    ns, _, rest = name.rpartition("/")
    base, _, tag = rest.partition(":")
    try:
        r = (client or httpx).get(f"{OLLAMA_REGISTRY}/v2/{ns or 'library'}/{base}/manifests/{tag or 'latest'}", timeout=8.0,
                                  headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
        r.raise_for_status()
        return int(sum(layer["size"] for layer in r.json()["layers"]))
    except Exception:                                    # noqa: BLE001
        return None


def hf_download(repo: str, total_bytes: int, out=emit, item: str = "stt") -> str:
    """Scarica un repo Hugging Face riprendendo da dove era arrivato; l'avanzamento si legge dalla cache (indipendente da tqdm)."""
    from huggingface_hub import constants, snapshot_download
    blobs = os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--"), "blobs")
    stop = threading.Event()

    def poll():
        while not stop.wait(0.6):
            out(event="progress", item=item, name=repo, done=_dir_size(blobs), total=total_bytes)

    t = threading.Thread(target=poll, daemon=True)
    t.start()
    try:
        return snapshot_download(repo)
    finally:
        stop.set()
        t.join(timeout=2)


def ollama_pull(model: str, total_hint: int, out=emit, client=None) -> None:
    """Scarica un chatbot con Ollama (/api/pull in streaming): riprende da solo i pezzi gia' scaricati."""
    import httpx
    layers: dict[str, tuple[int, int]] = {}
    last = 0.0
    cm = (client or httpx.Client(timeout=httpx.Timeout(30.0, read=None))).stream("POST", OLLAMA + "/api/pull", json={"model": model, "stream": True})
    with cm as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("error"):
                raise RuntimeError(ev["error"])
            if ev.get("digest") and ev.get("total"):
                layers[ev["digest"]] = (int(ev["total"]), int(ev.get("completed", 0)))
            now = time.monotonic()
            if now - last >= 0.5 or ev.get("status") == "success":
                last = now
                total = max(total_hint, sum(t for t, _ in layers.values()))
                out(event="progress", item="llm", name=model, done=sum(c for _, c in layers.values()), total=total, status=ev.get("status", ""))
            if ev.get("status") == "success":
                return
    raise RuntimeError("il download si e' interrotto prima della fine")


def _ensure_ollama(wait_s: float = 25.0) -> bool:
    """Se Ollama non risponde prova ad aprirlo e aspetta che sia pronto (vedi aria/ollama.py)."""
    from . import ollama
    return ollama.ensure_running(wait_s)


def _check_names(stt: str | None, llm: str | None) -> str | None:
    if stt and not P.valid_repo(stt):
        return f"Il nome del modello di riconoscimento vocale non e' valido: '{stt}' (serve il formato organizzazione/nome, ad esempio mlx-community/whisper-small-mlx)."
    if llm:
        ok = P.valid_repo(llm[4:]) if P.is_mlx_ref(llm) else P.valid_ollama_name(llm)
        if not ok:
            return f"Il nome del chatbot non e' valido: '{llm}' (un nome di Ollama come llama3.1:8b, oppure un modello MLX come mlx-community/gemma-3-text-4b-it-4bit)."
    return None


def _llm_bytes(ref: str, profile: str, preset_llm: str | None) -> int:
    """Peso da scaricare di un chatbot: dal catalogo, dalla versione, dal registro di Ollama o da Hugging Face. Solleva se un repo non esiste."""
    if ref in P.LLM_GB:
        return int(P.LLM_GB[ref] * 1e9)
    if preset_llm and ref == preset_llm and profile in P.PROFILES:
        return int(P.PROFILES[profile]["llm_gb"] * 1e9)
    if P.is_mlx_ref(ref):
        return hf_total_bytes(ref[4:])
    return ollama_size_bytes(ref) or int(5e9)


def download(config_path: str, profile: str, llm_override: str | None = None, stt_override: str | None = None, out=emit) -> bool:
    """Scarica i pezzi mancanti di una scelta (riconoscimento vocale, poi chatbot). Restituisce True se alla fine c'e' tutto."""
    if profile not in P.PROFILES and profile != P.CUSTOM:
        out(event="error", message=f"versione sconosciuta: {profile}")
        return False
    bad = _check_names(stt_override, llm_override)
    if bad:
        out(event="error", message=bad)
        return False
    base = cfgmod.load(config_path, settings=False)
    t = _target(base, profile, stt_override, llm_override)
    repo, llm = P.stt_repo(t["stt"]), t["llm"]
    need_stt = not stt_installed(t["stt"])
    if need_stt and t["stt"].get("kind") == "apple":
        out(event="error", message="Manca il programma di supporto per il riconoscimento di Apple: rilancia app/install.sh (lo compila).")
        return False
    llms = installed_llms()
    need_llm = not llm_ready(llm, llms)
    try:
        stt_bytes = int(P.STT_MB[repo] * 1e6) if repo in P.STT_MB else (hf_total_bytes(repo) if need_stt else 0)
    except Exception as e:                               # noqa: BLE001
        out(event="error", message=f"Non trovo il modello '{repo}' su Hugging Face ({type(e).__name__}). Controlla il nome e la connessione.")
        return False
    try:
        llm_bytes = _llm_bytes(llm, t["profile"], t["preset_llm"]) if need_llm else 0
    except Exception as e:                               # noqa: BLE001
        out(event="error", message=f"Non trovo il chatbot '{llm}' su Hugging Face ({type(e).__name__}). Controlla il nome e la connessione.")
        return False
    need = (stt_bytes if need_stt else 0) + (llm_bytes if need_llm else 0)
    free = disk_free_gb() * 1e9
    if need and free < need + MARGIN_GB * 1e9:
        out(event="error", message=f"Spazio insufficiente: servono circa {need / 1e9:.1f} GB (piu' {MARGIN_GB:.1f} GB di margine) e ne hai {free / 1e9:.1f} GB liberi.")
        return False
    try:
        if need_stt:
            out(event="start", item="stt", name=repo, label=P.STT_NAMES.get(repo, repo), total=stt_bytes)
            hf_download(repo, stt_bytes, out)
            problem = mlx_whisper_problem(repo) if t["stt"].get("kind") == "mlx-whisper" else None
            if problem:
                out(event="error", message=f"'{repo}' {problem}.")
                return False
            out(event="done", item="stt", name=repo)
        if need_llm and P.is_mlx_ref(llm):                           # chatbot dentro Aria: si scarica da Hugging Face, niente Ollama
            out(event="start", item="llm", name=llm, label=P.llm_label(llm), total=llm_bytes)
            hf_download(llm[4:], llm_bytes, out, item="llm")
            problem = mlx_lm_problem(llm[4:])
            if problem:
                out(event="error", message=f"'{llm[4:]}' {problem}.")
                return False
            out(event="done", item="llm", name=llm)
        elif need_llm:
            if not _ensure_ollama():
                out(event="error", message="Ollama non e' acceso: aprilo e riprova (oppure scegli un chatbot MLX, che non lo richiede).")
                return False
            out(event="start", item="llm", name=llm, label=llm, total=llm_bytes)
            ollama_pull(llm, llm_bytes, out)
            out(event="done", item="llm", name=llm)
    except Exception as e:                               # noqa: BLE001
        out(event="error", message=f"{type(e).__name__}: {e}")
        return False
    out(event="finished", ok=True)
    return True


# ------------------------------------------------------------------------------------ applica
def apply(config_path: str, profile: str, llm_override: str | None = None, stt_override: str | None = None, llms="auto") -> dict:
    """Salva la scelta in settings.json, ma solo se i pezzi sono installati (altrimenti l'app resterebbe muta)."""
    if profile not in P.PROFILES and profile != P.CUSTOM:
        return {"ok": False, "error": f"versione sconosciuta: {profile}"}
    bad = _check_names(stt_override, llm_override)
    if bad:
        return {"ok": False, "error": bad}
    base = cfgmod.load(config_path, settings=False)
    t = _target(base, profile, stt_override, llm_override)
    repo = P.stt_repo(t["stt"])
    if not stt_installed(t["stt"]):
        why = mlx_whisper_problem(repo) if t["stt"].get("kind") == "mlx-whisper" else None
        return {"ok": False, "error": f"Il riconoscimento vocale '{repo}' {why or 'non e'' ancora scaricato'}."}
    if not P.is_mlx_ref(t["llm"]):
        llms = installed_llms() if llms == "auto" else llms
        if llms is None:
            return {"ok": False, "error": "Ollama non risponde: aprilo e riprova (oppure scegli un chatbot MLX, che non lo richiede)."}
        if not _llm_known(t["llm"], llms):
            return {"ok": False, "error": f"Il chatbot '{t['llm']}' non e' installato."}
    elif not mlx_lm_installed(t["llm"][4:]):
        why = mlx_lm_problem(t["llm"][4:])
        return {"ok": False, "error": f"Il chatbot '{t['llm'][4:]}' {why or 'non e'' ancora scaricato'}."}
    if t["profile"] == P.CUSTOM:
        settings = {"profile": P.CUSTOM, "stt_model": repo, "llm_model": t["llm"]}
    else:
        settings = {"profile": t["profile"], "llm_model": t["llm"] if t["llm"] != t["preset_llm"] else None}
    P.save_settings(config_path, settings)
    return {"ok": True, "profile": t["profile"], "stt": repo, "llm": t["llm"]}


# ------------------------------------------------------------------------------------ rimuovi
def _hf_dir(repo: str) -> str:
    from huggingface_hub import constants
    return os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--"))


def _tree_size(path: str) -> int:
    """Spazio che si libera togliendo un modello: nella cache di Hugging Face i file veri stanno in blobs/ e snapshots/ ha solo collegamenti
    (contarli due volte raddoppierebbe il numero)."""
    root = os.path.join(path, "blobs")
    total = 0
    for base, _d, files in os.walk(root if os.path.isdir(root) else path):
        for f in files:
            fp = os.path.join(base, f)
            try:
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def remove(config_path: str, kind: str, ident: str, st: dict | None = None, client=None) -> dict:
    """Toglie un modello dal Mac. Mai quello in uso, mai l'ultimo installato (Aria non funzionerebbe piu').
    kind = 'stt' (ident = repo Hugging Face) | 'llm' (ident = riferimento: mlx:org/nome oppure nome di Ollama)."""
    if kind not in ("stt", "llm"):
        return {"ok": False, "error": f"cosa vuoi rimuovere? 'stt' o 'llm', non '{kind}'"}
    bad = _check_names(ident if kind == "stt" else None, ident if kind == "llm" else None)
    if bad:
        return {"ok": False, "error": bad}
    st = st or status(config_path)
    entries = st["stt_models"] if kind == "stt" else st["llm_models"]
    key = "repo" if kind == "stt" else "ref"
    e = next((m for m in entries if m[key] == ident), None)
    if e is None or not e["installed"]:
        return {"ok": False, "error": "Questo modello non e' installato."}
    if e["block"] == "in uso":
        return {"ok": False, "error": "E' il modello che Aria sta usando: scegline prima un altro e applica."}
    if e["block"]:
        return {"ok": False, "error": "E' l'unico installato: Aria ha bisogno di almeno un modello per funzionare."}
    if kind == "llm" and not P.is_mlx_ref(ident):                    # modello di Ollama
        import httpx
        try:
            r = (client or httpx).request("DELETE", OLLAMA + "/api/delete", json={"model": ident}, timeout=30.0)
            r.raise_for_status()
        except Exception as ex:                                      # noqa: BLE001
            return {"ok": False, "error": f"Ollama non l'ha rimosso ({type(ex).__name__})."}
        return {"ok": True, "freed_mb": round((e.get("gb") or 0) * 1000)}
    repo = ident if kind == "stt" else ident[4:]
    d = _hf_dir(repo)
    from huggingface_hub import constants
    if not os.path.realpath(d).startswith(os.path.realpath(constants.HF_HUB_CACHE) + os.sep) or not os.path.basename(d).startswith("models--"):
        return {"ok": False, "error": "Percorso non valido: non rimuovo nulla."}           # per sicurezza: solo dentro la cache dei modelli
    freed = _tree_size(d)
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True, "freed_mb": round(freed / 1e6)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aria.models")
    ap.add_argument("cmd", choices=["status", "download", "apply", "remove", "workspace", "power", "wake"])
    ap.add_argument("profile", nargs="?")
    ap.add_argument("ident", nargs="?")
    ap.add_argument("--config", required=True)
    ap.add_argument("--llm")
    ap.add_argument("--stt")
    ap.add_argument("--extra-stt")
    ap.add_argument("--extra-llm")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(json.dumps(status(a.config, extra_stt=a.extra_stt, extra_llm=a.extra_llm), ensure_ascii=False))
        return 0
    if a.cmd == "power":
        if a.profile in (None, "status"):
            res = {"ok": True, "powers": powers_status(a.config)}
        else:
            res = power_set(a.config, a.profile, (a.ident or "").lower() in ("on", "true", "1", "si", "sì"))
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res["ok"] else 1
    if a.cmd == "workspace":
        res = (workspace_set(a.config, a.ident or "") if a.profile == "set" else workspace_clear(a.config) if a.profile == "clear"
               else {"ok": True, **workspace_status(a.config)})
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res["ok"] else 1
    if a.cmd == "wake":                                                       # wake set "hey aria" | wake clear | wake
        res = (wake_set(a.config, a.ident or "") if a.profile == "set" else (P.set_wake_phrase(a.config, None) or {"ok": True, "wake_phrase": _wake_status(a.config)})
               if a.profile == "clear" else {"ok": True, "wake_phrase": _wake_status(a.config)})
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res["ok"] else 1
    if a.cmd == "remove":
        if a.profile not in ("stt", "llm") or not a.ident:
            ap.error("serve: remove stt|llm IDENTIFICATIVO")
        res = remove(a.config, a.profile, a.ident)
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res["ok"] else 1
    if not a.profile:
        ap.error("serve la versione: leggera, media, pesante o personalizzata")
    if a.cmd == "download":
        return 0 if download(a.config, a.profile, a.llm, a.stt) else 1
    res = apply(a.config, a.profile, a.llm, a.stt)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
