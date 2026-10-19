"""Il riconoscimento vocale integrato nel Mac (programma di supporto Swift) e la sua scelta dalle Impostazioni."""
import asyncio
import os
import stat
import sys

import numpy as np
import pytest

from aria import models, profiles as P
from aria.stt import AppleSTT, make_stt


def fake_helper(tmp_path, reply="R\tCiao Aria"):
    p = tmp_path / "aria-apple-stt"
    p.write_text(f"#!{sys.executable}\nimport sys\nprint('READY', flush=True)\nfor line in sys.stdin:\n    print({reply!r}.replace('\\\\t', '\\t'), flush=True)\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def speech(n=16000):
    return (np.sin(np.linspace(0, 600, n)) * 3000).astype(np.int16)


async def test_apple_stt_talks_to_the_helper_and_cleans_the_text(tmp_path):
    stt = make_stt({"kind": "apple", "helper": fake_helper(tmp_path)})
    assert isinstance(stt, AppleSTT)
    await stt.warmup()
    assert await stt.transcribe(speech(), 16000) == "Ciao Aria"
    assert await stt.transcribe(speech(), 16000) == "Ciao Aria"                       # lo stesso programma risponde a piu' frasi
    stt.close()


async def test_apple_stt_without_the_helper_explains_what_to_do(tmp_path):
    stt = AppleSTT({"helper": str(tmp_path / "non-esiste")})
    with pytest.raises(RuntimeError, match="install.sh"):
        await stt.transcribe(speech(), 16000)


async def test_apple_stt_drops_whisper_style_hallucinations(tmp_path):
    stt = AppleSTT({"helper": fake_helper(tmp_path, "R\tSottotitoli e revisione a cura di QTSS")})
    assert await stt.transcribe(speech(), 16000) == ""
    stt.close()


def test_apple_is_a_choice_in_settings_only_when_the_helper_exists(tmp_path, monkeypatch):
    cfg = {"brains": [{"name": "mac", "stt": {"kind": "mlx-whisper", "model": "mlx-community/whisper-small-mlx-q4"}, "llm": {"kind": "mlx-lm", "model": "x/y"}}]}
    settings = {"profile": P.CUSTOM, "stt_model": P.APPLE_STT}
    monkeypatch.setenv("ARIA_APPLE_STT", str(tmp_path / "manca"))
    import copy
    assert P.apply_settings(copy.deepcopy(cfg), settings)["brains"][0]["stt"]["kind"] == "mlx-whisper"        # senza programma di supporto: resta quello di prima
    monkeypatch.setenv("ARIA_APPLE_STT", fake_helper(tmp_path))
    assert P.apply_settings(copy.deepcopy(cfg), settings)["brains"][0]["stt"] == {"kind": "apple"}
    assert P.stt_repo({"kind": "apple"}) == P.APPLE_STT and P.valid_repo(P.APPLE_STT)
    assert models.stt_installed({"kind": "apple"}) and any(c["repo"] == P.APPLE_STT for c in P.STT_CATALOG)
    assert P.estimate_ram_gb(0, 4.7) < P.estimate_ram_gb(None, 4.7)                                           # Apple non pesa sulla RAM di Aria


def test_the_mac_speech_engine_is_never_offered_for_removal():
    entries = [{"repo": "a/whisper", "installed": True}, {"repo": P.APPLE_STT, "installed": True}]
    models._remove_flags(entries, "repo", "a/whisper")
    assert entries[1]["removable"] is False and entries[1]["block"] == "integrato nel Mac" and entries[0]["block"] == "in uso"


async def test_the_router_treats_apple_as_a_local_engine_not_as_a_server_to_ping(tmp_path):
    """Bug dal vivo: «apple» non era tra i motori locali, il router lo cercava come server (base_url vuoto) e diceva «nessun riconoscimento vocale disponibile»."""
    from aria.main import factory
    from aria.router import Router
    helper = fake_helper(tmp_path)
    router = Router([{"name": "mac", "stt": {"kind": "apple", "helper": helper}}], factory)
    assert await router.transcribe(speech(), 16000) == "Ciao Aria"
    for o in router.objects("stt"):
        o.close()


async def test_the_answer_to_a_cancelled_request_is_not_given_to_the_next_one(tmp_path):
    p = tmp_path / "aria-apple-stt"
    p.write_text(f"#!{sys.executable}\nimport sys, time\nprint('READY', flush=True)\nn = 0\nfor line in sys.stdin:\n    n += 1\n    time.sleep(0.4 if n == 1 else 0)\n    print('R\\tfrase', n, flush=True)\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    stt = AppleSTT({"helper": str(p)})
    await stt.warmup()
    t = asyncio.create_task(stt.transcribe(speech(), 16000))
    await asyncio.sleep(0.15)
    t.cancel()                                                                       # l'interruzione a voce ha chiuso il controllo mentre il programma lavorava
    await asyncio.gather(t, return_exceptions=True)
    assert await stt.transcribe(speech(), 16000) == "frase 2"                        # e la frase dopo non riceve il testo della prima
    stt.close()


def test_spoken_stumbles_the_recognizer_writes_down_are_removed_but_emphasis_stays():
    from aria.stt import clean_transcript
    assert clean_transcript("Come come cavolo faccio a crearli, perché non voglio farli già già pronti.") == "Come cavolo faccio a crearli, perché non voglio farli già pronti."
    assert clean_transcript("E mi diresti la ricetta di degli gnocchi alla romana") == "E mi diresti la ricetta degli gnocchi alla romana"
    assert clean_transcript("No, ti sto chiedendo se se va bene.") == "No, ti sto chiedendo se va bene."
    assert clean_transcript("Sì, dico di mettere degli eventi, mettere degli eventi.") == "Sì, dico di mettere degli eventi."
    assert clean_transcript("Ti sto ti sto chiedendo") == "Ti sto chiedendo"
    assert clean_transcript("Molto molto buono") == "Molto molto buono" and clean_transcript("No no, non quello") == "No no, non quello"


def test_math_written_with_symbols_by_the_recognizer_is_still_a_calculation_but_dates_and_times_are_left_alone():
    from aria import intent
    from aria.intent import ToolCall
    for text, expr in (("Quanto fa 120 ÷ 4?", "120/4"), ("Quanto fa 7 × 8?", "7*8"), ("quanto fa 5 + 3", "5+3"), ("Quanto fa 120 / 4", "120/4"),
                       ("quanto fa 3 - 1", "3-1"), ("Quanto fa il 20% di 350?", "350*20/100"), ("quanto fa 9 x 6", "9*6"), ("quanto fa 100 : 5", "100/5")):
        assert intent.detect(text, []) == ToolCall("CALCOLA", expr), text
    assert intent.spoken_math("ricordami il 10/10 di chiamare Mario") == "ricordami il 10/10 di chiamare Mario"
    assert intent.spoken_math("Metti la sveglia alle 10:30") == "Metti la sveglia alle 10:30"
    assert intent.spoken_math("tra 3-4 giorni") == "tra 3-4 giorni"


def test_names_the_recognizer_wrote_by_ear_come_back_from_the_things_aria_knows():
    from aria.lexicon import Lexicon
    lex = Lexicon()
    lex.add_all(["Mario", "Roma"], loose=True)
    lex.add_all(["Somnium", "Ricetta"])
    assert lex.correct("Mi chiamo Maria e abito a Roma.") == "Mi chiamo Mario e abito a Roma."
    assert lex.correct("Ciao Maria, come stai?") == "Ciao Mario, come stai?"
    assert lex.correct("Dov'è scritto Sonnium?") == "Dov'è scritto Somnium?"
    assert lex.correct("Maria è la mia amica") == "Maria è la mia amica"              # a inizio frase senza virgola non si tocca
    assert lex.correct("Ho incontrato Rivetta ieri") == "Ho incontrato Rivetta ieri"   # i nomi dei file valgono solo a suono uguale, non «quasi»
    assert lex.correct("la maria del mercato") == "la maria del mercato"             # senza maiuscola non e' un nome
    assert Lexicon().correct("Mi chiamo Maria") == "Mi chiamo Maria"
