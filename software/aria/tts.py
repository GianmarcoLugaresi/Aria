"""Sintesi vocale. Tre modi: Piper (CPU, leggerissimo), Kokoro (82M, piu' naturale), server compatibile OpenAI (es. Qwen3-TTS sul Mac)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil

import httpx
import numpy as np

log = logging.getLogger("aria.tts")


def _i16(x: np.ndarray) -> np.ndarray:
    if x.dtype.kind == "f":
        x = np.clip(x, -1.0, 1.0) * 32767.0
    return x.astype(np.int16)


class PiperTTS:
    """Usa l'eseguibile `piper` (pip install piper-tts) leggendo PCM grezzo: API stabile anche se la libreria cambia."""

    def __init__(self, cfg: dict):
        self.model = os.path.expanduser(cfg["model_path"])
        self.bin = cfg.get("binary") or shutil.which("piper") or "piper"
        self.speed = float(cfg.get("speed", 1.0))
        meta = self.model + ".json"
        self.sr = json.load(open(meta))["audio"]["sample_rate"] if os.path.exists(meta) else 22050

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        proc = await asyncio.create_subprocess_exec(
            self.bin, "--model", self.model, "--output_raw", "--length_scale", str(1.0 / self.speed),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await proc.communicate(text.encode("utf-8"))
        if not out:
            raise RuntimeError("piper non ha prodotto audio")
        return np.frombuffer(out, dtype=np.int16), self.sr


class KokoroTTS:
    """pip install kokoro-onnx; servono kokoro-v1.0.onnx e voices-v1.0.bin. Voci italiane: if_sara (donna), im_nicola (uomo)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.k = None

    def _load(self):
        if self.k is None:
            from kokoro_onnx import Kokoro  # type: ignore
            d = os.path.expanduser(cfg_dir) if (cfg_dir := self.cfg.get("model_dir")) else "models"
            self.k = Kokoro(os.path.join(d, "kokoro-v1.0.onnx"), os.path.join(d, "voices-v1.0.bin"))
        return self.k

    def _run(self, text: str):
        k = self._load()
        samples, sr = k.create(text, voice=self.cfg.get("voice", "if_sara"), speed=float(self.cfg.get("speed", 1.0)), lang="it")
        return _i16(np.asarray(samples)), int(sr)

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        return await asyncio.get_running_loop().run_in_executor(None, self._run, text)


class OpenAITTS:
    """POST /v1/audio/speech con response_format=pcm (s16le mono). Es. Kokoro-FastAPI, openedai-speech, server MLX."""

    def __init__(self, cfg: dict):
        self.base = cfg["base_url"].rstrip("/")
        self.model = cfg.get("model", "tts-1")
        self.voice = cfg.get("voice", "alloy")
        self.sr = int(cfg.get("sample_rate", 24000))
        self.speed = float(cfg.get("speed", 1.0))
        self.http = httpx.AsyncClient(timeout=30.0)

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        r = await self.http.post(self.base + "/audio/speech", json={"model": self.model, "input": text, "voice": self.voice,
                                                                   "response_format": "pcm", "speed": self.speed})
        r.raise_for_status()
        return np.frombuffer(r.content, dtype=np.int16), self.sr


def _guard_eos(model, confirm_logit: float = 0.0, extra_frames: int = 8) -> bool:
    """Pocket TTS decide da solo quando ha finito la frase, ma a volte lo «sente» troppo presto (il segnale di fine sale piano, senza il picco netto
    che c'e' quando ha davvero finito) e l'ultima parola si taglia («scacchi» -> «sca», «insalata» -> «insalto»). Qui, se il segnale di fine non ha
    raggiunto un picco sicuro, si lasciano `extra_frames` pezzetti (80 ms l'uno) in piu' perche' la parola finisca. Se qualcosa non torna con la
    versione di pocket-tts installata, non si cambia niente (resta il comportamento originale). Restituisce True se il controllo e' attivo."""
    try:
        import torch
        state = {"logit": -99.0}
        orig_forward = model.flow_lm.out_eos.forward

        def hook(x):
            y = orig_forward(x)
            state["logit"] = float(y.reshape(-1)[0])
            return y
        model.flow_lm.out_eos.forward = hook
        min_frames = model._MIN_FRAMES_BEFORE_EOS

        @torch.no_grad()
        def generate(self, model_state, max_gen_len, frames_after_eos, latents_queue, stop):
            backbone_input = torch.full((1, 1, self.flow_lm.ldim), fill_value=float("NaN"), device=next(iter(self.flow_lm.parameters())).device, dtype=self.flow_lm.dtype)
            eos_step = spike_step = None
            for step in range(max_gen_len):
                if stop.is_set():
                    break
                next_latent, is_eos = self._run_flow_lm_and_increment_step(model_state=model_state, backbone_input_latents=backbone_input)
                if step >= min_frames:
                    if is_eos.item() and eos_step is None:
                        eos_step = step
                    if state["logit"] > confirm_logit and spike_step is None:
                        spike_step = step
                if spike_step is not None and step >= spike_step + frames_after_eos:
                    break                                                   # fine sicura: come prima
                if spike_step is None and eos_step is not None and step >= eos_step + frames_after_eos + extra_frames:
                    break                                                   # fine incerta: gli si e' dato il tempo di finire la parola
                latents_queue.put(next_latent)
                backbone_input = next_latent
            latents_queue.put(None)

        import types
        model._autoregressive_generation = types.MethodType(generate, model)
        return True
    except Exception as e:                                                   # noqa: BLE001
        log.warning("controllo della fine frase di Pocket TTS non attivato (%s): resta quello di fabbrica", e)
        return False


class PocketTTS:
    """Kyutai Pocket TTS: 100M parametri, solo CPU, ~7x tempo reale su Mac, italiano incluso (MIT + CC-BY-4.0).
    pip install pocket-tts. Voci predefinite: lola, vera, eve, jane, mary, cosette, anna, estelle, fantine (donne); giovanni, paul, ... (uomini)."""

    VOICES_F = ["lola", "vera", "eve", "jane", "mary", "cosette", "anna", "estelle", "fantine", "azelma", "eponine", "alba"]

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.language = cfg.get("language", "italian")          # "italian_24l" = piu' qualita', 3x piu' pesante
        self.voice = cfg.get("voice", "lola")
        self.frames_after_eos = cfg.get("frames_after_eos", 14)  # quanti pezzetti (80 ms) generare dopo il «ho finito» del modello (di fabbrica 1-5): con pochi l'ultima parola si taglia.
        #                                                          Misurato su 24 frasi difficili x voce: con la voce «anna» da 3/24 frasi complete a ~16/24, le altre voci restano a 20-21/24
        self.eos_threshold = cfg.get("eos_threshold")            # piu' alto = il modello finisce piu' tardi
        self.temperature = cfg.get("temperature")                # None = quella consigliata dal modello (0,3); piu' bassa = voce piu' stabile
        self.eos_guard = cfg.get("eos_guard", True)              # lascia finire l'ultima parola quando il modello «chiude» troppo presto
        self.model = None
        self.state = None
        from concurrent.futures import ThreadPoolExecutor
        self.pool = ThreadPoolExecutor(max_workers=1)             # torch non e' thread-safe: una sintesi alla volta

    def _load(self):
        if self.model is None:
            from pocket_tts import TTSModel  # type: ignore
            kw = {"eos_threshold": float(self.eos_threshold)} if self.eos_threshold is not None else {}
            if self.temperature is not None:
                kw["temp"] = float(self.temperature)
            self.model = TTSModel.load_model(language=self.language, **kw)
            self.state = self.model.get_state_for_audio_prompt(self.voice)
            guard = _guard_eos(self.model) if self.eos_guard else False
            log.info("Pocket TTS pronto (%s, voce %s, %d Hz%s)", self.language, self.voice, self.model.sample_rate, ", fine frase protetta" if guard else "")
        return self.model

    def set_voice(self, name: str) -> None:
        self.voice = name
        if self.model is not None:
            self.state = self.model.get_state_for_audio_prompt(name)

    def _run(self, text: str):
        m = self._load()
        kw = {"frames_after_eos": int(self.frames_after_eos)} if self.frames_after_eos is not None else {}
        audio = m.generate_audio(self.state, text, **kw)
        return _i16(audio.detach().cpu().numpy().astype(np.float32).squeeze()), int(m.sample_rate)

    async def warmup(self) -> None:
        await asyncio.get_running_loop().run_in_executor(self.pool, self._run, "Ciao.")

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        return await asyncio.get_running_loop().run_in_executor(self.pool, self._run, text)


class MacSayTTS:
    """Il comando `say` di macOS: zero installazione, voci italiane di sistema (Alice, ...). Piu' robotica di Pocket TTS."""

    def __init__(self, cfg: dict):
        self.voice = cfg.get("voice", "Alice")
        self.rate = int(cfg.get("rate", 175))

    def set_voice(self, name: str) -> None:
        self.voice = name

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        import tempfile
        import wave
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            proc = await asyncio.create_subprocess_exec("say", "-v", self.voice, "-r", str(self.rate), "-o", path,
                                                        "--file-format=WAVE", "--data-format=LEI16@22050", text,
                                                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
            with wave.open(path, "rb") as w:
                return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()
        finally:
            os.unlink(path)


class QwenTTS:
    """La «voce naturale»: Qwen3-TTS (0,6 mld di parametri, 4 bit) in un processo a parte (qwentts_server.py). Parla con la voce di una registrazione di riferimento (aria/voices/<nome>.wav):
    sempre la stessa voce, in italiano, senza i tagli e le parole mangiate di Pocket TTS. Misurato su 18 frasi: 13 perfette, 2,6 % di parole sbagliate (Pocket 10 perfette, 5,2 %),
    ~3x il tempo reale, 1,8 GB di RAM (picco 2,8). Si accende dalle Impostazioni (potere «voice_natural»); il modello (~0,9 GB) si scarica da solo la prima volta."""

    REPO = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit"
    NATURAL_ONLY = ("aria", "chiara", "elena", "marco")                  # si chiamano solo a voce («usa la voce di Marco»)
    FOLLOW = ("lola", "vera", "eve", "jane", "mary", "cosette", "anna", "estelle", "fantine", "giovanni", "paul", "george", "michael", "javert")
    #                                                                    i nomi del selettore dell'app: sceglierne uno cambia la voce di Pocket E quella naturale (che ha una registrazione di riferimento per ciascuno)
    VOICES = NATURAL_ONLY + FOLLOW
    FILES = ("model.safetensors", "speech_tokenizer/model.safetensors", "config.json")

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.repo = cfg.get("repo", self.REPO)
        self.voice = cfg.get("voice_natural") or (cfg.get("voice") if cfg.get("voice") in self.FOLLOW else "aria")             # (senza una scelta a voce: quella del selettore)
        self.temperature = float(cfg.get("temperature", 0.8))
        self.proc: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self._rid = 0
        self._starting: asyncio.Task | None = None
        self._dl = None
        self._dl_error = ""
        self._ready = False                                                # il processo ha detto READY (il modello e' in memoria e i kernel compilati)
        self._bad_until = 0.0                                              # dopo un errore: pausa, si usa la voce di prima
        self._on_cache: tuple[float, bool] = (0.0, False)
        self._dl_cache: tuple[float, bool] = (-99.0, False)
        self._dl_retry_at = 0.0

    # ---- disponibilita'
    def enabled(self) -> bool:
        import time
        ts, val = self._on_cache
        if time.monotonic() - ts < 2.0:
            return val
        try:
            from . import profiles as P
            val = bool(P.get_powers(self.cfg.get("_config_path")).get("voice_natural", False))
        except Exception:                                                  # noqa: BLE001
            val = False
        self._on_cache = (time.monotonic(), val)
        return val

    def downloaded(self) -> bool:
        import time
        ts, val = self._dl_cache
        if val and time.monotonic() - ts < 30.0 or (not val and time.monotonic() - ts < 3.0):
            return val
        try:
            from huggingface_hub import try_to_load_from_cache
            val = all(isinstance(try_to_load_from_cache(self.repo, f), str) for f in self.FILES)
        except Exception:                                                  # noqa: BLE001
            val = False
        self._dl_cache = (time.monotonic(), val)
        return val

    def _download_bg(self) -> None:
        """Scarica il modello senza bloccare Aria (la voce di prima parla nel frattempo)."""
        import threading
        import time
        if (self._dl is not None and self._dl.is_alive()) or time.monotonic() < self._dl_retry_at:
            return

        def run():
            try:
                from huggingface_hub import snapshot_download
                log.info("voce naturale: scarico il modello (%s)…", self.repo)
                snapshot_download(self.repo)
                log.info("voce naturale: modello scaricato")
                self._dl_error = ""
            except Exception as e:                                         # noqa: BLE001
                self._dl_error = str(e)[:120]
                self._dl_retry_at = time.monotonic() + 300.0                # (rete assente o lenta: riprova fra cinque minuti, non a ogni frase)
                log.warning("voce naturale: download non riuscito (%s)", self._dl_error)
        self._dl = threading.Thread(target=run, daemon=True)
        self._dl.start()

    def usable(self) -> bool:
        """Si puo' parlare con la voce naturale ADESSO? (acceso nelle Impostazioni, modello scaricato, processo pronto). Altrimenti avvia quello che manca e risponde no."""
        import time
        if not self.enabled():
            if self.proc is not None:
                self.close()                                               # spenta: libera la memoria
            return False
        if time.monotonic() < self._bad_until:
            return False
        if not self.downloaded():
            self._download_bg()
            return False
        if self._ready and self.proc is not None and self.proc.returncode is None:
            return True
        if self._starting is None or self._starting.done():
            try:
                self._starting = asyncio.get_running_loop().create_task(self._start_quiet())
            except RuntimeError:
                return False
        return False

    # ---- processo
    def _voice_files(self) -> tuple[str, str]:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")
        name = self.voice if self.voice in self.VOICES else "aria"
        return os.path.join(d, name + ".wav"), os.path.join(d, name + ".txt")

    async def _start_quiet(self) -> None:
        try:
            await self._start()
        except Exception as e:                                             # noqa: BLE001
            import time
            log.warning("voce naturale non partita (%s): resta la voce di prima per un po'", str(e)[:150])
            self._bad_until = time.monotonic() + 120

    async def _start(self) -> None:
        import json
        import sys
        async with self.lock:
            if self.proc and self.proc.returncode is None:
                return
            wav, txt = self._voice_files()
            conf = {"repo": self.repo, "ref_audio": wav, "ref_text": open(txt, encoding="utf-8").read().strip(), "temperature": self.temperature}
            self._ready = False
            cmd = list(self.cfg.get("server_cmd") or [sys.executable, "-m", "aria.qwentts_server"])                       # ("server_cmd": solo per i test)
            self.proc = await asyncio.create_subprocess_exec(*cmd, json.dumps(conf), stdin=asyncio.subprocess.PIPE,
                                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            line = b""
            try:
                for _ in range(50):                                         # (qualche libreria stampa prima: si cerca la riga READY)
                    line = await asyncio.wait_for(self.proc.stdout.readline(), 240)
                    if not line or line.decode("utf-8", "ignore").strip() == "READY":
                        break
            except asyncio.TimeoutError:
                line = b""
            if line.decode("utf-8", "ignore").strip() != "READY":
                self.proc.kill()
                self.proc = None
                raise RuntimeError("il processo della voce non e' diventato pronto")
            self._ready = True
            log.info("voce naturale pronta (%s)", self.voice)

    def close(self) -> None:
        self._ready = False
        if self.proc is not None:
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass
            self.proc = None

    def set_voice(self, name: str) -> None:
        if name in self.VOICES:
            self.voice = name                                              # (la registrazione di riferimento viaggia con ogni frase: nessun riavvio)

    async def warmup(self) -> None:
        if self.enabled() and self.downloaded():
            await self._start()

    async def synthesize(self, text: str, lang: str = "it") -> tuple[np.ndarray, int]:
        import json
        import time
        import wave
        if not self.usable():
            raise RuntimeError("voce naturale non pronta")
        async with self.lock:
            if not self._ready or self.proc is None or self.proc.returncode is not None:
                raise RuntimeError("voce naturale non attiva")
            self._rid += 1
            rid = self._rid
            wav, txt = self._voice_files()
            try:
                self.proc.stdin.write((json.dumps({"id": rid, "text": text, "seed": int(time.time() * 1000) % 100000, "ref_audio": wav,
                                                   "ref_text": open(txt, encoding="utf-8").read().strip(), "lang": lang}) + "\n").encode())
                await self.proc.stdin.drain()
                while True:
                    line = await asyncio.wait_for(self.proc.stdout.readline(), 20 + 0.25 * len(text))
                    if not line:
                        raise RuntimeError("il processo della voce si e' chiuso")
                    ans = json.loads(line)
                    if ans.get("id") == rid:
                        break                                              # (una risposta rimasta a una richiesta annullata si salta)
                    if ans.get("path"):
                        try:
                            os.unlink(ans["path"])
                        except OSError:
                            pass
            except Exception:                                              # noqa: BLE001
                self.close()
                self._bad_until = time.monotonic() + 30
                raise
        if "error" in ans:
            raise RuntimeError(ans["error"])
        path = ans["path"]
        try:
            with wave.open(path, "rb") as w:
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                sr = w.getframerate()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return pcm, sr


class AutoTTS:
    """La voce di Aria: la «naturale» (Qwen3-TTS) quando e' accesa e pronta, altrimenti Pocket TTS come sempre. Se la naturale sbaglia, quella frase la dice Pocket."""

    def __init__(self, cfg: dict):
        self.pocket = PocketTTS(cfg)
        self.qwen = QwenTTS(cfg)

    @property
    def voice(self):
        return self.pocket.voice

    @property
    def chunk_chars(self) -> int:
        """Pocket TTS taglia le frasi lunghe: a pezzi da 30 caratteri. La voce naturale regge frasi intere."""
        return self.qwen.CHUNK if self.qwen.usable() else 30

    def set_voice(self, name: str) -> None:
        if name in QwenTTS.VOICES:
            self.qwen.set_voice(name)                                        # la voce naturale con quel nome…
        if name not in QwenTTS.NATURAL_ONLY:
            self.pocket.set_voice(name)                                      # …e quella di prima (i nomi del selettore valgono per tutte e due)

    async def warmup(self) -> None:
        if self.qwen.enabled() and self.qwen.downloaded():
            try:
                await self.qwen.warmup()
                return
            except Exception as e:                                         # noqa: BLE001
                log.warning("voce naturale: avvio non riuscito (%s)", str(e)[:120])
        await self.pocket.warmup()

    _FOREIGN = re.compile(r"^In (inglese|francese|spagnolo|tedesco|portoghese): (.+)$", re.S)
    _LANG_CODE = {"inglese": "en", "francese": "fr", "spagnolo": "es", "tedesco": "de", "portoghese": "pt"}

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        if self.qwen.usable():
            try:
                m = self._FOREIGN.match(text)
                if m:                                                            # «In inglese: good morning»: l'introduzione in italiano e la frase nella sua lingua
                    a, sr = await self.qwen.synthesize(f"In {m.group(1)}:")
                    b, sr2 = await self.qwen.synthesize(m.group(2), self._LANG_CODE[m.group(1)])
                    return np.concatenate([np.asarray(a).reshape(-1), np.zeros(int(0.15 * sr), dtype=np.int16), np.asarray(b).reshape(-1)]), sr
                return await self.qwen.synthesize(text)
            except Exception as e:                                         # noqa: BLE001
                log.warning("voce naturale: %s -> questa frase la dice Pocket TTS", str(e)[:120])
        return await self.pocket.synthesize(text)


QwenTTS.CHUNK = 120


def make_tts(cfg: dict):
    kind = cfg.get("kind", "piper")
    return {"piper": PiperTTS, "kokoro": KokoroTTS, "openai": OpenAITTS, "pocket": PocketTTS, "say": MacSayTTS, "natural": AutoTTS}[kind](cfg)
