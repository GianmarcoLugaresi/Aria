"""La «voce naturale» di Aria: Qwen3-TTS (0,6 miliardi di parametri, 4 bit, ~1,8 GB) in un processo a parte, come la visione: cosi' la sintesi gira in parallelo al chatbot
(un solo thread MLX nel processo principale li metterebbe in fila) e se qualcosa va storto si riavvia senza toccare il resto.

La voce e' sempre la stessa perche' parte da una registrazione di riferimento (voices/<nome>.wav + .txt): il modello la «continua» con il testo nuovo.
Protocollo (una riga JSON per richiesta su stdin / risposta su stdout):
    avvio:     python -m aria.qwentts_server '{"repo": ..., "ref_audio": ..., "ref_text": ..., "temperature": 0.8}'   ->   «READY»
    richiesta: {"id": 3, "text": "Ciao!", "seed": 7, "ref_audio": "(facoltativo: un'altra voce)", "ref_text": "..."}      ->   {"id": 3, "path": "/tmp/xxx.wav", "sec": 1.2}   oppure   {"id": 3, "error": "..."}
Il WAV e' mono 16 bit a 24 kHz. Si genera a pezzetti (streaming): il picco di memoria resta ~3 GB invece di ~7 GB."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import wave


# Il modello vuole il NOME della lingua («italian»): con un codice come «it» non lo riconosce, ignora l'indicazione e sceglie da solo, cioe' parla con un accento a caso (giapponese, cinese…)
LANGS = {"it": "italian", "en": "english", "fr": "french", "de": "german", "es": "spanish", "pt": "portuguese", "ru": "russian", "ja": "japanese", "ko": "korean", "zh": "chinese"}


def lang_name(code: str | None) -> str:
    c = (code or "it").strip().lower()
    return LANGS.get(c, c if c in LANGS.values() else "italian")


def _write_wav(path: str, pcm) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm.tobytes())


def main() -> None:
    cfg = json.loads(sys.argv[1])
    out_f = os.fdopen(os.dup(1), "w")                                # il canale del protocollo; le stampe delle librerie («Initialized encoder codebooks»…) vanno altrove
    sys.stdout = sys.stderr
    import numpy as np
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model

    mx.set_cache_limit(256 * 1024 * 1024)
    model = load_model(cfg["repo"])
    ref_audio, ref_text = cfg["ref_audio"], cfg["ref_text"]
    temperature = float(cfg.get("temperature", 0.8))

    def synth(text: str, seed: int | None, ref=None, lang: str = "it") -> "np.ndarray":
        if seed is not None:
            mx.random.seed(int(seed))
        max_tokens = int(len(text) * 1.7) + 40                       # 12,5 pezzi al secondo, ~13 caratteri al secondo di parlato: oltre questo il modello sta «inventando»
        chunks = [np.array(r.audio).reshape(-1) for r in model.generate(
            text=text, ref_audio=(ref or (ref_audio, ref_text))[0], ref_text=(ref or (ref_audio, ref_text))[1], lang_code=lang_name(lang), temperature=temperature, max_tokens=max_tokens, stream=True, streaming_interval=1.0)]
        if not chunks:
            raise RuntimeError("nessun audio")
        a = np.concatenate(chunks)
        return (np.clip(a, -1.0, 1.0) * 32767.0).astype(np.int16)

    for warm in ("Ciao.", "Va bene, ti ricordo io domani alle nove di chiamare il dentista.", "Per fare la pasta alla carbonara servono uova, pecorino, guanciale e pepe nero."):
        synth(warm, 1)                                               # i primi giri compilano i kernel (e per ogni lunghezza nuova): meglio farlo prima di READY
    out_f.write("READY\n")
    out_f.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            ref = (req["ref_audio"], req["ref_text"]) if req.get("ref_audio") else None             # (la voce puo' cambiare da una frase all'altra senza riavviare)
            pcm = synth(str(req["text"]), req.get("seed"), ref, str(req.get("lang") or "it"))
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="aria_qwen_")
            os.close(fd)
            _write_wav(path, pcm)
            out = {"id": rid, "path": path, "sec": round(len(pcm) / 24000, 2)}
        except Exception as e:                                       # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            out = {"id": rid, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        out_f.write(json.dumps(out) + "\n")
        out_f.flush()


if __name__ == "__main__":
    main()
