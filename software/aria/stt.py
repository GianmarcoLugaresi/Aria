"""Riconoscimento vocale (italiano). Due modi: server compatibile OpenAI sul tuo Mac/mini PC, oppure Whisper nel processo."""
from __future__ import annotations

import asyncio
import io
import re
import logging
import os
import wave

import httpx
import numpy as np

log = logging.getLogger("aria.stt")
PROMPT = "Conversazione in italiano tra una persona e Aria, un'assistente da scrivania."


def prepare_audio(pcm: np.ndarray, target_db: float = -20.0, max_gain_db: float = 24.0) -> np.ndarray:
    """int16 -> float32 [-1,1]. Toglie il DC e ALZA il volume se il microfono e' basso: Whisper sbaglia molto con audio debole.
    Non abbassa mai e non manda in saturazione."""
    x = pcm.astype(np.float32) / 32768.0
    if len(x) == 0:
        return x
    x = x - float(x.mean())
    peak = float(np.max(np.abs(x))) + 1e-9
    rms = float(np.sqrt(np.mean(x * x))) + 1e-9
    gain = 10 ** ((target_db - 20 * np.log10(rms)) / 20)
    gain = max(1.0, min(gain, 10 ** (max_gain_db / 20), 0.95 / peak))
    return np.clip(x * gain, -1.0, 1.0)


def audio_stats(pcm: np.ndarray) -> tuple[float, float]:
    """(picco, rms) in dBFS: servono a capire se il microfono e' troppo basso o in saturazione."""
    x = pcm.astype(np.float32) / 32768.0
    if len(x) == 0:
        return -99.0, -99.0
    return (20 * np.log10(float(np.max(np.abs(x))) + 1e-9), 20 * np.log10(float(np.sqrt(np.mean(x * x))) + 1e-9))


# frasi che Whisper "inventa" sul silenzio o sul rumore (sottotitoli dei video su cui e' stato addestrato)
_HALLUCINATIONS = ("sottotitoli", "amara org", "sottotitoli creati", "iscriviti al canale", "grazie a tutti per la visione",
                   "alla prossima", "grazie per la visione", "ci vediamo al prossimo video", "subtitles by", "www ")


_FUNC = {"il", "lo", "la", "le", "i", "gli", "l", "un", "una", "uno", "del", "dello", "della", "dei", "degli", "delle", "dell", "di", "da", "in", "con", "su", "per", "tra", "fra", "a", "al", "allo", "alla", "ai",
         "agli", "alle", "all", "e", "o", "ma", "se", "che", "non", "mi", "ti", "ci", "si", "vi", "li", "ne", "poi", "come", "cosa", "quando", "dove", "perche", "perché", "gia", "già", "anche", "sul", "sulla",
         "nel", "nella", "nello", "dal", "dalla", "ho", "ha", "hai", "sono", "è", "e'", "ora", "allora", "quindi", "cioe", "cioè", "ecco", "tipo"}
_PREP_PAIR = {"di": {"del", "dello", "della", "dei", "degli", "delle", "dell"}, "a": {"al", "allo", "alla", "ai", "agli", "alle", "all"}, "in": {"nel", "nello", "nella", "nei", "negli", "nelle", "nell"},
              "da": {"dal", "dallo", "dalla", "dai", "dagli", "dalle", "dall"}, "su": {"sul", "sullo", "sulla", "sui", "sugli", "sulle", "sull"}}


def dedupe_repeats(text: str) -> str:
    """Le esitazioni del parlato che il riconoscimento di Apple trascrive alla lettera: «del del», «se se va», «già già», «ti sto ti sto», «di degli». Whisper le toglie da solo; qui si fa lo stesso
    (solo parole di servizio e gruppi di 2-3 parole ripetuti: «molto molto» o «no no» restano, sono enfasi)."""
    toks = text.split()
    if len(toks) < 2:
        return text
    bare = lambda w: re.sub(r"[^\wàèéìòù']", "", w.lower())
    out: list[str] = []
    i = 0
    cap = lambda w, was_cap: (w[:1].upper() + w[1:]) if was_cap and w[:1].islower() else w
    while i < len(toks):
        done = False
        for n in (3, 2):                                                      # gruppo di n parole subito ripetuto: si tiene la SECONDA volta (ha la punteggiatura finale)
            a, b = toks[i:i + n], toks[i + n:i + 2 * n]
            if len(a) == n and len(b) == n and [bare(x) for x in a] == [bare(x) for x in b] and all(bare(x) for x in a):
                b = list(b)
                b[0] = cap(b[0], a[0][:1].isupper())
                out.extend(b)
                i += 2 * n
                done = True
                break
        if done:
            continue
        w = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if nxt and bare(w) == bare(nxt) and bare(w) in _FUNC:                  # «del del» -> «del» (con la maiuscola e la punteggiatura giuste)
            toks[i + 1] = cap(nxt, w[:1].isupper())
            i += 1
            continue
        if nxt and bare(w) in _PREP_PAIR and bare(nxt) in _PREP_PAIR[bare(w)]:  # «di degli» -> «degli»
            toks[i + 1] = cap(nxt, w[:1].isupper())
            i += 1
            continue
        out.append(w)
        i += 1
    return " ".join(out)


def clean_transcript(text: str) -> str:
    from .textutil import normalize
    t = normalize(text)
    if not t:
        return ""
    if any(h in t for h in _HALLUCINATIONS) and len(t.split()) <= 8:
        return ""
    words = t.split()
    if len(words) >= 6 and len(set(words)) <= 2:                  # "sì sì sì sì sì sì": ripetizione da allucinazione
        return ""
    return dedupe_repeats(text.strip())


def segment_confidence(segments: list[dict]) -> dict | None:
    """Fiducia di Whisper sulla frase: avg_logprob (0 = sicurissimo, -1 = incerto, -2 = quasi a caso), probabilita' di "non e' parlato", compressione (ripetizioni)."""
    segs = [x for x in segments if "avg_logprob" in x]
    if not segs:
        return None
    dur = sum(max(0.05, float(x.get("end", 0)) - float(x.get("start", 0))) for x in segs)
    avg = sum(float(x["avg_logprob"]) * max(0.05, float(x.get("end", 0)) - float(x.get("start", 0))) for x in segs) / dur
    return {"avg_logprob": avg, "no_speech": max(float(x.get("no_speech_prob", 0.0)) for x in segs), "compression": max(float(x.get("compression_ratio", 1.0)) for x in segs)}


def pcm_to_wav(pcm: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


class OpenAISTT:
    """POST /v1/audio/transcriptions: va bene speaches/faster-whisper-server, mlx-audio, LocalAI, whisper.cpp (modalita' OpenAI)."""

    def __init__(self, cfg: dict):
        self.base = cfg["base_url"].rstrip("/")
        self.model = cfg.get("model", "whisper-1")
        self.lang = cfg.get("language", "it")
        self.http = httpx.AsyncClient(timeout=30.0)

    async def transcribe(self, pcm: np.ndarray, sr: int = 16000) -> str:
        r = await self.http.post(self.base + "/audio/transcriptions",
                                 files={"file": ("audio.wav", pcm_to_wav(pcm, sr), "audio/wav")},
                                 data={"model": self.model, "language": self.lang, "temperature": "0",
                                       "response_format": "json", "prompt": PROMPT})
        r.raise_for_status()
        return r.json().get("text", "").strip()


class FasterWhisperSTT:
    """Whisper in-process con CTranslate2 (pip install faster-whisper). Sul Raspberry: model 'small' o 'base', int8."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.model = None

    def _load(self):
        if self.model is None:
            from faster_whisper import WhisperModel  # type: ignore
            import os
            self.model = WhisperModel(self.cfg.get("model", "small"), device=self.cfg.get("device", "auto"),
                                      compute_type=self.cfg.get("compute_type", "int8"),
                                      cpu_threads=int(self.cfg.get("cpu_threads", min(8, os.cpu_count() or 4))))
            log.info("Whisper '%s' caricato", self.cfg.get("model", "small"))
        return self.model

    def _run(self, pcm: np.ndarray) -> str:
        m = self._load()
        audio = prepare_audio(pcm)
        segs, _ = m.transcribe(audio, language=self.cfg.get("language", "it"), beam_size=int(self.cfg.get("beam_size", 5)), vad_filter=False,
                               condition_on_previous_text=False, initial_prompt=PROMPT, temperature=[0.0, 0.2, 0.4])
        return clean_transcript(" ".join(s.text.strip() for s in segs))

    async def warmup(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self._run, np.zeros(16000, dtype=np.int16))

    async def transcribe(self, pcm: np.ndarray, sr: int = 16000) -> str:
        if sr != 16000:
            raise ValueError("faster-whisper vuole audio a 16 kHz")
        return await asyncio.get_running_loop().run_in_executor(None, self._run, pcm)


class MLXWhisperSTT:
    """Whisper su GPU Apple (MLX): gira sul Mac con chip Apple. Con 'mlx-community/whisper-large-v3-turbo-q4' (0,46 GB)
    si ha un modello MOLTO piu' preciso di 'small' allo stesso peso. pip install mlx-whisper"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.repo = cfg.get("model", "mlx-community/whisper-large-v3-turbo-q4")
        from .mlxpool import POOL
        self.pool = POOL                                          # MLX vuole sempre lo stesso thread (condiviso con il chatbot MLX)
        self.loaded = False
        self.last_conf: dict | None = None                        # quanto era sicuro Whisper dell'ultima frase (serve a dire «non ho capito» invece di rispondere a caso)

    def _load(self):
        if not self.loaded:
            from huggingface_hub import snapshot_download
            snapshot_download(self.repo)                          # scarica se manca
            self._run(np.zeros(16000, dtype=np.int16))            # e compila i kernel una volta
            self.loaded = True
            log.info("MLX Whisper '%s' pronto", self.repo)

    def _run(self, pcm: np.ndarray) -> str:
        import mlx_whisper                                       # type: ignore
        audio = prepare_audio(pcm)
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=self.repo, language=self.cfg.get("language", "it"),
                                   condition_on_previous_text=False, initial_prompt=PROMPT if self.cfg.get("prompt", True) else None,
                                   verbose=None, fp16=True, no_speech_threshold=0.6)
        self.last_conf = segment_confidence(r.get("segments") or [])
        return clean_transcript(r.get("text", ""))

    async def warmup(self) -> None:
        await asyncio.get_running_loop().run_in_executor(self.pool, self._load)

    async def transcribe(self, pcm: np.ndarray, sr: int = 16000) -> str:
        if sr != 16000:
            raise ValueError("MLX Whisper vuole audio a 16 kHz")
        self.loaded = True
        return await asyncio.get_running_loop().run_in_executor(self.pool, self._run, pcm)


APPLE_HELPER = os.path.join(os.environ.get("ARIA_BIN") or os.path.expanduser("~/Library/Application Support/Aria/bin"), "aria-apple-stt")


def apple_helper_path(cfg: dict | None = None) -> str:
    return (cfg or {}).get("helper") or os.environ.get("ARIA_APPLE_STT") or APPLE_HELPER


class AppleSTT:
    """Il riconoscimento vocale INTEGRATO nel Mac (Apple SpeechTranscriber, macOS 26+): nessun modello da scaricare, non pesa sulla RAM di Aria
    e risponde in ~0,1 s. Parla con un programma di supporto (software/helpers/aria_apple_stt.swift, compilato dall'installer): una riga per frase."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.helper = apple_helper_path(cfg)
        self.proc: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()
        self.last_conf: dict | None = None                      # Apple non da' una misura di sicurezza come Whisper
        self.pending = 0                                        # richieste scritte al programma di cui non si e' ancora letta la risposta (una richiesta annullata a meta')

    async def _start(self) -> None:
        if self.proc and self.proc.returncode is None:
            return
        if not os.path.exists(self.helper):
            raise RuntimeError(f"manca il programma di supporto per il riconoscimento di Apple ({self.helper}): rilancia app/install.sh")
        self.pending = 0
        self.proc = await asyncio.create_subprocess_exec(self.helper, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        line = await asyncio.wait_for(self.proc.stdout.readline(), 600)         # la prima volta puo' scaricare la lingua italiana (dati di Apple)
        if line.decode("utf-8", "ignore").strip() != "READY":
            err = line.decode("utf-8", "ignore").strip()
            self.proc.kill()
            self.proc = None
            raise RuntimeError(f"riconoscimento di Apple non pronto: {err or 'nessuna risposta'}")
        log.info("Riconoscimento vocale di Apple pronto")

    async def warmup(self) -> None:
        async with self.lock:
            await self._start()

    async def transcribe(self, pcm: np.ndarray, sr: int = 16000) -> str:
        if sr != 16000:
            raise ValueError("il riconoscimento di Apple qui vuole audio a 16 kHz")
        import os as _os
        import tempfile
        x = prepare_audio(pcm)                                   # lo stesso trattamento (volume) che si da' a Whisper
        x = np.concatenate([np.zeros(8000, np.float32), x, np.zeros(8000, np.float32)])
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="aria_stt_")
        _os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(pcm_to_wav((np.clip(x, -1, 1) * 32767).astype(np.int16), 16000))
            async with self.lock:
                await self._start()
                try:
                    while self.pending > 0:                      # la risposta a una richiesta annullata arriva comunque: si butta, altrimenti questa frase riceve il testo di un'altra
                        await asyncio.wait_for(self.proc.stdout.readline(), 10)
                        self.pending -= 1
                    self.proc.stdin.write((path + "\n").encode())
                    self.pending += 1
                    await self.proc.stdin.drain()
                    line = (await asyncio.wait_for(self.proc.stdout.readline(), 30)).decode("utf-8", "ignore").rstrip("\n")
                    self.pending -= 1
                except Exception:                                # noqa: BLE001
                    if self.proc:
                        self.proc.kill()
                    self.proc, self.pending = None, 0
                    raise
        finally:
            try:
                _os.remove(path)
            except OSError:
                pass
        if not line.startswith("R\t"):
            raise RuntimeError(f"riconoscimento di Apple: {line[:120] or 'nessuna risposta'}")
        self.last_conf = None
        return clean_transcript(line[2:])

    def close(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.kill()


def make_stt(cfg: dict):
    kind = cfg.get("kind", "openai")
    if kind == "openai":
        return OpenAISTT(cfg)
    if kind == "faster-whisper":
        return FasterWhisperSTT(cfg)
    if kind == "mlx-whisper":
        return MLXWhisperSTT(cfg)
    if kind == "apple":
        return AppleSTT(cfg)
    raise ValueError(f"STT sconosciuto: {kind}")
