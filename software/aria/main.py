"""Avvio:  python -m aria.main --config config.yaml   [--dev] [--text] [--list-devices]"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from . import config as cfgmod
from .display import serve_display
from .leds import make_leds
from .llm import OpenAILLM, make_llm
from .memory import Memory
from . import i18n
from .persona import build_system, load_persona, load_persona_for
from .router import Router
from .state import Hub
from .stt import make_stt
from .tools import Tools
from .tts import make_tts
from .vad import make_vad


def _voice_file(cfg: dict) -> str:
    return os.path.join(cfg["data_dir"], "voce.en.txt" if i18n.is_en() else "voce.txt")                   # una voce scelta per lingua: «lola» in italiano non e' quella giusta per l'inglese


def _natural_voice_file(cfg: dict) -> str:
    return os.path.join(cfg["data_dir"], "voce_naturale.en.txt" if i18n.is_en() else "voce_naturale.txt")


def _restore_voice(cfg: dict, hub: Hub) -> None:
    """La voce scelta dal menu dell'app resta salvata tra un avvio e l'altro (quella di Pocket in voce.txt, quella della «voce naturale» in voce_naturale.txt)."""
    try:
        name = open(_voice_file(cfg), encoding="utf-8").read().strip()
    except OSError:
        name = ""
    try:
        natural = open(_natural_voice_file(cfg), encoding="utf-8").read().strip()
    except OSError:
        natural = ""
    from .tts import QwenTTS
    if name in QwenTTS.NATURAL_ONLY:                                    # (vecchi salvataggi: una voce solo-naturale scritta nel posto sbagliato)
        name, natural = "", name
    elif name in QwenTTS.FOLLOW and not natural:
        natural = name                                                  # la voce scelta dal selettore vale anche per la naturale
    for b in cfg["brains"]:
        t = b.get("tts", {})
        if name and t.get("kind") in ("pocket", "say", "natural"):
            t["voice"] = name
        if natural and t.get("kind") == "natural":
            t["voice_natural"] = natural
    shown = name
    if not shown:                                                       # nessuna scelta salvata: il menu segna comunque la voce di fabbrica
        for b in cfg["brains"]:
            t = b.get("tts", {})
            if t.get("kind") == "pocket" and t.get("voice"):
                shown = t["voice"]
                break
    if shown:
        hub.set_info(voice=shown)

    def save(cmd: dict) -> None:
        if cmd.get("cmd") == "voice" and cmd.get("name"):
            paths = []
            if cmd["name"] in QwenTTS.VOICES:
                paths.append(_natural_voice_file(cfg))                  # (l'ultima scelta vince: anche quella del selettore sostituisce una fatta a voce)
            if cmd["name"] not in QwenTTS.NATURAL_ONLY:
                paths.append(_voice_file(cfg))
            for path in paths:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(cmd["name"])
    hub.on_command(save)


def _parent_alive(ppid: int) -> bool:
    """Il processo che ci ha avviati e' ancora li'? Su Mac/Linux il padre di un orfano cambia (getppid); su Windows resta il vecchio numero: si chiede al sistema se e' finito."""
    if sys.platform != "win32":
        return os.getppid() == ppid
    import ctypes
    SYNCHRONIZE, WAIT_TIMEOUT = 0x00100000, 0x102
    k32 = ctypes.windll.kernel32                                            # type: ignore[attr-defined]
    h = k32.OpenProcess(SYNCHRONIZE, False, ppid)
    if not h:
        return False                                                        # non esiste piu'
    try:
        return k32.WaitForSingleObject(h, 0) == WAIT_TIMEOUT
    finally:
        k32.CloseHandle(h)


async def watch_parent() -> None:
    """Se l'app che ci ha avviati sparisce (chiusura forzata, crash), ci spegniamo: niente processi orfani."""
    ppid = os.getppid()
    while True:
        await asyncio.sleep(2.0)
        if not _parent_alive(ppid):
            logging.getLogger("aria").warning("l'app non c'e' piu': esco")
            os._exit(0)


async def warmup(router: Router, hub: Hub) -> None:
    """Carica in memoria LLM, riconoscimento e voce; poi segnala "pronta" all'app."""
    import time
    t0 = time.monotonic()
    for stage in ("stt", "tts", "llm"):
        try:
            async for _b, obj in router.candidates(stage):
                if hasattr(obj, "warmup"):
                    await obj.warmup()
                elif hasattr(obj, "_load"):
                    await asyncio.get_running_loop().run_in_executor(None, obj._load)
                break
        except Exception as e:                                       # noqa: BLE001
            logging.getLogger("aria").warning("riscaldamento %s non riuscito: %s", stage, e)
    logging.getLogger("aria").info("pronta in %.1fs", time.monotonic() - t0)
    hub.set_info(ready=True)


def prefetch(cfg: dict) -> int:
    """Scarica/carica i modelli una volta sola (l'installer lo lancia): cosi' il primo avvio e' subito pronto."""
    import httpx
    bad = 0
    stages = [(b["name"], "stt", b["stt"]) for b in cfg["brains"] if b.get("stt")]
    if cfg["wake"].get("stt"):
        stages.append(("attivazione", "stt", cfg["wake"]["stt"]))
    stages += [(b["name"], "tts", b["tts"]) for b in cfg["brains"] if b.get("tts")]
    for name, stage, c in stages:
        kind = c.get("kind")
        try:
            if stage == "stt" and kind == "mlx-whisper":
                print(f"[{name}] riconoscimento vocale: MLX Whisper '{c.get('model')}' (primo avvio: download)…", flush=True)
                make_stt(c)._load()
            elif stage == "stt" and kind == "faster-whisper":
                print(f"[{name}] riconoscimento vocale: Whisper '{c.get('model', 'small')}' (primo avvio: download)…", flush=True)
                make_stt(c)._load()
            elif stage == "tts" and kind in ("pocket", "natural"):
                print(f"[{name}] voce: Pocket TTS {c.get('language', 'italian')} (primo avvio: download)…", flush=True)
                obj = make_tts(c)
                (getattr(obj, "pocket", None) or obj)._load()
            elif stage == "tts" and kind == "say":
                print(f"[{name}] voce: comando 'say' di macOS (nessun download)", flush=True)
        except Exception as e:                                       # noqa: BLE001
            print(f"  ERRORE: {e}", flush=True)
            bad += 1
    for b in cfg["brains"]:
        llm = b.get("llm")
        if not llm:
            continue
        if llm.get("kind") == "mlx-lm":                              # chatbot dentro Aria: si scarica da Hugging Face, niente Ollama
            try:
                from huggingface_hub import snapshot_download
                print(f"[{b['name']}] chatbot: MLX '{llm['model']}' (primo avvio: download)…", flush=True)
                snapshot_download(llm["model"])
            except Exception as e:                                   # noqa: BLE001
                print(f"  ERRORE: {e}", flush=True)
                bad += 1
            continue
        try:
            r = httpx.get(llm["base_url"].rstrip("/") + "/models", timeout=3.0)
            ids = [x.get("id") for x in r.json().get("data", [])]
            if llm["model"] in ids:
                print(f"[{b['name']}] modello '{llm['model']}' presente", flush=True)
            else:
                print(f"[{b['name']}] MANCA il modello '{llm['model']}': esegui  ollama pull {llm['model']}", flush=True)
                bad += 1
        except Exception:                                            # noqa: BLE001
            print(f"[{b['name']}] il server LLM non risponde su {llm['base_url']}: avvia Ollama", flush=True)
            bad += 1
    return bad


def factory(stage: str, cfg: dict):
    return {"llm": make_llm, "stt": make_stt, "tts": make_tts}[stage](cfg)


def build(cfg: dict, config_path: str | None):
    hub = Hub()
    memory = Memory(os.path.join(cfg["data_dir"], "memoria.db")) if cfg["memory"]["enabled"] else None
    bases = [os.path.dirname(os.path.abspath(config_path))] if config_path else []
    bases += [os.getcwd(), os.path.join(os.path.dirname(__file__), "..")]
    persona = load_persona_for(cfg, bases, config_path)
    router = Router(cfg["brains"], factory)
    return hub, memory, persona, router


def _ensure_ollama_bg(cfg: dict) -> None:
    """Se il chatbot e' Ollama locale e non risponde, lo apre e aspetta che sia pronto (in parallelo al caricamento dei modelli)."""
    try:
        from . import ollama
        if ollama.is_local((cfg["brains"][0].get("llm") or {}).get("base_url")):
            ollama.ensure_running()
    except Exception as e:                                       # noqa: BLE001
        logging.getLogger("aria").warning("avvio di Ollama non riuscito: %s", e)


def _make_mic(a: dict):
    """Sul Mac, con le casse, il microfono passa dal filtro eco di macOS (audio.VoiceMic) cosi' si puo' interrompere Aria a voce mentre parla; si spegne con `audio.voice_processing: false`."""
    import sys
    from .audio import Mic, VoiceMic, vpmic_path
    if sys.platform == "darwin" and a.get("voice_processing", True) and a["input_rate"] == 16000 and a.get("input_device") is None and os.path.exists(vpmic_path()):
        return VoiceMic(a["input_device"], a["input_rate"])
    return Mic(a["input_device"], a["input_rate"])

def _timer_message(label: str) -> str:
    """Cosa dice Aria quando un timer scade (o un «ricordami tra dieci minuti di…»)."""
    if i18n.is_en():
        return f"Reminder: {label}." if label.startswith(("to ", "that ")) else f"Your {label} timer is up."
    return f"Ti ricordo {label}." if label.startswith("di ") else f"Il timer {label} è scaduto."


async def run_voice(cfg, config_path, dev: bool, no_display: bool):
    asyncio.get_running_loop().run_in_executor(None, _ensure_ollama_bg, cfg)
    from .audio import Speaker
    from .conversation import Aria
    from .wake import KeyboardWake, make_wake
    if dev:
        cfg["audio"]["barge_in"] = False
    hub, memory, persona, router = build(cfg, config_path)
    a = cfg["audio"]
    fake = os.environ.get("ARIA_FAKE_AUDIO")
    if fake:                                                        # collaudo senza microfono/altoparlanti
        from .fakeaudio import FileMic, NullSpeaker
        mic, speaker = FileMic(fake, hub), NullSpeaker(a["output_rate"])
    else:
        speaker = Speaker(a["output_device"], a["output_rate"], a["volume"])
        mic = _make_mic(a)
    mode = cfg["wake"]["mode"]
    if mode == "stt":
        wake = None                                         # il riconoscimento della frase e' dentro Aria (wait_for_wake)
    else:
        wake = KeyboardWake() if (dev and not cfg["wake"]["model_path"]) or mode == "keyboard" else make_wake(cfg["wake"])
    aria_ref: dict = {}
    tools = Tools(cfg, memory, on_timer=lambda label: aria_ref["a"].announce(_timer_message(label)))
    aria = Aria(cfg, hub, mic, speaker, wake, make_vad(cfg["vad"]["kind"]), router, tools, memory, persona)
    if not fake:
        from .vad import make_idle_vad
        aria.idle_vad = make_idle_vad(cfg["vad"]["kind"])              # per aspettare «hey aria» tutto il giorno: lo stesso tipo di rilevatore, ma su un solo thread (batteria)
    aria_ref["a"] = aria
    if mode == "stt" and cfg["wake"].get("stt"):
        aria.wake_stt = make_stt(cfg["wake"]["stt"])                  # Whisper piccolo solo per "hey aria"
    _restore_voice(cfg, hub)
    hub.set_info(ready=False, wake_phrase=cfg["wake"]["phrase"])                # (l'app la mostra nel menu: «Stato: pronta, di' «Hey Aria»»)
    bg = [asyncio.create_task(warmup(router, hub))]                 # (riferimenti tenuti fino alla fine: asyncio da solo li terrebbe solo con riferimenti deboli)
    if os.environ.get("ARIA_PARENT_WATCH"):
        bg.append(asyncio.create_task(watch_parent()))
    tasks = [asyncio.create_task(make_leds(cfg["leds"]).run(hub))]
    if not no_display:
        d = cfg["display"]
        await serve_display(hub, d["host"], d["port"], d["fps"])
    await aria.run()
    for t in tasks:
        t.cancel()


async def run_text(cfg, config_path):
    """Prova carattere, strumenti e memoria SENZA audio: scrivi una frase, leggi la risposta."""
    from .conversation import Aria
    hub, memory, persona, router = build(cfg, config_path)
    tools = Tools(cfg, memory)

    class Dummy:
        pass

    aria = Aria(cfg, hub, Dummy(), Dummy(), Dummy(), Dummy(), router, tools, memory, persona)
    aria.sys_prompt = build_system(persona, cfg, memory.context() if memory else "")
    print(f"[testo] parli con {cfg['name']}. Ctrl-C per uscire.\n")
    while True:
        try:
            user = await asyncio.get_running_loop().run_in_executor(None, input, "tu > ")
        except (EOFError, KeyboardInterrupt):
            break
        aria.history.append({"role": "user", "content": user})
        msgs = [{"role": "system", "content": aria.sys_prompt}] + aria.history[-12:]
        async for kind, val in aria.reply_events(msgs):
            print(f"  [{kind}] {val}" if kind != "sentence" else f"aria > {val}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aria")
    ap.add_argument("--config")
    ap.add_argument("--dev", action="store_true", help="sviluppo: Invio al posto del wake word, niente interruzioni")
    ap.add_argument("--text", action="store_true", help="solo testo: prova carattere/strumenti senza audio")
    ap.add_argument("--no-display", action="store_true")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--prefetch", action="store_true", help="scarica e verifica i modelli, poi esce")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    if args.list_devices:
        from .audio import list_devices
        print(list_devices())
        return 0
    cfg = cfgmod.load(args.config)
    if args.prefetch:
        return 1 if prefetch(cfg) else 0
    logging.basicConfig(level=logging.DEBUG if args.verbose else cfg["log_level"], format="%(asctime)s %(name)s: %(message)s")
    try:
        asyncio.run(run_text(cfg, args.config) if args.text else run_voice(cfg, args.config, args.dev, args.no_display))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
