"""Microfono e altoparlante (sounddevice). Importato solo quando serve, cosi' i test girano senza scheda audio."""
from __future__ import annotations

import asyncio
from collections import deque
import logging
import os
import subprocess
import threading
import time

import numpy as np

log = logging.getLogger("aria.audio")


def resolve_device(spec, kind: str):
    """None -> predefinito; int -> indice; str -> primo dispositivo il cui nome la contiene."""
    import sounddevice as sd
    if spec is None or isinstance(spec, int):
        return spec
    ch = "max_input_channels" if kind == "input" else "max_output_channels"
    for i, d in enumerate(sd.query_devices()):
        if str(spec).lower() in d["name"].lower() and d[ch] > 0:
            return i
    log.warning("dispositivo audio '%s' non trovato: uso il predefinito", spec)
    return None


def default_devices() -> tuple[int | None, int | None]:
    """(microfono predefinito, uscita predefinita) di macOS come numeri di CoreAudio: cambiano quando colleghi o scolleghi gli AirPods. (None, None) se non si riesce a saperlo."""
    try:
        import ctypes
        import sys
        if sys.platform != "darwin":
            return None, None
        ca = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")

        class Addr(ctypes.Structure):
            _fields_ = [("sel", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("elem", ctypes.c_uint32)]

        def get(sel: int) -> int | None:
            dev, size = ctypes.c_uint32(0), ctypes.c_uint32(4)
            addr = Addr(sel, 0x676C6F62, 0)                                                       # 'glob'
            err = ca.AudioObjectGetPropertyData(1, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(dev))
            return int(dev.value) if err == 0 and dev.value else None
        return get(0x64496E20), get(0x644F7574)                                                   # 'dIn ' e 'dOut'
    except Exception:                                                                             # noqa: BLE001
        return None, None


def audio_problem(before: tuple, now: tuple, frame_age: float, speaking: bool, follow_default: bool = True) -> str | None:
    """Serve riaprire microfono e casse? 'ferma' = il microfono non manda piu' niente (dispositivo sparito: gli AirPods si sono scollegati), 'cambiato' = il dispositivo predefinito
    e' un altro (e non sta parlando: non si taglia una frase a meta'). None = tutto bene."""
    if frame_age > 4.0:
        return "ferma"
    if follow_default and before != now and None not in before and None not in now and not speaking:
        return "cambiato"
    return None


def reinit_audio(mic, speaker) -> None:
    """Chiude i flussi, fa rileggere a PortAudio l'elenco dei dispositivi e li riapre sul predefinito di adesso."""
    import sounddevice as sd
    for fn in (getattr(mic, "close_sync", None), speaker.close):
        try:
            if fn:
                fn()
        except Exception:                                                                         # noqa: BLE001
            pass
    sd._terminate()
    sd._initialize()
    speaker.start()
    mic.start_sync()


def list_devices() -> str:
    import sounddevice as sd
    return str(sd.query_devices())


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or len(x) == 0:
        return x
    n = int(round(len(x) * sr_out / sr_in))
    xp = np.linspace(0, len(x) - 1, num=n)
    return np.interp(xp, np.arange(len(x)), x.astype(np.float32)).astype(np.int16)


def tone(freqs: list[float], dur: float = 0.09, sr: int = 16000, vol: float = 0.25) -> np.ndarray:
    parts = []
    for f in freqs:
        t = np.arange(int(sr * dur)) / sr
        env = np.minimum(1.0, np.minimum(t / 0.01, (dur - t) / 0.03))
        parts.append((np.sin(2 * np.pi * f * t) * env * vol * 32767).astype(np.int16))
    return np.concatenate(parts)


CHIME_WAKE = [660.0, 880.0]
CHIME_DONE = [660.0, 520.0]
CHIME_ERROR = [330.0, 247.0]
CHIME_TIMER = [880.0, 880.0, 1175.0]


class Frame(np.ndarray):
    """Un blocco di microfono con l'ORARIO in cui e' stato registrato (`adc`, secondi sullo stesso orologio dell'uscita audio): serve a sottrarre l'eco di Aria (vedi aec.py)."""
    adc: float | None = None


class Mic:
    cleaned = False                                                         # True = il microfono arriva GIA' senza l'eco delle casse (vedi VoiceMic)

    def __init__(self, device=None, rate: int = 16000, block: int = 512):
        self.device, self.rate, self.block = device, rate, block
        self.q: asyncio.Queue | None = None
        self.stream = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.last_frame = time.monotonic()                                  # quando e' arrivato l'ultimo blocco: se passano secondi, il dispositivo e' sparito

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.q = asyncio.Queue(maxsize=400)
        self.start_sync()

    def start_sync(self) -> None:
        import sounddevice as sd
        self.last_frame = time.monotonic()

        def cb(indata, frames, time_info, status):
            if status:
                log.debug("mic: %s", status)
            self.last_frame = time.monotonic()
            frame = indata[:, 0].copy().view(Frame)
            try:
                frame.adc = float(time_info.inputBufferAdcTime)
            except Exception:                                    # noqa: BLE001
                frame.adc = None
            self.loop.call_soon_threadsafe(self._put, frame)

        self.stream = sd.InputStream(device=resolve_device(self.device, "input"), samplerate=self.rate, channels=1,
                                     dtype="int16", blocksize=self.block, callback=cb)
        self.stream.start()

    def _put(self, frame: np.ndarray) -> None:
        if self.q.full():
            self.q.get_nowait()
        self.q.put_nowait(frame)

    async def frames(self):
        while True:
            yield await self.q.get()

    def flush(self) -> None:
        while self.q and not self.q.empty():
            self.q.get_nowait()

    def close_sync(self) -> None:
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:                                                # noqa: BLE001
                pass
            self.stream = None

    async def stop(self) -> None:
        self.close_sync()


VPMIC_HELPER = os.path.join(os.environ.get("ARIA_BIN") or os.path.expanduser("~/Library/Application Support/Aria/bin"), "aria-vpmic")


def vpmic_path() -> str:
    return os.environ.get("ARIA_VPMIC") or VPMIC_HELPER


class VoiceMic(Mic):
    """Il microfono con il filtro eco e antirumore del Mac (Voice Processing, quello delle chiamate FaceTime), tramite un programma di supporto (helpers/aria_vpmic.swift).
    Mentre Aria parla dalle casse la sua voce viene TOLTA dal microfono (misurato su queste casse: la voce di Aria sparisce del tutto, e la voce dell'utente sopra la sua si
    riconosce parola per parola), quindi si puo' interromperla a voce anche mentre parla senza pause.

    Il filtro costa batteria (misurato: ~12 % di un core per il programma + ~11 % per coreaudiod, di continuo), quindi NON resta acceso: a riposo (Aria aspetta «hey aria») si usa il
    microfono normale, che costa quasi niente; `engage()` accende il filtro quando inizia una conversazione, `release()` lo spegne alla fine. Nel passaggio il microfono normale resta
    aperto finche' il filtro non manda il primo blocco, cosi' non si perde nemmeno una parola.
    Se il programma non parte (permesso, macOS vecchio) o si ferma troppe volte di seguito, si resta sul microfono normale (`cleaned` False: Aria usa il suo filtro e l'ascolto nelle pause)."""

    def __init__(self, device=None, rate: int = 16000, block: int = 512, helper: str | None = None):
        super().__init__(device, rate, block)
        self.helper = helper or vpmic_path()
        self.proc: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.wanted = False                                                 # c'e' una conversazione: il filtro eco deve essere acceso
        self._closing = False
        self._gen = 0                                                       # a ogni (ri)avvio un numero nuovo: un thread vecchio capisce da solo che deve smettere
        self._lk = threading.RLock()                                        # apertura/chiusura del microfono normale
        self._skip_until = 0.0                                              # fino a quando (orologio monotonico) si resta sul microfono normale perche' quello con filtro eco non funzionava
        self.first_frame_timeout = 4.0                                      # dopo «READY» il primo blocco di audio deve arrivare entro questi secondi
        self.retry_after = 900.0                                            # dopo un fallimento si riprova col filtro eco non prima di 15 minuti

    # ---- microfono normale (sempre aperto a riposo)
    def _plain_on(self) -> None:
        with self._lk:
            if self.stream is None and not self._closing:
                Mic.start_sync(self)

    def _plain_off(self) -> None:
        with self._lk:
            Mic.close_sync(self)

    def _swap_to_helper(self, gen: int) -> bool:
        """Chiude il microfono normale SOLO se la conversazione e' ancora in corso (release() potrebbe averlo appena riaperto)."""
        with self._lk:
            if not self._alive(gen):
                return False
            Mic.close_sync(self)
            return True

    def start_sync(self) -> None:
        self.last_frame = time.monotonic()
        self._closing = False
        self._plain_on()
        if self.wanted:
            self.engage()

    # ---- filtro eco a richiesta
    def engage(self) -> None:
        """Inizia una conversazione: accende il filtro eco (ci mette ~1,5 s; nel frattempo si continua col microfono normale)."""
        self.wanted = True
        if self.loop is None or self._closing or time.monotonic() < self._skip_until:
            return
        if self.thread is not None and self.thread.is_alive() and self.proc is not None:
            return                                                          # gia' acceso (o in accensione)
        self._gen += 1
        self.thread = threading.Thread(target=self._run, args=(self._gen,), daemon=True, name="aria-vpmic")
        self.thread.start()

    def release(self) -> None:
        """Fine della conversazione: spegne il filtro eco e torna al microfono normale (a riposo costa quasi niente)."""
        self.wanted = False
        self._gen += 1                                                      # il thread del programma di supporto lo capisce e si chiude
        proc, self.proc = self.proc, None
        self.cleaned = False
        self._plain_on()
        if proc is not None:
            threading.Thread(target=self._kill, args=(proc,), daemon=True).start()    # (aspettare che esca fermerebbe Aria per un attimo)

    def _spawn(self) -> subprocess.Popen | None:
        if not os.path.exists(self.helper):
            return None
        try:
            return subprocess.Popen([self.helper], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        except OSError as e:
            log.warning("microfono con filtro eco: non parte (%s)", str(e)[:100])
            return None

    def _read_exact(self, proc: subprocess.Popen, n: int, first_timeout: float | None = None) -> bytes | None:
        import select
        buf = b""
        while len(buf) < n:
            if first_timeout is not None and not buf:
                r, _, _ = select.select([proc.stdout], [], [], first_timeout)
                if not r:
                    return None                                              # niente audio: il microfono e' bloccato
            d = proc.stdout.read(n - len(buf))
            if not d:
                return None
            buf += d
            first_timeout = None
        return buf

    def _alive(self, gen: int) -> bool:
        return not self._closing and gen == self._gen

    def _run(self, gen: int) -> None:
        fails = 0
        while self._alive(gen):
            t0 = time.monotonic()
            proc = self._spawn()
            frames = 0
            if proc is not None:
                self.proc = proc
                head = self._read_header(proc, gen)
                if head and head.startswith(b"READY"):
                    block = self.block * 2
                    while self._alive(gen):
                        data = self._read_exact(proc, block, self.first_frame_timeout if frames == 0 else None)
                        if data is None or not self._alive(gen):
                            break
                        if frames == 0:
                            if not self._swap_to_helper(gen):                # il filtro manda audio: da qui in poi il microfono normale non serve (e non si doppia)
                                break
                            self.cleaned = True
                            log.info("microfono con filtro eco del Mac attivo")
                        frames += 1
                        self.last_frame = time.monotonic()
                        frame = np.frombuffer(data, dtype=np.int16).copy().view(Frame)
                        frame.adc = None                                   # (l'eco e' gia' tolto: niente orario per il nostro filtro)
                        if self.loop is not None:
                            self.loop.call_soon_threadsafe(self._put, frame)
                self._kill(proc)
                if self.proc is proc:
                    self.proc = None
            if not self._alive(gen):
                return                                                      # release()/close_sync(): ci pensano loro al microfono normale
            self.cleaned = False
            self._plain_on()                                                # (il filtro e' caduto: intanto si torna al microfono normale)
            fails = 0 if (frames and time.monotonic() - t0 > 8.0) else fails + 1
            if proc is None or fails >= 2:
                log.warning("microfono con filtro eco non disponibile (%s): resto sul microfono normale per un po' (l'interruzione a voce sulle casse sara' meno pronta)",
                            "il programma manca" if proc is None else "non manda audio" if not frames else "si ferma di continuo")
                self._skip_until = time.monotonic() + self.retry_after
                return
            log.info("microfono con filtro eco: si e' fermato%s, lo riapro", "" if frames else " senza mandare audio")
            time.sleep(0.4 * fails)

    def _read_header(self, proc: subprocess.Popen, gen: int, timeout: float = 15.0) -> bytes | None:
        """La riga «READY» arriva in ~1,5 s (la prima volta, con la richiesta del permesso, anche di piu')."""
        import select
        end = time.monotonic() + timeout
        line = b""
        while time.monotonic() < end and self._alive(gen):
            r, _, _ = select.select([proc.stdout], [], [], 0.2)
            if r:
                ch = proc.stdout.read(1)
                if not ch:
                    return None
                line += ch
                if ch == b"\n":
                    return line
            elif proc.poll() is not None:
                return None
        return None

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            if proc.stdin:
                proc.stdin.close()                                          # il programma esce da solo quando stdin si chiude
        except Exception:                                                   # noqa: BLE001
            pass
        try:
            proc.wait(timeout=1.5)
        except Exception:                                                   # noqa: BLE001
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:                                               # noqa: BLE001
                pass
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:                                                   # noqa: BLE001
            pass

    def close_sync(self) -> None:
        self._closing = True
        self._gen += 1
        proc, self.proc = self.proc, None
        if proc is not None:
            self._kill(proc)
        self.cleaned = False
        self._plain_off()


class Speaker:
    def __init__(self, device=None, rate: int = 16000, volume: float = 0.9):
        self.device, self.rate, self.volume = device, rate, volume
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.level = 0.0
        self.stream = None
        self.ring = np.zeros(int(rate * 10), dtype=np.int16)           # gli ultimi 10 s di quello che e' uscito dalle casse (il «riferimento» per togliere l'eco dal microfono)
        self.out_count = 0                                             # campioni scritti nell'anello, da sempre
        self.played_samples = 0                                        # campioni di voce (non di silenzio) usciti finora
        self.queued_samples = 0                                        # campioni di voce messi in coda finora
        self.texts: deque = deque(maxlen=64)                           # (fine in campioni, testo) di ogni frase messa in coda: dice COSA sta dicendo adesso
        self.captions: deque = deque(maxlen=64)                        # (inizio, fine, testo): serve a mostrare i sottotitoli A TEMPO con la voce
        self.next_text: str | None = None                              # il testo della prossima play() (lo imposta chi la chiama)
        self.blocks: deque = deque(maxlen=512)                         # (orario in cui il blocco esce dalle casse, numero del suo primo campione)
        self._quiet = 0                                                # campioni di silenzio di fila (per fermare l'uscita quando non si parla)
        self.idle_stop_s = 2.5

    def ref_at(self, t: float | None, n: int = 512, rate: int = 16000):
        """Quello che le casse suonavano negli `n` campioni (a `rate`) a partire dall'orario `t` (stesso orologio di Frame.adc), come float -1..1; None se non c'e'."""
        if t is None or not self.blocks:
            return None
        blocks = list(self.blocks)
        dac, n0 = next((b for b in reversed(blocks) if b[0] <= t), blocks[0])
        L, step = len(self.ring), self.rate / rate
        p0 = n0 + (t - dac) * self.rate                                # posizione (in campioni dell'uscita) di `t`
        p1 = p0 + n * step
        if p0 < self.out_count - L + 4 * self.rate / 16 or p1 + 2 > self.out_count or p0 < 0:
            return None
        i0 = int(np.floor(p0)) - 1
        idx = np.arange(i0, int(np.ceil(p1)) + 3) % L
        seg = self.ring[idx].astype(np.float32) / 32768.0
        pos = (p0 + np.arange(n) * step) - i0
        return np.interp(pos, np.arange(len(seg)), seg).astype(np.float32)

    def start(self) -> None:
        import sounddevice as sd

        def cb(outdata, frames, time_info, status):
            n = frames * 2
            with self.lock:
                chunk = bytes(self.buf[:n])
                del self.buf[:n]
            pcm = np.frombuffer(chunk, dtype=np.int16)
            out = np.zeros(frames, dtype=np.int16)
            out[: len(pcm)] = pcm
            outdata[:, 0] = out
            self.played_samples += len(pcm)
            self._quiet = 0 if len(pcm) else self._quiet + frames
            try:
                n0, L = self.out_count, len(self.ring)
                self.ring[np.arange(n0, n0 + frames) % L] = out
                self.blocks.append((float(time_info.outputBufferDacTime), n0))
                self.out_count = n0 + frames
            except Exception:                                    # noqa: BLE001
                pass
            self.level = float(min(1.0, np.sqrt(np.mean((out.astype(np.float32) / 32768.0) ** 2)) * 5.0))
            if self._quiet >= self.idle_stop_s * self.rate:                  # niente da dire da un po': l'uscita si ferma (resta aperta, riparte alla prossima frase)
                raise sd.CallbackStop

        self.stream = sd.OutputStream(device=resolve_device(self.device, "output"), samplerate=self.rate, channels=1,
                                      dtype="int16", callback=cb, blocksize=512)
        self._quiet = 0
        self.stream.start()

    def _wake_output(self) -> None:
        """L'uscita audio gira solo mentre Aria parla (e qualche secondo dopo): una uscita sempre aperta che suona silenzio tiene sveglio l'audio del Mac e consuma batteria
        (misurato: ~7 % di un core in coreaudiod + l'hardware dell'audio mai a riposo)."""
        st = self.stream
        if st is not None and not st.active:
            try:
                self._quiet = 0
                try:
                    st.stop()                                                # (uno stream fermato dal callback va «chiuso» con stop() prima di poter ripartire)
                except Exception:                                            # noqa: BLE001
                    pass
                st.start()
            except Exception as e:                                           # noqa: BLE001
                log.warning("uscita audio: non riparte (%s)", str(e)[:100])

    def play(self, pcm: np.ndarray, sr: int) -> None:
        pcm = resample(pcm, sr, self.rate)
        if self.volume != 1.0:
            pcm = (pcm.astype(np.float32) * self.volume).astype(np.int16)
        with self.lock:
            start = self.queued_samples
            self.buf += pcm.tobytes()
            self.queued_samples += len(pcm)
            if self.next_text:
                self.texts.append((self.queued_samples, self.next_text))
                self.captions.append((start, self.queued_samples, self.next_text))
        self.next_text = None
        self._wake_output()

    def recent_text(self, back_s: float = 2.4) -> str:
        """Le frasi che si stanno sentendo adesso dalle casse (quelle degli ultimi `back_s` secondi e di quello che sta per uscire): e' l'eco che puo' rientrare nel microfono."""
        lo, hi = self.played_samples - int(back_s * self.rate), self.played_samples + int(0.25 * self.rate)
        out, start = [], 0
        for end, text in list(self.texts):
            if end > lo and start < hi:
                out.append(text)
            start = end
        return " ".join(out)

    def stop(self) -> None:
        with self.lock:
            self.buf.clear()
            self.queued_samples = self.played_samples
            self.texts.clear()
            self.captions.clear()
        self.level = 0.0

    @property
    def playing(self) -> bool:
        with self.lock:
            busy = len(self.buf) > 0
        if busy:
            self._wake_output()                                              # (se l'uscita si e' fermata proprio mentre arrivava una frase, riparte qui)
        return busy

    async def wait_done(self, poll: float = 0.03) -> None:
        while self.playing:
            await asyncio.sleep(poll)
        await asyncio.sleep(0.12)                                # lascia finire l'ultimo blocco
        self.level = 0.0

    def close(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()
