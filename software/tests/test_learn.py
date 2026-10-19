"""Impara solo da quello che dice l'utente: nome, citta', correzioni, fatti, impegni con data."""
import datetime as dt

from aria import learn as L

NOW = dt.datetime(2026, 10, 6, 12, 0)                 # un martedi'


def test_name_from_explicit_phrases_and_from_the_answer():
    assert L.parse_name("Mi chiamo Mario e domani ho un esame") == "Mario"
    assert L.parse_name("mi chiamo mario") == "Mario"
    assert L.parse_name("chiamami Gianni") == "Gianni"
    assert L.parse_name("Il mio nome è Anna Maria") == "Anna Maria"
    assert L.parse_name("Mario") is None                                    # senza domanda, una parola sola non e' un nome
    assert L.parse_name("Mario", expect=True) == "Mario"
    assert L.parse_name("allora io sono Mario", expect=True) == "Mario"
    assert L.parse_name("Marco Rossi", expect=True) == "Marco Rossi"
    assert L.parse_name_denial("non mi chiamo Luca") == "Luca"


def test_name_traps_do_not_fire():
    for t in ("sono stanco", "sono a casa", "ciao", "che ore sono?", "sono in ritardo", "mi chiamo stanco"):
        assert L.parse_name(t, expect=("?" not in t and t != "sono a casa")) is None, t
    assert L.parse_name("sono stanco") is None
    assert L.parse_name("questa è una frase lunga che non è un nome di nessuno", expect=True) is None


def test_city_from_phrases_and_from_the_answer():
    assert L.parse_city("abito a Milano") == "Milano"
    assert L.parse_city("Sono di Roma") == "Roma"
    assert L.parse_city("vivo a Reggio Emilia da tre anni") == "Reggio Emilia"
    assert L.parse_city("abito a San Giovanni in Persiceto") == "San Giovanni in Persiceto"
    assert L.parse_city("Milano", expect=True) == "Milano"
    assert L.parse_city("a Reggio Emilia", expect=True) == "Reggio Emilia"
    assert L.parse_city("Milano") is None
    assert L.parse_city_denial("non abito a Roma") == "Roma"


def test_city_traps_do_not_fire():
    for t in ("sono di fretta", "sono di buon umore", "sono di turno", "non lo so", "sto a casa"):
        assert L.parse_city(t, expect=True) is None, t
    assert L.parse_city("che tempo fa a Milano?", expect=True) is None       # una domanda non e' una risposta


def test_declines():
    assert L.is_decline("preferisco non dirtelo") and L.is_decline("non importa, dopo") and not L.is_decline("Mario")


def texts(s):
    return [(f.text, f.importance, f.kind) for f in L.extract(s, NOW)]


def test_facts_in_the_third_person_without_guessing_gender():
    assert texts("Ho un cane che si chiama Briciola") == [("Ha un cane che si chiama Briciola", 4, "fatto")]
    assert texts("Sono allergico alle noci") == [("Allergia: noci", 5, "fatto")]
    assert texts("Sono allergica alle noci") == [("Allergia: noci", 5, "fatto")]
    assert texts("Lavoro come infermiere, e domani sono stanco") == [("Lavora come infermiere", 4, "fatto")]
    assert texts("Mi piace il caffè lungo") == [("Apprezza il caffè lungo", 2, "fatto")]
    assert texts("non mi piace la pioggia") == [("Non apprezza la pioggia", 2, "fatto")]
    assert texts("Mia sorella si chiama Giulia") == [("Suo/sua sorella si chiama Giulia", 4, "fatto")]
    assert texts("Studio ingegneria a Bologna") == [("Studia ingegneria a Bologna", 4, "fatto")]
    assert texts("ho 30 anni")[0][0].startswith("Ha 30 anni") and texts("ho 300 anni") == []


def test_events_get_an_absolute_date():
    assert texts("domani ho un esame di analisi") == [("Mercoledì 7 ottobre: ha un esame di analisi", 3, "evento")]
    assert texts("Ho un esame domani") == [("Mercoledì 7 ottobre: ha un esame", 3, "evento")]
    assert texts("venerdì vado a Milano con Marco") == [("Venerdì 9 ottobre: va a Milano con Marco", 3, "evento")]
    f = L.extract("domani ho un esame", NOW)[0]
    assert dt.datetime.fromtimestamp(f.due).date() == dt.date(2026, 10, 7)


def test_questions_and_noise_teach_nothing():
    for t in ("che ore sono?", "oggi ho fame", "ho sonno", "come si chiama il tuo cane?", "", "ho un esame domani?"):
        assert texts(t) == [], t


def test_learns_projects_diets_fears_and_quarrels():
    from aria import learn
    texts = lambda s: [f.text for f in learn.extract(s)]   # noqa: E731
    assert texts("Sto studiando per l'esame di analisi due") == ["Sta studiando per l'esame di analisi due"]
    assert texts("Sono vegetariano") == ["Mangia vegetariano"] and texts("Sono vegana da due anni") == ["È vegano"]
    assert texts("Ho paura dei ragni") == ["Ha paura dei ragni"] and texts("Ho paura di volare") == ["Ha paura di volare"]
    assert texts("Ieri ho litigato con mio padre")[0].startswith("Ha litigato con suo padre")


def test_places_that_are_not_a_city_are_not_learned_as_the_city():
    """«abito in centro» faceva diventare «Centro» la citta' del meteo (e «vivo in Italia» l'Italia)."""
    from aria.learn import parse_city
    for t in ("abito in centro", "vivo in Italia", "abito in campagna vicino a Roma", "abito in via Roma"):
        assert parse_city(t) is None, t
    assert parse_city("abito a Città di Castello") == "Città di Castello" and parse_city("vivo a San Giovanni in Persiceto") == "San Giovanni in Persiceto"
