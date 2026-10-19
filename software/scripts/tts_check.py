"""La voce «mangia» delle parole? Sintetizza frasi vere con Pocket TTS, le riconosce con Whisper e dice quali parole si perdono.

    python scripts/tts_check.py [--voice anna] [--stt mlx-community/whisper-large-v3-turbo-q4] [frase ...]

Non e' un giudizio sulla bellezza della voce: dice solo se tutto il testo e' davvero pronunciato (e se le parole perse sono all'inizio o alla fine).
"""
import argparse
import asyncio
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aria.audio import resample                         # noqa: E402
from aria.speech import speechify                       # noqa: E402
from aria.stt import MLXWhisperSTT                      # noqa: E402
from aria.tts import PocketTTS                          # noqa: E402

SENTENCES = [
    "Come fa a vedere un dito da dentro un computer?", "Sarà un dito magico!", "Ah, ecco Mario! Stai cercando di capire come funziona il mondo, eh?",
    "Mi fai venire voglia di fare una partita a scacchi!", "Eccomi di nuovo Mario.", "Ciao Mario, dimmi cosa ti passa per la testa!", "Buonasera Mario!",
    "Beh, dimmi Mario, come stai stamattina?", "Fantastico sentire questo! La giornata sembra già promettere meglio, no?", "Sì, dimmi.",
    "Ciao Mario! Che bello averti qui oggi.", "Direi che va tutto sommato bene, eh?", "Capita, capita. Allora, dimmi pure quello che ti va.",
    "Mmm, un basilico che si arrende!", "Sembra proprio che gli manchi un po' di sole, forse?", "Lampadina puntata... che tenerezza!",
    "Spero che questo aiuti il tuo basilico a riprendersi.", "Caspita Mario, non ho mai visto un orto così originale!", "Stai cercando di fare un'insalata?",
    "Ah, scusa Mario. Va benissimo così!", "Almeno non hai bisogno di annaffiarlo.", "Mario, a volte le piante hanno bisogno di un po' di luce artificiale anche!",
    "Ma di niente.", "Certo che sì, Mario! Almeno non si lamenterà più della scarsa illuminazione.", "Beh, il sole è meglio, ma una lampadina può fare al caso suo!",
    "Ti ricordo che domani alle nove hai il dentista.", "Va bene, ti ricorderò di chiamare il commercialista domani alle nove.", "Che bella notizia, trenta all'esame!",
]


FILLERS = {"ah", "beh", "mmm", "mmh", "eh", "boh", "uhm", "ehm", "oh", "ehi", "mario", "marrio"}      # Whisper non le scrive / il nome lo scrive come gli pare: non contano come parole perse


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s).split()


def align(ref: list[str], hyp: list[str]):
    """Parole del testo che mancano nel riconosciuto (distanza di edit con backtrace)."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    i, j, missing, wrong = n, m, [], []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] != hyp[j - 1]:
                wrong.append((i - 1, ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            missing.append((i - 1, ref[i - 1])); i -= 1
        else:
            j -= 1
    return missing[::-1], wrong[::-1]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="anna")
    ap.add_argument("--stt", default="mlx-community/whisper-large-v3-turbo-q4")
    ap.add_argument("--language", default="italian", help="italian (6 strati, leggera) oppure italian_24l (24 strati, 3x piu' pesante)")
    ap.add_argument("--frames", type=int, help="frames_after_eos di Pocket TTS (di solito 3-5)")
    ap.add_argument("--no-guard", action="store_true", help="senza il controllo della fine frase (come Pocket TTS di fabbrica)")
    ap.add_argument("--temp", type=float, help="temperatura di Pocket TTS (0,3 e' il valore di fabbrica)")
    ap.add_argument("--eos", type=float, help="eos_threshold di Pocket TTS (-4.0 e' il valore di fabbrica)")
    ap.add_argument("sentences", nargs="*")
    args = ap.parse_args()
    tts = PocketTTS({"language": args.language, "voice": args.voice, "frames_after_eos": args.frames, "eos_threshold": args.eos, "temperature": args.temp, "eos_guard": not args.no_guard})
    stt = MLXWhisperSTT({"model": args.stt, "prompt": False})
    tot_ref = tot_missing = edge_loss = defective = 0
    for text in (args.sentences or SENTENCES):
        pcm, sr = await tts.synthesize(speechify(text))
        pcm16 = resample(pcm, sr, 16000)
        sil = np_zeros = __import__("numpy").zeros(8000, dtype="int16")
        heard = await stt.transcribe(__import__("numpy").concatenate([sil, pcm16, sil]), 16000)
        ref, hyp = [w for w in words(speechify(text)) if w not in FILLERS], [w for w in words(heard) if w not in FILLERS]
        missing, wrong = align(ref, hyp)
        tot_ref += len(ref); tot_missing += len(missing)
        edge = [w for i, w in missing if i <= 1 or i >= len(ref) - 2] + [r for i, r, h in wrong if i >= len(ref) - 2]
        edge_loss += len(edge)
        bad = [w for _, w in missing] + [f"{r}->{h}" for i, r, h in wrong if i >= len(ref) - 2]
        flag = "  <-- DIFETTI: " + ", ".join(bad) if bad else ""
        defective += 1 if bad else 0
        print(f"{len(pcm) / sr:4.1f}s | {text[:60]:60} | sentito: {heard.strip()[:70]}{flag}")
    print(f"\nparole del testo: {tot_ref} | perse {tot_missing} ({100 * tot_missing / tot_ref:.1f}%) | difetti a inizio/fine frase: {edge_loss} | frasi con difetti: {defective}/{len(args.sentences or SENTENCES)}")


asyncio.run(main())
