"""Configurazione: valori di default + file YAML che li sovrascrive (merge ricorsivo)."""
from __future__ import annotations

import copy
import os
from typing import Any

DEFAULTS: dict[str, Any] = {
    "name": "Aria",
    "language": None,                    # None = lo decidono le Impostazioni, poi la lingua del sistema (vedi i18n.py): «it» o «en»
    "location": {"city": "Roma", "lat": 41.9028, "lon": 12.4964},   # per meteo e ora locale: cambia!
    "persona_file": "../anima/persona_compatta.md",
    "units": "auto",                     # auto | metric | imperial: gradi Celsius o Fahrenheit nel meteo (in inglese: lo decide il Mac, o la regione)
    "data_dir": "~/.aria",
    "wake": {
        "phrase": "hey aria",
        "mode": "auto",                  # model | stt | keyboard | auto (model se c'è model_path, altrimenti keyboard)
        "model_path": None,              # modello openWakeWord addestrato (.onnx); None = modalita' sviluppo (tasto Invio)
        "threshold": 0.6,
        "cooldown_s": 2.0,
        "verify_with_stt": True,         # riconferma con il riconoscimento vocale (taglia i falsi positivi)
    },
    "audio": {
        "input_device": None,            # numero o parte del nome (es. "ReSpeaker")
        "output_device": None,
        "input_rate": 16000,
        "output_rate": 16000,            # il XVF3800 suona a 16 kHz; sul Mac puoi mettere 24000
        "barge_in": True,                # interrompibile mentre parla (richiede AEC hardware, o cuffie)
        "sleep_on_battery": True,        # a batteria, con lo schermo spento da un minuto, smette di ascoltare e lascia andare il Mac in stop
        "volume": 0.9,
    },
    "turn": {
        "first_turn_timeout_s": 6.0,     # dopo il wake word, quanto aspetta che inizi a parlare
        "follow_up_timeout_s": 8.0,      # dopo la risposta, finestra senza dover richiamare
        "end_silence_ms": 750,           # silenzio che chiude la frase
        "min_speech_ms": 250,
        "max_utterance_s": 20.0,
        "preroll_ms": 700,               # audio tenuto PRIMA che il rilevatore si accorga della voce: con voce bassa si accorge tardi e si perdeva l'inizio della parola («Abbassalo» -> «Baselò»)
        "barge_in_ms": 260,
        "filler_after_ms": 0,            # >0: se la risposta tarda dice "vediamo..." (spento: la voce cortissima cambia timbro)
        "first_chunk_min_chars": 30,     # la prima frase non parte da sola se piu' corta: Pocket TTS cambierebbe timbro
    },
    "vad": {"threshold": 0.5, "kind": "auto", "gain": "auto"},    # auto = Silero se disponibile, altrimenti energia; gain: volume dato al RILEVATORE (non a Whisper) quando parli piano; "auto" lo adatta, 1 = spento
    # cervelli in ordine di preferenza: il primo raggiungibile vince, per ogni stadio
    "brains": [
        {
            "name": "on-device",
            "llm": {"base_url": "http://127.0.0.1:8080/v1", "model": "local", "temperature": 0.8, "max_tokens": 180,
                    "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},   # llama.cpp; per Ollama: {"reasoning_effort": "none"}
            "stt": {"kind": "faster-whisper", "model": "small", "compute_type": "int8"},
            "tts": {"kind": "piper", "model_path": "models/it_IT-paola-medium.onnx", "voice": None},
        }
    ],
    "tools": {
        "web_search": {"kind": "ddgs", "searxng_url": None, "max_results": 4},
        "weather": True,
        "wikipedia": True,
        "timers": True,
    },
    "memory": {"enabled": True, "max_facts_in_prompt": 6, "history_turns": 6},
    "display": {"host": "127.0.0.1", "port": 8765, "fps": 30},
    "leds": {"kind": "none", "count": 38},       # none | pi5neo (strip WS2812 via SPI sul Raspberry Pi 5)
    "log_level": "INFO",
}


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(path: str | None = None, settings: bool = True) -> dict:
    """settings=True: sopra config.yaml applica le scelte delle Impostazioni (settings.json: versione e chatbot, vedi profiles.py)."""
    cfg = copy.deepcopy(DEFAULTS)
    saved: dict = {}
    if path:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            cfg = deep_merge(cfg, yaml.safe_load(f) or {})
        if settings:
            from .profiles import apply_settings, load_settings
            saved = load_settings(path)
            cfg = apply_settings(cfg, saved)
    if settings:
        from . import i18n                                                  # la lingua: Impostazioni > config.yaml > sistema; vale per tutto il programma
        lang = i18n.resolve(saved.get("language"), cfg.get("language"))
        i18n.adapt_config(cfg, lang)
        i18n.set_language(lang)
    if path:
        cfg["_config_path"] = os.path.abspath(path)                 # le Impostazioni (es. la cartella di Aria) si rileggono da qui senza riavviare
        for b in cfg.get("brains") or []:
            if isinstance(b.get("tts"), dict):
                b["tts"]["_config_path"] = cfg["_config_path"]       # (la voce naturale si accende e spegne dalle Impostazioni senza riavviare)
    cfg["data_dir"] = os.path.expanduser(cfg["data_dir"])
    os.makedirs(cfg["data_dir"], exist_ok=True)
    return cfg
