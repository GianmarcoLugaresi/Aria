"""La memoria "umana": profilo certo, importanza, dimenticanza graduale, impegni con data, correzioni."""
import datetime as dt
import sqlite3
import time

from aria.memory import DAY, Memory


def test_profile_and_asking_bookkeeping():
    m = Memory()
    assert m.get_profile("name") is None
    m.set_profile("name", "  Mario ")
    m.set_profile("name", "Mario")                               # sovrascrive
    assert m.get_profile("name") == "Mario"
    m.mark_asked("name")
    assert m.profile() == {"name": "Mario"}                      # i contatori interni non sono "cose che so di te"
    n, ts = m.times_asked("name")
    assert n == 1 and abs(ts - time.time()) < 5
    m.mark_asked("name", count=3)
    assert m.times_asked("name")[0] == 3 and m.del_profile("name") and not m.del_profile("name")


def test_importance_decides_what_fades():
    m = Memory()
    for text, imp, age in (("Apprezza il jazz", 2, 50), ("Apprezza il tè", 2, 5), ("Ha un cane", 4, 400), ("Studia ingegneria", 3, 200), ("Allergia: noci", 5, 900)):
        m.add_fact(text, imp)
        m.db.execute("UPDATE facts SET created=?, used=? WHERE text=?", (time.time() - age * DAY, time.time() - age * DAY, text))
    got = " | ".join(m.relevant(None, 10))
    assert "cane" in got and "noci" in got and "tè" in got        # importanti per sempre; il futile recente c'e'
    assert "jazz" not in got and "ingegneria" not in got          # futile vecchio e medio molto vecchio: sfumati
    assert "jazz" in " ".join(m.relevant("che musica come il jazz", 10))      # ma se se ne torna a parlare, riaffiora


def test_repeating_a_fact_reinforces_it():
    m = Memory()
    assert m.add_fact("Apprezza il caffè", 2)
    assert m.add_fact("apprezza il caffè", 4) is None
    assert m.db.execute("SELECT importance FROM facts").fetchone()[0] == 4 and len(m.all_facts()) == 1


def test_events_come_back_around_their_date():
    m = Memory()
    now = time.time()
    day = lambda n: dt.datetime.combine(dt.date.today() + dt.timedelta(days=n), dt.time(23, 59, 59)).timestamp()
    m.add_fact("Domani: ha un esame", 3, day(1), "evento")
    m.add_fact("Ieri: aveva il dentista", 3, day(-1), "evento")
    m.add_fact("Tra dieci giorni: ha una gara", 3, day(10), "evento")
    m.add_fact("Dieci giorni fa: ha fatto un viaggio", 3, day(-10), "evento")
    up = dict(m.upcoming(now))
    assert up == {"Domani: ha un esame": 1, "Ieri: aveva il dentista": -1}
    ctx = m.context(None, 6, now)
    assert "Impegni" in ctx and "domani" in ctx and "com'è andata" in ctx and "gara" not in ctx and "viaggio" not in ctx
    assert "esame" not in " ".join(m.relevant(None, 10))          # gli impegni non finiscono tra i fatti generici


def test_context_states_only_certain_things():
    m = Memory()
    assert m.context() == ""                                       # niente nome, niente citta': non afferma nulla
    m.set_profile("name", "Mario")
    m.set_profile("city", "Milano")
    m.add_fact("Ha un cane", 4)
    ctx = m.context("cane")
    assert "si chiama Mario e abita a Milano" in ctx and "Ha un cane" in ctx


def test_forget_covers_the_profile_too():
    m = Memory()
    m.set_profile("name", "Mario")
    m.set_profile("city", "Milano")
    assert m.forget("il mio nome") == 1 and m.get_profile("name") is None and m.get_profile("city") == "Milano"
    assert m.forget("dove abito") == 1 and m.get_profile("city") is None
    m.set_profile("name", "Luca")
    assert m.forget("che mi chiamo Luca") >= 1 and m.get_profile("name") is None


def test_describe_for_what_do_you_know_about_me():
    m = Memory()
    assert "Non so ancora niente" in m.describe()
    m.set_profile("name", "Mario")
    m.add_fact("Ha un cane", 4)
    d = m.describe()
    assert "ti chiami Mario" in d and "ricordo anche che ha un cane" in d


def test_old_databases_are_upgraded(tmp_path):
    p = str(tmp_path / "vecchia.db")
    db = sqlite3.connect(p)
    db.executescript("CREATE TABLE facts(id INTEGER PRIMARY KEY, text TEXT NOT NULL, norm TEXT UNIQUE, created REAL, used REAL);"
                     "CREATE VIRTUAL TABLE facts_fts USING fts5(text, tokenize='unicode61 remove_diacritics 2');"
                     "CREATE TABLE sessions(id INTEGER PRIMARY KEY, started REAL, summary TEXT);"
                     "INSERT INTO facts(text,norm,created,used) VALUES('Ha un gatto','ha un gatto',%f,%f);" % (time.time(), time.time()))
    db.commit()
    db.close()
    m = Memory(p)
    assert m.add_fact("Ha un cane", 4) and set(m.all_facts()) == {"Ha un gatto", "Ha un cane"}
    assert "gatto" in " ".join(m.relevant(None, 5))                # il vecchio fatto ha importanza 3 di default
