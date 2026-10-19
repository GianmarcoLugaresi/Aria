"""Rilevamento della voce e dei turni di parola.

- EnergyVAD: nessuna dipendenza, soglia adattiva sul rumore di fondo. Funziona, ma e' meno furbo.
- SileroVAD: rete neurale piccolissima (pip install pysilero-vad); molto meglio con musica e rumori.
- Endpointer: trasforma la sequenza di probabilita' in eventi "start / end / timeout".
"""
from __future__ import annotations

import logging
import math

import numpy as np

log = logging.getLogger("aria.vad")
FRAME = 512          # campioni a 16 kHz = 32 ms (richiesto da Silero)


class EnergyVAD:
    def __init__(self, margin_db: float = 9.0):
        self.floor_db = -60.0
        self.margin = margin_db
        self.n = 0

    def reset(self) -> None:
        self.n = 0

    def prob(self, frame: np.ndarray) -> float:
        x = frame.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(x * x)) + 1e-9)
        db = 20 * math.log10(rms)
        self.n += 1
        if self.n < 15 or db < self.floor_db + 3:                 # il pavimento segue il rumore (sale piano, scende in fretta)
            self.floor_db += (db - self.floor_db) * (0.2 if db < self.floor_db else 0.01)
        return 1.0 / (1.0 + math.exp(-(db - (self.floor_db + self.margin)) / 2.0))


class SileroVAD:
    def __init__(self):
        from pysilero_vad import SileroVoiceActivityDetector  # type: ignore
        self.det = SileroVoiceActivityDetector()
        self.prob(np.zeros(FRAME, dtype=np.int16))                # self-test: se l'API e' diversa, solleva subito

    def reset(self) -> None:
        if hasattr(self.det, "reset"):
            self.det.reset()

    def prob(self, frame: np.ndarray) -> float:
        raw = frame.astype(np.int16).tobytes()
        p = self.det(raw) if callable(self.det) else self.det.process_chunk(raw)
        return float(p)


def _silero_onnx_path() -> str | None:
    """Il modello Silero v6 in formato ONNX che arriva gia' con faster-whisper (nessun download): si cerca senza importare il pacchetto (che e' pesante)."""
    import importlib.util
    import os
    try:
        spec = importlib.util.find_spec("faster_whisper")
    except Exception:                                             # noqa: BLE001
        spec = None
    if spec is None or not spec.origin:
        return None
    p = os.path.join(os.path.dirname(spec.origin), "assets", "silero_vad_v6.onnx")
    return p if os.path.exists(p) else None


class OnnxSileroVAD:
    """Silero eseguito con onnxruntime su UN solo thread. Misurato col microfono vero, 31 blocchi al secondo, tre prove alternate: pysilero-vad 11-14 % di un core
    (a ogni blocco crea e distrugge un gruppo di thread ggml), questo 1,6 % (il microfono da solo 1,3-1,8 %). E' il modello v6 di faster-whisper, non il v6.2 di pysilero:
    l'inizio della voce lo trova uguale, ma alla fine delle frasi e' meno «tenace» (su 40 registrazioni vere a volte chiude prima). Per questo si usa solo ad aspettare
    «hey aria» (tutto il giorno: li' conta la batteria), mentre in conversazione resta pysilero."""

    CONTEXT = 64                                                  # Silero vuole gli ultimi 64 campioni del blocco precedente davanti a ogni blocco da 512

    def __init__(self, path: str | None = None):
        import onnxruntime as ort  # type: ignore
        path = path or _silero_onnx_path()
        if not path:
            raise RuntimeError("modello Silero ONNX non trovato")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.enable_cpu_mem_arena = False
        opts.log_severity_level = 4
        self.sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"], sess_options=opts)
        self.reset()
        self.prob(np.zeros(FRAME, dtype=np.int16))                # self-test: se il modello e' diverso, solleva subito
        self.reset()

    def reset(self) -> None:
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = np.zeros((1, 1, 128), dtype=np.float32)
        self.ctx = np.zeros(self.CONTEXT, dtype=np.float32)

    def prob(self, frame: np.ndarray) -> float:
        x = np.asarray(frame, dtype=np.float32).reshape(-1) / 32768.0
        inp = np.concatenate([self.ctx, x])[None, :]
        out, self.h, self.c = self.sess.run(None, {"input": inp, "h": self.h, "c": self.c})
        self.ctx = x[-self.CONTEXT:]
        return float(np.asarray(out).reshape(-1)[0])


def make_idle_vad(kind: str = "auto"):
    """Il rilevatore per l'attesa di «hey aria» (gira tutto il giorno): Silero su un solo thread se c'e', altrimenti None (si usa quello normale)."""
    if kind not in ("auto", "silero"):
        return None
    try:
        return OnnxSileroVAD()
    except Exception as e:                                        # noqa: BLE001
        log.info("Silero leggero per l'attesa non disponibile (%s): uso quello normale", str(e)[:80])
        return None


def make_vad(kind: str = "auto"):
    if kind in ("auto", "silero"):
        try:
            return SileroVAD()
        except Exception as e:                                    # noqa: BLE001
            if kind == "silero":
                raise
            log.info("Silero VAD (pysilero-vad) non disponibile (%s): provo la versione ONNX", str(e)[:80])
        try:
            return OnnxSileroVAD()                                    # (Windows/Linux senza il pacchetto nativo: stesso modello, onnxruntime)
        except Exception as e:                                        # noqa: BLE001
            if kind == "silero":
                raise
            log.warning("Silero VAD non disponibile (%s): uso il rilevatore a energia", e)
    return EnergyVAD()


class Endpointer:
    """Macchina a stati sul flusso di probabilita'. push(prob) -> None | 'start' | 'end' | 'timeout'."""

    def __init__(self, frame_ms: float = 32.0, start_ms: int = 96, end_silence_ms: int = 750, min_speech_ms: int = 250,
                 max_utterance_s: float = 20.0, no_speech_timeout_s: float = 6.0, on: float = 0.5, off: float = 0.35):
        self.fm = frame_ms
        self.start_frames = max(1, round(start_ms / frame_ms))
        self.end_frames = max(1, round(end_silence_ms / frame_ms))
        self.min_speech_frames = max(1, round(min_speech_ms / frame_ms))
        self.max_frames = round(max_utterance_s * 1000 / frame_ms)
        self.timeout_frames = round(no_speech_timeout_s * 1000 / frame_ms)
        self.on, self.off = on, off
        self.reset()

    def reset(self) -> None:
        self.in_speech = False
        self.run = 0            # frame consecutivi sopra soglia (attesa) o sotto soglia (in parlato)
        self.speech_frames = 0
        self.total = 0
        self.waited = 0

    def push(self, prob: float):
        if not self.in_speech:
            self.waited += 1
            self.run = self.run + 1 if prob >= self.on else 0
            if self.run >= self.start_frames:
                self.in_speech, self.run = True, 0
                self.speech_frames = self.start_frames
                self.total = self.start_frames
                return "start"
            if self.timeout_frames and self.waited >= self.timeout_frames:
                return "timeout"
            return None
        self.total += 1
        if prob >= self.off:
            self.speech_frames += 1
            self.run = 0
        else:
            self.run += 1
        if self.run >= self.end_frames:
            if self.speech_frames >= self.min_speech_frames:
                return "end"
            self.in_speech, self.run, self.total, self.speech_frames = False, 0, 0, 0   # un click: ignoralo
            return None
        if self.total >= self.max_frames:
            return "end"
        return None
