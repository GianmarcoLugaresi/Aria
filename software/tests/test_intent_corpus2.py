"""Frasi non previste dalle regole (scritte a parte, tests/intent_corpus2.py): ogni richiesta va allo strumento giusto, e la chiacchiera non fa partire niente."""
import pytest

from intent_corpus2 import FILES, NEG2, POS2
from aria import intent


@pytest.mark.parametrize("text,tools,parts", POS2)
def test_the_request_goes_to_the_right_tool(text, tools, parts):
    c = intent.detect(text, FILES, screen_on=True)
    assert c is not None and c.name in tools, (text, c)
    assert all(p in c.arg.lower() for p in parts), (text, c.arg, parts)


@pytest.mark.parametrize("text", NEG2)
def test_chitchat_starts_nothing(text):
    assert intent.detect(text, FILES, screen_on=True) is None, text


def test_unknown_actions_are_refused_honestly_with_the_right_kind():
    cases = {"Stampa questo documento": "print", "Scarica Firefox": "download", "Riavvia il computer": "system", "Attiva il bluetooth": "system", "Fai una foto": "media",
             "Registra lo schermo": "media", "Condividi questo con Marco": "share", "Cancella il file della spesa": "files", "Chiudi Safari": "app", "Chiudi la finestra": "app",
             "Fai un bonifico a Marco": "money", "Scrivi un messaggio su WhatsApp a Giulia": "message", "Chiama mia madre": "call", "Accendi la luce": "home", "Ordina una pizza": "buy"}
    for text, kind in cases.items():
        c = intent.detect(text)
        assert c is not None and c.name == "NON_SO" and c.arg == kind, (text, c)
    assert intent.detect("scrivimi una lettera di auguri").name == "SCRIVI" and intent.detect("butta il file nella cartella") is None      # scrivere e salvare restano possibili


def test_live_questions_are_searched_not_invented():
    for t in ("Chi ha vinto ieri la partita?", "Com'è il traffico verso Milano?", "A che ora chiude il supermercato?", "Quanto costa oggi il bitcoin?", "Orari dei treni per Roma"):
        assert intent.detect(t).name == "CERCA", t


def test_the_decoder_gate_lets_requests_through_and_keeps_chat_out():
    assert intent.request_like("Vorrei che tu alzassi il livello audio") and intent.request_like("Domani a quest'ora, chiama Mario")
    for t in ("Mi chiamo Mario e domani ho un esame di analisi", "Ho sentito una canzone bellissima ieri", "La musica classica mi rilassa", "Perché il cielo è azzurro?"):
        assert not intent.request_like(t), t
