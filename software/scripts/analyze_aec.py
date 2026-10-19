"""Come va la cancellazione dell'eco nella vita vera? Legge ~/.aria/aec_ultima.npz (microfono, riferimento e residuo dell'ULTIMA risposta che Aria ha detto,
salvati da conversation._save_aec_debug) e dice: quanto ritardo c'e' tra casse e microfono, quanta parte dell'eco e' «lineare» (si puo' togliere), quanto toglie il filtro
com'e' adesso e se un'altra taratura andrebbe meglio.

    python scripts/analyze_aec.py [percorso.npz]

Si lancia dopo aver fatto dire ad Aria una risposta lunga (almeno 10 secondi) con le casse del Mac. Non esce niente dal Mac."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria.aec import EchoCanceller  # noqa: E402

B = 512
SR = 16000


def db(x: float) -> float:
    return 10 * np.log10(max(x, 1e-12))


def erle(mic: np.ndarray, res: np.ndarray, skip: int = 20) -> float:
    m, r = mic[skip * B:], res[skip * B:]
    return db(np.mean(m * m)) - db(np.mean(r * r))


def delay_ms(mic: np.ndarray, ref: np.ndarray) -> tuple[float, float]:
    """Ritardo (ms) con la correlazione massima e quanto e' netto il picco (1 = molto)."""
    n = 1 << int(np.ceil(np.log2(len(mic) + len(ref))))
    c = np.fft.irfft(np.fft.rfft(mic, n) * np.conj(np.fft.rfft(ref, n)), n)
    lags = np.concatenate([np.arange(0, 1 * SR), np.arange(-SR // 4, 0)])          # da -250 ms a +1 s
    vals = np.abs(c[lags])
    i = int(np.argmax(vals))
    return 1000.0 * lags[i] / SR, float(vals[i] / (np.median(vals) * 12 + 1e-12))           # >1: il picco spicca almeno 12 volte sul resto


def coherence(mic: np.ndarray, ref: np.ndarray, shift: int = 0) -> float:
    """Media (0-1) di quanto il microfono dipende linearmente dal riferimento (spostato del ritardo) nella banda della voce (300-4000 Hz)."""
    if shift > 0:
        ref = np.concatenate([np.zeros(shift), ref])[:len(mic)]
    nper = 4096
    nseg = (min(len(mic), len(ref)) - nper) // (nper // 2)
    if nseg < 8:
        return 0.0
    w = np.hanning(nper)
    Sxx = Syy = Sxy = 0
    for k in range(nseg):
        a = ref[k * nper // 2:k * nper // 2 + nper] * w
        b = mic[k * nper // 2:k * nper // 2 + nper] * w
        A, Bf = np.fft.rfft(a), np.fft.rfft(b)
        Sxx = Sxx + np.abs(A) ** 2
        Syy = Syy + np.abs(Bf) ** 2
        Sxy = Sxy + A * np.conj(Bf)
    coh = np.abs(Sxy) ** 2 / (Sxx * Syy + 1e-20)
    f = np.fft.rfftfreq(nper, 1 / SR)
    band = (f > 300) & (f < 4000)
    return float(np.sum((coh * Syy)[band]) / (np.sum(Syy[band]) + 1e-20))                # pesata dall'energia: i punti senza segnale non contano


def run(mic: np.ndarray, ref: np.ndarray, shift: int = 0, parts: int = 16, mu: float = 0.35) -> np.ndarray:
    aec = EchoCanceller(B, parts, mu)
    if shift > 0:
        ref = np.concatenate([np.zeros(shift), ref])[:len(mic)]
    elif shift < 0:
        mic = np.concatenate([np.zeros(-shift), mic])[:len(ref)]
    n = min(len(mic), len(ref)) // B
    out = np.zeros(n * B)
    for i in range(n):
        out[i * B:(i + 1) * B] = aec.process(mic[i * B:(i + 1) * B], ref[i * B:(i + 1) * B])
    return out


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.aria/aec_ultima.npz")
    if not os.path.exists(path):
        print(f"Non c'e' {path}: fai dire ad Aria una risposta lunga (10+ secondi) con le casse del Mac e riprova.")
        return 1
    d = np.load(path, allow_pickle=True)
    mic, ref, res = (d[k].astype(np.float64) for k in ("mic", "ref", "res"))
    secs = len(mic) / SR
    print(f"{secs:.1f} s di audio. Livello microfono {db(np.mean(mic ** 2)):.0f} dB, riferimento {db(np.mean(ref ** 2)):.0f} dB, residuo {db(np.mean(res ** 2)):.0f} dB")
    print(f"Il filtro com'e' ora toglie {erle(mic, res):.1f} dB (15 dB = molto bene, 3 dB = quasi niente)")
    dl, peak = delay_ms(mic, ref)
    print(f"Ritardo casse→microfono: {dl:.0f} ms (picco {'netto' if peak > 1 else 'debole: forse non ce eco lineare, o il microfono ha una elaborazione propria'})")
    print(f"Coerenza lineare nella banda della voce: {coherence(mic, ref, max(0, int(dl * SR / 1000))):.2f} (1 = tutto eco lineare, 0 = niente da togliere con un filtro)")
    best = (-99.0, None)
    for shift in (0, int(dl * SR / 1000) - 64, int(dl * SR / 1000) - 256, int(dl * SR / 1000)):
        for parts, mu in ((16, 0.35), (32, 0.35), (16, 0.6), (32, 0.6), (16, 0.15)):
            try:
                r = run(mic, ref, max(0, min(shift, 4 * B)), parts, mu)
            except Exception:                                        # noqa: BLE001
                continue
            e = erle(mic[:len(r)], r)
            if e > best[0]:
                best = (e, (shift, parts, mu))
    print(f"Meglio rifacendo il calcolo qui: {best[0]:.1f} dB con anticipo={best[1][0]} campioni, partizioni={best[1][1]}, mu={best[1][2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
