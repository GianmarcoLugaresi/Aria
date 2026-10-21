"""Memoria a lungo termine, un po' come quella di una persona.

  profilo   le cose certe: come ti chiami, dove abiti. Le scrive solo quello che DICI TU (mai il modello: i modelli piccoli inventano).
  fatti     cose che hai detto (gusti, famiglia, lavoro, salute...), ognuna con un'IMPORTANZA da 1 a 5:
            quelle importanti (4-5) restano per sempre, quelle futili (1-2) si sfumano dopo qualche settimana se non tornano utili.
  impegni   fatti con una data ("domani ho un esame"): si ricordano nei giorni intorno alla data, cosi' Aria puo' chiedere "com'e' andata?".
SQLite + FTS5. Un fatto uguale non si duplica ma si rafforza.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import sqlite3
import time

from . import i18n
from .textutil import normalize

DAY = 86400.0
PROFILE_LABELS = {"name": "nome", "city": "città"}


_FIRST = {"i'm": ("you're", "they're"), "i’m": ("you're", "they're"), "i've": ("you've", "they've"), "i'll": ("you'll", "they'll"), "i'd": ("you'd", "they'd"), "i": ("you", "they"),
          "me": ("you", "them"), "my": ("your", "their"), "mine": ("yours", "theirs"), "myself": ("yourself", "themselves"), "am": ("are", "are")}
_FIRST_RX = re.compile(r"\b(i['’]m|i['’]ve|i['’]ll|i['’]d|i|me|my|mine|myself)\b", re.I)
_THIRD_YOU = ((r"^is\b", "you're"), (r"^has\b", "you have"), (r"^works\b", "you work"), (r"^studies\b", "you study"), (r"^loves\b", "you love"), (r"^likes\b", "you like"),
              (r"^hates\b", "you hate"), (r"^dislikes\b", "you dislike"), (r"^adores\b", "you adore"), (r"^eats\b", "you eat"), (r"^can't stand\b", "you can't stand"),
              (r"^allergic\b", "you're allergic"), (r"^doesn't\b", "you don't"), (r"^(?=had|argued|broke|lost)", "you "))


def _says_i(text: str) -> bool:
    return bool(_FIRST_RX.search(text))


def person(fact: str, who: str = "you") -> str:
    """Un fatto sull'utente detto bene in inglese: «my dog is called Max» -> «your dog is called Max» (who='you') / «their dog…» (who='they');
    «Is vegetarian» -> «you're vegetarian». Per i fatti scritti dall'utente stesso (prima persona) e per quelli che Aria ricava (terza persona senza soggetto)."""
    idx = 0 if who == "you" else 1
    f = re.sub(r"\s*\((?:said|told) on [^)]*\)", "", fact.strip()) if who == "you" else fact.strip()
    if _says_i(f):
        out = _FIRST_RX.sub(lambda m: _FIRST[m.group(1).lower().replace("’", "'")][idx], f)
        out = re.sub(r"\b(you|they) am\b", r"\1 are", out, flags=re.I)
        out = re.sub(r"\b(you|they) was\b", r"\1 were", out, flags=re.I)
        return out[:1].lower() + out[1:]
    if who != "you":
        return f
    low = f[:1].lower() + f[1:]
    for rx, rep in _THIRD_YOU:
        if re.match(rx, low, re.I):
            return re.sub(r"\btheir\b", "your", re.sub(rx, rep, low, count=1, flags=re.I), flags=re.I)
    return re.sub(r"\btheir\b", "your", low, flags=re.I)


class Memory:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, text TEXT NOT NULL, norm TEXT UNIQUE, created REAL, used REAL);
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, tokenize='unicode61 remove_diacritics 2');
            CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, started REAL, summary TEXT);
            CREATE TABLE IF NOT EXISTS profile(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated REAL);
            """
        )
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(facts)")}          # database di versioni precedenti: aggiunge le colonne nuove
        for col, ddl in (("importance", "INTEGER DEFAULT 3"), ("due", "REAL"), ("kind", "TEXT DEFAULT 'fatto'"), ("followed", "INTEGER DEFAULT 0")):
            if col not in cols:
                self.db.execute(f"ALTER TABLE facts ADD COLUMN {col} {ddl}")
        self.db.commit()

    # -- profilo (cose certe)
    def set_profile(self, key: str, value: str) -> None:
        value = re.sub(r"\s+", " ", value or "").strip()
        if value:
            self.db.execute("INSERT INTO profile(key,value,updated) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
                            (key, value, time.time()))
            self.db.commit()

    def get_profile(self, key: str) -> str | None:
        r = self.db.execute("SELECT value FROM profile WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

    def del_profile(self, key: str) -> bool:
        n = self.db.execute("DELETE FROM profile WHERE key=?", (key,)).rowcount
        self.db.commit()
        return n > 0

    def profile(self) -> dict[str, str]:
        return {k: v for k, v in self.db.execute("SELECT key,value FROM profile WHERE key NOT LIKE '\\_%' ESCAPE '\\'")}

    def times_asked(self, what: str) -> tuple[int, float]:
        """Quante volte Aria ha gia' chiesto 'name'/'city' e quando l'ultima (per non diventare insistente)."""
        v = self.get_profile("_asked_" + what)
        if not v:
            return 0, 0.0
        n, _, ts = v.partition("|")
        return int(n), float(ts or 0)

    def mark_asked(self, what: str, count: int | None = None) -> None:
        n, _ = self.times_asked(what)
        self.set_profile("_asked_" + what, f"{n + 1 if count is None else count}|{time.time()}")

    # -- fatti
    def add_fact(self, text: str, importance: int = 3, due: float | None = None, kind: str = "fatto") -> int | None:
        """Aggiunge un fatto. Se c'e' gia' non lo duplica: lo rafforza (importanza piu' alta, ricordato adesso) e restituisce None."""
        text = re.sub(r"\s+", " ", text).strip().rstrip(".")
        if len(text) < 4:
            return None
        importance = max(1, min(5, int(importance)))
        norm = normalize(text)
        now = time.time()
        row = self.db.execute("SELECT id, importance FROM facts WHERE norm=?", (norm,)).fetchone()
        if row:
            self.db.execute("UPDATE facts SET used=?, importance=? WHERE id=?", (now, max(row[1] or 3, importance), row[0]))
            self.db.commit()
            return None
        cur = self.db.execute("INSERT INTO facts(text,norm,created,used,importance,due,kind) VALUES(?,?,?,?,?,?,?)",
                              (text, norm, now, now, importance, due, kind))
        self.db.execute("INSERT INTO facts_fts(rowid,text) VALUES(?,?)", (cur.lastrowid, text))
        self.db.commit()
        return cur.lastrowid

    def forget(self, keyword: str) -> int:
        """Dimentica i fatti che contengono la parola e, se la parola riguarda il nome o la citta', anche il profilo."""
        key = normalize(keyword)
        if not key:
            return 0
        gone = 0
        words = set(key.split())
        if words & {"nome", "chiamo", "chiamarmi", "chiami"} and self.del_profile("name"):
            gone += 1
        if words & {"citta", "abito", "abita", "vivo", "casa", "dove"} and self.del_profile("city"):
            gone += 1
        for k in ("name", "city"):                                   # "dimentica che mi chiamo Luca": il valore detto corrisponde
            v = self.get_profile(k)
            if v and normalize(v) in key:
                self.del_profile(k)
                gone += 1
        rows = self.db.execute("SELECT id,norm FROM facts").fetchall()
        ids = [i for i, n in rows if key in n]
        for i in ids:
            self.db.execute("DELETE FROM facts WHERE id=?", (i,))
            self.db.execute("DELETE FROM facts_fts WHERE rowid=?", (i,))
        self.db.commit()
        return gone + len(ids)

    def all_facts(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT text FROM facts ORDER BY created")]

    @staticmethod
    def _fades(importance: int, created: float, now: float, matched: bool) -> bool:
        """Le cose futili si sfumano: importanza 1-2 dopo 6 settimane, 3 dopo 6 mesi, 4-5 mai. Se tornano in un discorso, restano."""
        age_d = (now - created) / DAY
        return not matched and ((importance <= 2 and age_d > 42) or (importance == 3 and age_d > 180))

    def relevant(self, query: str | None, k: int = 6, now: float | None = None) -> list[str]:
        """I fatti da tenere a mente adesso: contano pertinenza alla frase, importanza e freschezza; i futili vecchi non ci sono."""
        now = now or time.time()
        matched: set[int] = set()
        words = [w for w in normalize(query or "").split() if len(w) >= 3]
        if words:
            q = " OR ".join(f'"{w}"' for w in words[:12])
            try:
                matched = {r[0] for r in self.db.execute("SELECT rowid FROM facts_fts WHERE facts_fts MATCH ? LIMIT 50", (q,))}
            except sqlite3.OperationalError:
                matched = set()
        scored = []
        for i, text, imp, created, used in self.db.execute("SELECT id,text,COALESCE(importance,3),created,used FROM facts WHERE COALESCE(kind,'fatto')='fatto'"):
            m = i in matched
            if self._fades(imp, created or now, now, m):
                continue
            fresh = math.exp(-((now - (used or created or now)) / DAY) / 30.0)
            scored.append((imp + (3.0 if m else 0.0) + 1.5 * fresh, i, text))
        scored.sort(key=lambda x: -x[0])
        out = scored[:k]
        for _, i, _ in out:
            self.db.execute("UPDATE facts SET used=? WHERE id=?", (now, i))
        self.db.commit()
        return [t for _, _, t in out]

    def upcoming(self, now: float | None = None) -> list[tuple[str, int]]:
        """Impegni vicini: [(testo, giorni)] con giorni < 0 se sono gia' passati (da ieri a 3 giorni fa), 0 oggi, 1 domani, 2 dopodomani."""
        now = now or time.time()
        today = dt.datetime.fromtimestamp(now).date()
        out = []
        for text, due in self.db.execute("SELECT text,due FROM facts WHERE kind='evento' AND due IS NOT NULL ORDER BY due"):
            days = (dt.datetime.fromtimestamp(due).date() - today).days
            if -3 <= days <= 2:
                out.append((text, days))
        return out

    def pending_followups(self, now: float | None = None) -> list[tuple[int, str, int]]:
        """Impegni passati da ieri a 3 giorni fa di cui Aria non ha ancora chiesto com'e' andata: [(id, testo, giorni)] con giorni < 0, i piu' recenti prima."""
        now = now or time.time()
        today = dt.datetime.fromtimestamp(now).date()
        out = []
        for i, text, due in self.db.execute("SELECT id,text,due FROM facts WHERE kind='evento' AND due IS NOT NULL AND COALESCE(followed,0)=0 ORDER BY due DESC"):
            days = (dt.datetime.fromtimestamp(due).date() - today).days
            if -3 <= days <= -1:
                out.append((i, text, days))
        return out

    def mark_followed(self, fact_id: int) -> None:
        self.db.execute("UPDATE facts SET followed=1 WHERE id=?", (fact_id,))
        self.db.commit()

    # -- sessioni (i riassunti automatici non si usano piu': il modello piccolo li inventava)
    def add_session(self, summary: str) -> None:
        summary = summary.strip()
        if summary:
            self.db.execute("INSERT INTO sessions(started,summary) VALUES(?,?)", (time.time(), summary))
            self.db.commit()

    def last_session(self) -> tuple[float, str] | None:
        r = self.db.execute("SELECT started,summary FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
        return (r[0], r[1]) if r else None

    # -- prompt e risposte
    def set_last_topic(self, text: str, now: float | None = None) -> None:
        """Una frase detta dall'utente a fine conversazione (parole sue, non riassunti del modello): la volta dopo Aria puo' riprenderla."""
        self.set_profile("_last_topic", text[:140])
        self.set_profile("_last_topic_ts", str(now or time.time()))

    def last_topic(self, now: float | None = None) -> tuple[str, str] | None:
        """(frase, «ieri»/«ieri sera»…) se l'ultima conversazione e' di 30 minuti - 3 giorni fa, altrimenti None."""
        text, ts = self.get_profile("_last_topic"), self.get_profile("_last_topic_ts")
        if not text or not ts:
            return None
        now = now or time.time()
        age = now - float(ts)
        if age < 30 * 60 or age > 3 * DAY:
            return None
        then = dt.datetime.fromtimestamp(float(ts))
        days = (dt.datetime.fromtimestamp(now).date() - then.date()).days
        part = "sera" if then.hour >= 18 else "giorno"
        if i18n.is_en():
            when = ("earlier today, a few hours ago" if days == 0 else ("yesterday evening" if part == "sera" else "yesterday") if days == 1 else "the day before yesterday" if days == 2 else "a few days ago")
        else:
            when = ("oggi, qualche ora fa" if days == 0 else ("ieri sera" if part == "sera" else "ieri") if days == 1 else "l'altro ieri" if days == 2 else "qualche giorno fa")
        return text, when

    def context(self, query: str | None = None, k: int = 6, now: float | None = None, include_last: bool = False) -> str:
        en = i18n.is_en()
        lines = []
        p = self.profile()
        known = []
        if p.get("name"):
            known.append(f"their name is {p['name']}" if en else f"si chiama {p['name']}")
        if p.get("city"):
            known.append(f"they live in {p['city']}" if en else f"abita a {p['city']}")
        if known:
            lines.append(("You know for sure that " + " and ".join(known) + ". Use the name now and then, not in every sentence.") if en
                         else "Sai con certezza che " + " e ".join(known) + ". Usa il nome ogni tanto, non a ogni frase.")
        facts = self.relevant(query, k, now)
        if facts:
            lines.append(("Things the user told you that you remember: " + "; ".join(person(f, "they") for f in facts) + ". If they relate to what they are saying now, bring them up naturally now and then (without listing them).") if en
                         else "Cose che l'utente ti ha detto e che ricordi: " + "; ".join(facts) + ". Se c'entrano con quello che dice adesso, ogni tanto riprendile con naturalezza (senza elencarle).")
        last = self.last_topic(now) if include_last else None
        if last:
            lines.append((f"Last time ({last[1]}) they told you: \"{last[0]}\". If it comes naturally, ask how that is going, only once and without pushing.") if en
                         else f"L'ultima volta ({last[1]}) ti ha detto: «{last[0]}». Se viene naturale, chiedi come va con quella cosa, una volta sola e senza insistere.")
        when = ({-3: "a few days ago", -2: "the day before yesterday", -1: "yesterday", 0: "today", 1: "tomorrow", 2: "the day after tomorrow"} if en
                else {-3: "qualche giorno fa", -2: "l'altro ieri", -1: "ieri", 0: "oggi", 1: "domani", 2: "dopodomani"})
        notes = []
        for text, d in self.upcoming(now):
            notes.append(f"{text} ({when[d]}" + (("; if it comes up, naturally ask how it went)" if en else "; se capita, chiedigli con naturalezza com'è andata)") if d < 0 else ")"))
        if notes:
            lines.append(("Commitments they told you about: " if en else "Impegni che ti ha detto: ") + "; ".join(notes) + ".")
        return "\n".join(lines)

    def describe(self, k: int = 6) -> str:
        """Cosa sa Aria dell'utente, detto a voce (per 'cosa sai di me?')."""
        p = self.profile()
        en = i18n.is_en()
        bits = []
        if p.get("name"):
            bits.append(f"your name is {p['name']}" if en else f"ti chiami {p['name']}")
        if p.get("city"):
            bits.append(f"you live in {p['city']}" if en else f"abiti a {p['city']}")
        facts = self.relevant(None, k)
        if not bits and not facts:
            return ("I don't know anything about you yet. Tell me something: to start, what's your name?" if en
                    else "Non so ancora niente di te. Raccontami qualcosa: per cominciare, come ti chiami?")
        out = []
        if bits:
            out.append(("I know that " + " and ".join(bits) + ".") if en else "So che " + " e ".join(bits) + ".")
        if facts:
            out.append(("I also remember that " + "; ".join(dict.fromkeys(person(f[0] if isinstance(f, tuple) else f, "you") for f in facts)) + ".") if en
                       else "Mi ricordo anche che " + "; ".join(f[0].lower() + f[1:] for f in facts) + ".")
        return " ".join(out)
