"""Cancellazione dell'eco: toglie dal microfono la voce di Aria (che esce dalle casse del Mac e rientra) per sentire l'utente che la interrompe.

Aria sa esattamente cosa sta riproducendo (il «riferimento»). Il microfono sente quel suono cambiato dalla stanza (ritardo, rimbalzi, un po' di distorsione): un filtro adattivo
(NLMS a blocchi nel dominio della frequenza, PBFDAF) impara come la stanza cambia il suono e lo sottrae. Quello che resta e' la voce dell'utente (piu' un po' di eco residua).
Il filtro impara mentre Aria parla e si TIENE tra una risposta e l'altra (la stanza e' sempre la stessa): all'interruzione e' gia' «allenato».
"""
from __future__ import annotations

import numpy as np


class EchoCanceller:
    def __init__(self, block: int = 512, parts: int = 16, mu: float = 0.35, eps: float = 1e-6):
        self.B, self.K, self.mu, self.eps = block, parts, mu, eps
        self.W = np.zeros((parts, block + 1), dtype=np.complex128)           # il filtro, a pezzi, nel dominio della frequenza
        self.X = np.zeros((parts, block + 1), dtype=np.complex128)           # gli ultimi spettri del riferimento
        self.xbuf = np.zeros(2 * block)
        self.P = np.full(block + 1, eps)                                      # potenza del riferimento (per normalizzare il passo)
        self.conv = 1.0                                                       # quanta parte del microfono resta dopo il filtro (1 = filtro non ancora allenato)
        self.resets = 0

    def soft_reset(self) -> None:
        """Per ricominciare dopo una pausa (tra una risposta e l'altra): la storia del riferimento e' vecchia, il filtro (la stanza) no."""
        self.X[:] = 0
        self.xbuf[:] = 0

    def reset(self) -> None:
        self.W[:] = 0
        self.X[:] = 0
        self.xbuf[:] = 0
        self.conv = 1.0

    def process(self, mic: np.ndarray, ref: np.ndarray, adapt: bool = True) -> np.ndarray:
        """mic e ref: un blocco (B campioni, float -1..1) ciascuno, allineati nel tempo. Restituisce il microfono senza l'eco."""
        B = self.B
        self.xbuf = np.concatenate([self.xbuf[B:], ref])
        Xf = np.fft.rfft(self.xbuf)
        self.X = np.roll(self.X, 1, axis=0)
        self.X[0] = Xf
        y = np.fft.irfft((self.W * self.X).sum(axis=0))[B:]
        e = mic - y
        ref_pow = float(np.mean(ref * ref))
        mic_pow = float(np.mean(mic * mic))
        e_pow = float(np.mean(e * e))
        if not np.isfinite(e_pow) or (ref_pow > 1e-8 and e_pow > 100.0 * mic_pow + 1e-4):     # divergenza (il residuo e' MOLTO piu' forte dell'ingresso): si riparte da zero invece di sparare rumore
            self.W[:] = 0
            self.resets += 1
            return mic.copy()
        if adapt and ref_pow > 1e-8:
            # (niente rilevatore di «doppio parlato»: provato, scambiava ogni cambio di parola di Aria per l'utente e il filtro non imparava piu'; la voce dell'utente dura poco
            # rispetto al tempo di apprendimento e la guardia di divergenza qui sopra basta)
            step = self.mu
            r = float(np.mean(e * e)) / (mic_pow + self.eps)
            self.conv = 0.95 * self.conv + 0.05 * min(r, 1.0)                     # quanta parte del microfono resta dopo il filtro (per i log)
            self.P = 0.9 * self.P + 0.1 * (np.abs(self.X) ** 2).sum(axis=0)
            E = np.fft.rfft(np.concatenate([np.zeros(B), e]))
            G = np.conj(self.X) * E / (self.P + self.eps)
            g = np.fft.irfft(G, axis=1)                                       # vincolo di causalita': si tiene solo la prima meta'
            g[:, B:] = 0.0
            self.W += step * np.fft.rfft(g, axis=1)
        return e
