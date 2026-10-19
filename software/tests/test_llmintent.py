"""Decodificare una richiesta con il chatbot: formato, strumenti ammessi e, soprattutto, niente dati inventati."""
from aria import llmintent as L
from aria.textutil import ToolCall


def test_parse_accepts_one_line_and_rejects_everything_else():
    assert L.parse("PROMEMORIA | domani alle nove chiamare Marco") == ToolCall("PROMEMORIA", "domani alle nove chiamare Marco")
    assert L.parse("MUSICA | track:rilassante\nspiegazione inutile") == ToolCall("MUSICA", "track:rilassante")
    assert L.parse("LISTA | della spesa|le uova") == ToolCall("LISTA", "della spesa|le uova")
    assert L.parse("`VOLUME | up`") == ToolCall("VOLUME", "up") and L.parse("Risposta: AGENDA | domani") == ToolCall("AGENDA", "domani")
    assert L.parse("NESSUNO") is None and L.parse("") is None and L.parse("Certo! Ecco il promemoria") is None
    assert L.parse("SCORCIATOIA | Buonanotte") is None and L.parse("CANCELLA | tutto") is None            # solo gli strumenti ammessi (niente scorciatoie, niente file)


def test_arguments_must_be_made_of_what_the_user_said():
    say = L.grounded
    assert say(ToolCall("PROMEMORIA", "domani alle nove chiamare Marco"), "ricordami domani alle 9 di chiamare Marco")        # «9» = «nove»
    assert say(ToolCall("PROMEMORIA", "domani"), "prova a creare un promemoria per domani")
    assert say(ToolCall("TIMER", "dieci minuti | pasta"), "metti un timer di 10 minuti per la pasta")
    assert say(ToolCall("VOLUME", "set:40"), "metti il volume a quaranta") and say(ToolCall("VOLUME", "up"), "più forte")
    assert say(ToolCall("MUSICA", "track:rilassante"), "mettimi della musica rilassante")
    assert not say(ToolCall("PROMEMORIA", "domani alle 10 prendere il caffè"), "prova a creare un promemoria per domani")            # orario e motivo inventati
    assert not say(ToolCall("EVENTO", "6 ottobre 2026 dentista"), "metti il dentista in calendario domani")                          # una data che nessuno ha detto
    assert not say(ToolCall("NOTA", "ricordati di chiamare Luca"), "segna una nota")


def test_the_decoder_can_route_to_the_everyday_tools_but_not_for_stories():
    from aria import llmintent
    from aria.textutil import ToolCall
    assert llmintent.parse("DATA | San Valentino") == ToolCall("DATA", "San Valentino")
    assert llmintent.parse("AIUTO |").name == "AIUTO" and llmintent.parse("CASO | dado").name == "CASO" and llmintent.parse("CONVERTI | 5 once in grammi").name == "CONVERTI"
    assert llmintent.plausible(ToolCall("DATA", "Quanti giorni mancano a San Valentino"), "Quanti giorni mancano a San Valentino")
    assert llmintent.plausible(ToolCall("CASO", "x"), "Fammi una scelta tra tre colori a caso")
    assert not llmintent.plausible(ToolCall("CASO", "x"), "Ho tirato un dado ieri e ho vinto")
    assert not llmintent.plausible(ToolCall("CONVERTI", "x"), "Ho convertito tutto in miglia")
