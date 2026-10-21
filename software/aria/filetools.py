"""Gli strumenti di Aria sui file: scrivere un testo, fare una ricerca e salvarla, liste e note, leggere e riassumere.

Tutto passa da `Workspace` (workspace.py): solo la cartella scelta dall'utente, solo file di testo, niente cancellazioni ne' sovrascritture.
Sono "mixin" di `Tools`: usano `self.cfg`, `self._web_results` e `self.generate` (una funzione async (sistema, richiesta, max_token) -> testo
che Aria collega al suo chatbot).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from . import i18n
from . import profiles as P
from .textutil import pick
from .workspace import Workspace, WorkspaceError, check_root, plain_for_speech, stamp

ASK = "@CHIEDI"                                         # vedi powers.ASK: manca un pezzo, lo si chiede a voce
NO_WORKSPACE = "Non ho ancora una cartella dove salvare i file: scegline una nelle Impostazioni di Aria."
NO_WORKSPACE_EN = "I don't have a folder to save files in yet: pick one in Aria's Settings."

DOC_SYSTEM = ("Sei un assistente che scrive testi in italiano, ben fatti e in Markdown. Scrivi esattamente quello che viene chiesto, "
              "senza frasi introduttive tipo «Ecco il testo» e senza commenti finali. Usa un titolo (# ) e, se serve, paragrafi o elenchi. "
              "Se non sei sicuro di un fatto non inventarlo: resta sul generale.")
DOC_PRO_SYSTEM = ("Sei un redattore che scrive documenti in italiano, completi, chiari e ben organizzati, in Markdown. Rispondi SOLO con il documento: "
                  "niente frasi introduttive («Ecco…») e niente commenti finali. Struttura: un titolo (# ), una breve introduzione, sezioni con titoli (## ), "
                  "elenchi puntati o numerati dove servono (per una ricetta: ## Ingredienti con le quantità, ## Preparazione con i passaggi numerati, ## Consigli) e una chiusa utile. "
                  "Spiega le cose per bene, con frasi complete. Se hai una bozza o delle note usale come base, ma correggi gli errori e completa i punti mancanti; "
                  "se le note dal web contraddicono la bozza, vale il web. Non inventare fatti, numeri o fonti: se non sei sicuro, resta sul generale.")
REVIEW_SYSTEM = ("Sei un revisore attento. Ti viene dato un documento in Markdown: restituiscilo rivisto, SOLO il documento. Correggi gli errori di fatto (confrontandoli con le note dal web, se ci sono), "
                 "gli errori di italiano e di battitura; completa passaggi o dati mancanti; togli ripetizioni e frasi vuote; controlla che l'ordine dei passaggi abbia senso e che le quantità siano coerenti. "
                 "Mantieni titolo e struttura (# , ## , elenchi). Se è un testo creativo (poesia, lettera, storia) conserva lo stile. Nessun commento su cosa hai cambiato.")
DOC_CREATIVE_SYSTEM = ("Sei uno scrittore che scrive testi creativi in italiano (canzoni, poesie, lettere, filastrocche, discorsi, dediche). Rispondi SOLO con il testo richiesto: "
                       "un titolo (# ) e poi il testo, con le strofe o i paragrafi separati da una riga vuota e un verso per riga. Niente introduzione («Ecco…»), niente commenti, "
                       "niente sezioni da articolo, niente elenchi puntati e niente note. Se l'utente ti ha dato o dettato un testo (strofe, ritornello, versi), continua nello stesso stile, "
                       "con lo stesso tono, la stessa lunghezza dei versi e lo stesso tipo di rime, senza ripetere quello che c'è già. Non inventare fatti reali.")
REVIEW_CREATIVE_SYSTEM = ("Sei un revisore di testi creativi. Ti viene dato un testo (canzone, poesia, lettera…): restituiscilo rivisto, SOLO il testo. Correggi errori di italiano e di battitura, "
                          "migliora i versi deboli e il ritmo, mantieni titolo, stile, voce e struttura a strofe (una riga vuota tra le strofe, un verso per riga). "
                          "Non aggiungere sezioni, elenchi, introduzioni né commenti su cosa hai cambiato.")
TOPIC_SYSTEM = "Rispondi SOLO con l'argomento del testo in al massimo sei parole, senza virgolette né punto finale."
DOC_SYSTEM_EN = ("You are an assistant who writes well-made texts in English, in Markdown. Write exactly what is asked, without introductory phrases like \"Here is the text\" "
                 "and without closing comments. Use a title (# ) and, if needed, paragraphs or lists. If you are not sure of a fact, don't invent it: stay general.")
DOC_PRO_SYSTEM_EN = ("You are an editor who writes documents in English: complete, clear and well organised, in Markdown. Reply with the document ONLY: "
                     "no introductory phrases (\"Here is…\") and no closing comments. Structure: a title (# ), a short introduction, sections with headings (## ), "
                     "bulleted or numbered lists where useful (for a recipe: ## Ingredients with the quantities, ## Method with numbered steps, ## Tips) and a useful conclusion. "
                     "Explain things properly, in full sentences. If you have a draft or notes, use them as a base, but correct the mistakes and fill in the missing points; "
                     "if the notes from the web contradict the draft, the web wins. Don't invent facts, numbers or sources: if you're not sure, stay general.")
REVIEW_SYSTEM_EN = ("You are a careful reviewer. You are given a document in Markdown: return it revised, ONLY the document. Correct factual errors (checking them against the notes from the web, if any), "
                    "spelling and grammar mistakes; fill in missing steps or data; remove repetition and empty sentences; check that the order of the steps makes sense and that the quantities are consistent. "
                    "Keep the title and structure (# , ## , lists). If it is a creative text (poem, letter, story) keep its style. No comments about what you changed.")
DOC_CREATIVE_SYSTEM_EN = ("You are a writer of creative texts in English (songs, poems, letters, rhymes, speeches, dedications). Reply ONLY with the requested text: "
                          "a title (# ) and then the text, with stanzas or paragraphs separated by a blank line and one line of verse per line. No introduction (\"Here is…\"), no comments, "
                          "no article-style sections, no bullet lists and no notes. If the user gave or dictated a text (stanzas, chorus, lines), continue in the same style, "
                          "with the same tone, the same line length and the same kind of rhymes, without repeating what is already there. Don't invent real facts.")
REVIEW_CREATIVE_SYSTEM_EN = ("You are a reviewer of creative texts. You are given a text (song, poem, letter…): return it revised, ONLY the text. Fix spelling and grammar mistakes, "
                             "improve weak lines and the rhythm, keep the title, style, voice and stanza structure (a blank line between stanzas, one line of verse per line). "
                             "Do not add sections, lists, introductions or comments about what you changed.")
TOPIC_SYSTEM_EN = "Reply ONLY with the topic of the text in six words at most, without quotation marks or a final full stop."
RESEARCH_SYSTEM_EN = ("Summarise in English ONLY what is written in the search results you are given: add nothing of your own. "
                      "If the results contradict each other, say so. Format: first a two-sentence paragraph, then a blank line, then 4-6 bullet points "
                      "starting with \"- \". No introduction and no comments.")
SUMMARY_SYSTEM_EN = "Summarise in English, in three clear sentences, the text you are given. Only the summary, without an introduction."
# parole che dicono che il testo da scrivere e' CREATIVO (non un testo di fatti): niente ricerca sul web, niente struttura da articolo.
# «storia» e «racconto» non ci sono: «la storia di Roma» e' un testo di fatti
_CREATIVE_EN = re.compile(r"\b(?:stanzas?|chorus|verses?|songs?|lyrics|poems?|poetry|rhymes?|limericks?|haikus?|sonnets?|jokes?|riddles?|letters?|dedications?|fairy ?tales?|fables?|scripts?|dialogues?|raps?|"
                          r"anthems?|toasts?|greetings?|birthday (?:message|card|wish\w*)|wedding speech|speech|stor(?:y|ies)|tales?|bedtime)\b")
_CREATIVE = re.compile(r"\b(?:strof\w+|ritornell\w+|vers[oi]|canzon\w+|poesi\w+|poem\w+|filastrocc\w+|rim[ae]|barzellett\w+|lettera|lettere|dedica|favol\w+|fiab\w+|copione|dialogo|lyrics|rap|inno|discorso di (?:auguri|matrimonio|laurea)|auguri|biglietto)\b")


def is_creative(*texts: str) -> bool:
    """Il testo richiesto e' creativo (canzone, poesia, lettera, dedica…)? Allora si scrive di fantasia, senza cercare sul web e senza forma da articolo."""
    from .textutil import normalize
    if i18n.is_en():
        joined = " ".join(t for t in texts if t).lower()
        if re.search(r"\b(?:history|story|stories) of\b|\bhistory\b", joined):
            return bool(re.search(r"\b(?:poems?|songs?|lyrics|rhymes?|limericks?|haikus?|letters?|jokes?)\b", joined))              # «the story of Rome» e' un testo di fatti
        return bool(_CREATIVE_EN.search(joined))
    return bool(_CREATIVE.search(normalize(" ".join(t for t in texts if t))))

FACT_KINDS_EN = {"recipe", "guide", "explanation", "article", "report", "summary", "outline", "tutorial", "text", "notes", "research", "instructions", "procedure", "essay", "paper", "analysis", "review", "description", "biography"}
FACT_KINDS = {"ricetta", "guida", "spiegazione", "articolo", "relazione", "riassunto", "scaletta", "tutorial", "report", "testo", "appunti", "ricerca", "istruzioni", "procedura"}      # qui contano i fatti: si controlla anche sul web
RESEARCH_SYSTEM = ("Riassumi in italiano SOLO quello che è scritto nei risultati di ricerca che ti vengono dati: non aggiungere niente di tuo. "
                   "Se i risultati si contraddicono, dillo. Formato: prima un paragrafo di due frasi, poi una riga vuota, poi 4-6 punti elenco "
                   "che iniziano con «- ». Nessuna introduzione e nessun commento.")
SUMMARY_SYSTEM = "Riassumi in italiano, in tre frasi chiare, il testo che ti viene dato. Solo il riassunto, senza introduzione."


def _no_workspace() -> str:
    return i18n.pick(NO_WORKSPACE, NO_WORKSPACE_EN)


def _clean_doc(text: str) -> str:
    """Toglie la frase di cortesia in testa («Ecco il testo:») e le recinzioni ```markdown che i modelli piccoli aggiungono."""
    text = re.sub(r"(?s)<\|channel>.*?<channel\|>", "", text or "")                  # il «ragionamento» che alcuni modelli scrivono prima della risposta non e' parte del documento
    if "<|channel>" in text:                                                          # ragionamento mai chiuso: non c'e' nessun documento
        text = text.split("<|channel>")[0]
    lines = text.strip().splitlines()
    if len(lines) > 2 and re.match(r"^(ecco|certo|va bene|ok|volentieri|sicuro|here|here's|sure|certainly|of course|okay|alright|absolutely|happy to)\b.*[:!.]$", lines[0].strip(), re.I):
        lines = lines[1:]
    t = "\n".join(lines).strip()
    t = re.sub(r"^```[a-zA-Z]*[ \t]*\n", "", t)
    t = re.sub(r"\n```[ \t]*$", "", t)
    return t.strip()


def _sources_md(refs: list) -> str:
    """Le righe della sezione «Fonti». I titoli dei motori di ricerca a volte arrivano incollati a quello del risultato dopo («…ChefsRicetta Gnocchi…»): si tiene solo il primo."""
    out = []
    for t, _b, u in refs:
        m = re.search(r"(?<=[a-zà-ù]{3})(?=[A-Z][a-zà-ù])", t[12:])
        t = (t[:12 + m.start()] if m else t)[:90].strip(" -–—|:")
        out.append(f"- {t} — {u}" if u else f"- {t}")
    return "\n".join(out)


async def _public_https(url: str) -> bool:
    """True se l'indirizzo e' https e il nome porta a un indirizzo pubblico (mai il Mac stesso, la rete di casa o indirizzi speciali)."""
    import asyncio
    import ipaddress
    import socket
    from urllib.parse import urlparse
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or "." not in host or re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?|.*\.(?:local|internal|lan|home|localhost)", host) or host == "localhost":
        return False
    try:
        infos = await asyncio.get_running_loop().run_in_executor(None, lambda: socket.getaddrinfo(host, u.port or 443, proto=socket.IPPROTO_TCP))
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            return False
    return bool(infos)


_BULLET = re.compile(r"^\s*[-*•]\s+")


def _split_summary(text: str) -> tuple[str, str]:
    """(in breve, punti) da quello che scrive il modello: il paragrafo prima dell'elenco + l'elenco come punti con '- '."""
    t = (text or "").strip()
    if not t:
        return "", ""
    lines = t.splitlines()
    first_bullet = next((i for i, ln in enumerate(lines) if _BULLET.match(ln)), None)
    if first_bullet is not None and first_bullet > 0:                      # un paragrafo e poi un elenco
        in_breve = " ".join(ln.strip() for ln in lines[:first_bullet] if ln.strip())
        rest = "\n".join(lines[first_bullet:])
    else:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]
        if len(blocks) >= 2 and not _BULLET.match(blocks[0]):
            in_breve, rest = blocks[0], "\n".join(blocks[1:])
        else:                                                                 # tutto di seguito: le prime due frasi sono "in breve"
            sentences = re.split(r"(?<=[.!?])\s+", t)
            in_breve, rest = " ".join(sentences[:2]).strip(), " ".join(sentences[2:]).strip()
    items = [re.sub(r"^[-*•]\s*", "", ln).strip() for ln in re.split(r"\n|(?<=[.!?])\s+(?=[A-ZÀ-Ý])", rest) if ln.strip()]
    return in_breve, "\n".join(f"- {b}" for b in items if b)


def first_sentences(text: str, max_chars: int = 240) -> str:
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or "").strip()):
        if out and len(out) + len(s) > max_chars:
            break
        out = (out + " " + s).strip()
        if len(out) >= max_chars * 0.6:
            break
    return out[:max_chars].rstrip()


class FileTools:
    generate = None                                    # async (sistema, richiesta, max_token) -> testo; la imposta Aria
    progress = None                                    # (etichetta, da, a, secondi) -> None: l'avanzamento per la barra dell'overlay; lo imposta Aria

    def _prog(self, label: str, start: float | None = None, until: float | None = None, eta: float | None = None) -> None:
        if self.progress is not None:
            try:
                self.progress(label, start, until, eta)
            except Exception:                                                          # noqa: BLE001
                pass

    def _ws(self) -> Workspace | None:
        """La cartella di Aria, riletta a ogni uso (cambia dalle Impostazioni senza riavviare) e riconvalidata (puo' essere stata spostata)."""
        root = self.cfg.get("workspace") or P.get_workspace(self.cfg.get("_config_path"))
        if not root:
            return None
        try:
            return Workspace(check_root(root))
        except WorkspaceError:
            return None

    async def _page_text(self, url: str, limit: int = 2800) -> str:
        """Il testo principale di una pagina web pubblica (https, mai indirizzi IP o locali). Serve a scrivere il documento sui FATTI veri e non sui riassuntini della ricerca."""
        import html as _html
        from urllib.parse import urljoin
        try:
            for _hop in range(4):                                                      # i rinvii si seguono a mano: ognuno deve essere di nuovo un sito pubblico
                if not await _public_https(url):                                       # (prima un sito pubblico poteva rinviare a «http://127.0.0.1…» o al router di casa)
                    return ""
                r = await self.http.get(url, timeout=7.0, follow_redirects=False)
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    url = urljoin(url, r.headers["location"])
                    continue
                break
            else:
                return ""
            if r.status_code != 200 or "html" not in r.headers.get("content-type", "") or len(r.content) > 2_000_000:
                return ""
            raw = r.text
        except Exception:                                                              # noqa: BLE001
            return ""
        raw = re.sub(r"(?is)<(script|style|nav|header|footer|aside|form|noscript|svg|iframe)\b.*?</\1>", " ", raw)
        raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
        raw = re.sub(r"(?i)</?(?:p|div|li|ul|ol|br|h[1-6]|tr|section|article)[^>]*>", "\n", raw)
        text = _html.unescape(re.sub(r"<[^>]+>", " ", raw))
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if len(ln) >= 25 or re.fullmatch(r"(?i)(ingredienti|preparazione|procedimento|consigli|come si prepara)[: ]*", ln)]
        body = "\n".join(lines)
        i = body.lower().find("ingredienti")
        if i > 0:                                                                       # le ricette: si parte dagli ingredienti
            body = body[i:]
        return body[:limit]

    async def _doc_refs(self, topic: str) -> list[tuple[str, str, str]]:
        """Note dal web sull'argomento, per controllare i fatti del documento. Se la rete non c'e' o e' spenta, nessuna nota (il documento si scrive lo stesso)."""
        if not self.cfg.get("human", {}).get("doc_web", True) or not self.cfg.get("tools", {}).get("web_search"):
            return []
        try:
            return (await self._web_results(topic, 5))[:5]
        except Exception:                                                              # noqa: BLE001
            return []

    async def _compose_doc(self, request: str, topic_hint: str = "", source: str = "", history: list | None = None, ground: bool = True, creative: bool = False) -> tuple[str, list] | None:
        """Scrive un DOCUMENTO vero: bozza completa (con la conversazione, quello che Aria ha detto e le note dal web) e poi una revisione. Restituisce (testo, fonti) o None."""
        topic = topic_hint
        en = i18n.is_en()
        self._prog(i18n.pick("Capisco di cosa scrivere", "Working out what to write about"), 0.02, 0.08, 4)
        if not topic and self.generate is not None:
            try:
                topic = (await self.generate(i18n.pick(TOPIC_SYSTEM, TOPIC_SYSTEM_EN), f"{request}\n{source[:300]}", 20)).strip().strip("\"'«».#* \n")
            except Exception:                                                          # noqa: BLE001
                topic = ""
        if not topic or len(topic.split()) > 8 or "\n" in topic:
            topic = " ".join(re.sub(r"[^\wàèéìòù' ]", " ", request).split()[:6])
        ground = ground and not creative
        if ground and self.cfg.get("human", {}).get("doc_web", True):
            self._prog(i18n.pick("Cerco informazioni sul web", "Searching the web"), 0.08, 0.2, 8)
        refs = await self._doc_refs(topic) if ground else []
        notes = "\n".join(f"- {t}: {b[:350]}" for t, b, _u in refs)
        if refs and self.cfg.get("human", {}).get("doc_pages", True):
            pages = []
            self._prog(i18n.pick("Leggo le pagine trovate", "Reading the pages I found"), 0.2, 0.3, 8)
            for t, _b, u in refs[:3]:
                body = await self._page_text(u)
                if len(body) > 300:
                    pages.append((f"Page \"{t}\":\n{body}") if en else f"Pagina «{t}»:\n{body}")
                if len(pages) == 2:
                    break
            if pages:
                notes += "\n\n" + "\n\n".join(pages)
        if en:
            parts = [f"User request: {request}"]
            if history:
                cut = 1800 if creative else 500
                ctx = "\n".join(f"{'User' if m.get('role') == 'user' else 'Aria'}: {str(m.get('content', ''))[:cut]}" for m in history[-6:])
                parts.append("Recent conversation:\n" + ctx)
            if source:
                parts.append("What Aria said out loud (a draft to start from, to improve and complete; IT MAY CONTAIN MISTAKES: if the notes from the web say otherwise, the web wins):\n" + source)
            if notes:
                parts.append("Notes found on the web (to check the facts):\n" + notes)
            parts.append("Now write the requested text." if creative else "Now write the complete document, about 350-600 words.")
        else:
            parts = [f"Richiesta dell'utente: {request}"]
            if history:
                cut = 1800 if creative else 500                                              # un testo dettato (strofe, versi) va letto per intero
                ctx = "\n".join(f"{'Utente' if m.get('role') == 'user' else 'Aria'}: {str(m.get('content', ''))[:cut]}" for m in history[-6:])
                parts.append("Conversazione recente:\n" + ctx)
            if source:
                parts.append("Quello che Aria ha detto a voce (bozza da cui partire, da migliorare e completare; PUO' CONTENERE ERRORI: se le note dal web dicono altro, vale il web):\n" + source)
            if notes:
                parts.append("Note trovate sul web (per controllare i fatti):\n" + notes)
            parts.append("Scrivi ora il testo richiesto." if creative else "Scrivi ora il documento completo, circa 350-600 parole.")
        self._prog(i18n.pick("Scrivo la bozza", "Writing the draft"), 0.3, 0.66, 40)
        draft = _clean_doc(await self.generate((DOC_CREATIVE_SYSTEM_EN if en else DOC_CREATIVE_SYSTEM) if creative else (DOC_PRO_SYSTEM_EN if en else DOC_PRO_SYSTEM), "\n\n".join(parts), 1000))
        if len(draft) < 40:
            return None
        text = draft
        self._prog(i18n.pick("Rileggo e correggo", "Proofreading and correcting"), 0.66, 0.94, 40)
        try:
            review_user = ((f"Notes from the web:\n{notes}\n\n" if notes else "") + f"Document to review:\n{draft}") if en else ((f"Note dal web:\n{notes}\n\n" if notes else "") + f"Documento da rivedere:\n{draft}")
            review = _clean_doc(await self.generate((REVIEW_CREATIVE_SYSTEM_EN if en else REVIEW_CREATIVE_SYSTEM) if creative else (REVIEW_SYSTEM_EN if en else REVIEW_SYSTEM), review_user, 1100))
            if len(review) >= 0.7 * len(draft) and review.lstrip().startswith("#"):                # revisione credibile: altrimenti resta la bozza
                text = review
        except Exception:                                                              # noqa: BLE001
            pass
        return text, refs

    @staticmethod
    def _doc_summary(text: str) -> str:
        heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)][:4]
        if i18n.is_en():
            if not heads:
                return "with everything explained properly"
            return "it covers " + (", ".join(heads[:-1]) + " and " + heads[-1] if len(heads) > 1 else heads[0])
        if not heads:
            return "con tutto spiegato per bene"
        return "dentro trovi " + (", ".join(heads[:-1]) + " e " + heads[-1] if len(heads) > 1 else heads[0])

    async def _scrivi(self, arg: str) -> str:
        """arg = 'tipo|argomento' (es. 'testo|la fotosintesi'): il chatbot scrive il documento (bozza + revisione, con controllo sul web per i testi di fatti) e lo salva nella cartella."""
        ws = self._ws()
        if ws is None:
            return _no_workspace()
        en = i18n.is_en()
        kind, _, topic = arg.partition("|")
        kind, topic = (kind.strip() or ("text" if en else "testo")), topic.strip()
        if not topic:
            return f"{ASK}|SCRIVI|{kind}|" + i18n.pick("Su cosa vuoi che scriva?", "What do you want me to write about?")
        if self.generate is None:
            return i18n.pick("Per ora non riesco a scrivere testi.", "I can't write texts right now.")
        creative = is_creative(kind, topic)
        request = f"Write a {kind} about: {topic}." if en else f"Scrivi un/una {kind} su: {topic}."
        out = await self._compose_doc(request, topic_hint=topic, ground=kind.lower() in (FACT_KINDS_EN if en else FACT_KINDS), creative=creative)
        if out is None:
            return i18n.pick("Non sono riuscita a scrivere un testo decente: riprova.", "I couldn't write a decent text: please try again.")
        text, refs = out
        title = f"{kind.capitalize()} - {topic}"
        if not text.lstrip().startswith("#"):
            text = f"# {kind.capitalize()}: {topic}\n\n{text}"
        if refs:
            text += "\n\n## " + i18n.pick("Fonti", "Sources") + "\n" + _sources_md(refs)
        self._prog(i18n.pick("Salvo il file nella cartella", "Saving the file to the folder"), 0.96, 0.99, 2)
        name = ws.new_file(title, text)
        return i18n.pick(f"Fatto: ho scritto «{ws.display(name)}» e l'ho messo nella tua cartella.", f"Done: I wrote \"{ws.display(name)}\" and put it in your folder.")

    async def _salva(self, arg: str) -> str:
        """Scrive nella cartella un DOCUMENTO a parte su quello di cui state parlando (non la trascrizione della conversazione): bozza + revisione.
        arg = JSON {kind, request, source, history} oppure, all'antica, 'tipo|testo detto a voce'."""
        ws = self._ws()
        if ws is None:
            return _no_workspace()
        import json as _json
        try:
            d = _json.loads(arg) if arg.lstrip().startswith("{") else None
        except ValueError:
            d = None
        if d is None:
            kind, _, text = arg.partition("|")
            d = {"kind": kind.strip() or "testo", "request": f"Scrivi un documento ({kind.strip() or 'testo'}) con quello che ho appena detto a voce.", "source": text.strip(), "history": []}
        en = i18n.is_en()
        kind, source = d.get("kind") or ("text" if en else "testo"), (d.get("source") or "").strip()
        if len(source) < 40 and not d.get("history") and len(d.get("request") or "") < 200:             # (una richiesta lunga porta con se' il testo da usare: «ti leggo questa canzone… scrivi le altre strofe»)
            return i18n.pick("Non ho niente di abbastanza lungo da scrivere: dimmi cosa devo mettere nel file, ad esempio «scrivimi una ricetta di gnocchi».",
                             "I don't have anything long enough to write: tell me what to put in the file, for example \"write me a carbonara recipe\".")
        if self.generate is None:
            return i18n.pick("Per ora non riesco a scrivere testi.", "I can't write texts right now.")
        request = d.get("request") or i18n.pick("Scrivi un documento su quello che abbiamo detto.", "Write a document about what we said.")
        out = await self._compose_doc(request, source=source, history=d.get("history") or [], ground=str(kind).lower() in (FACT_KINDS_EN if en else FACT_KINDS), creative=is_creative(str(kind), request))
        if out is None:
            return i18n.pick("Non sono riuscita a scrivere un documento decente: riprova.", "I couldn't write a decent document: please try again.")
        text, refs = out
        m = re.match(r"^\s*#\s+(.+)$", text, re.M)
        title = (m.group(1).strip() if m else "") or f"{str(kind).capitalize()} - " + " ".join(source.split()[:5]).strip(" ,.;:!?")
        if not text.lstrip().startswith("#"):
            text = f"# {title}\n\n{text}"
        if refs:
            text += "\n\n## " + i18n.pick("Fonti", "Sources") + "\n" + _sources_md(refs)
        self._prog(i18n.pick("Salvo il file nella cartella", "Saving the file to the folder"), 0.96, 0.99, 2)
        name = ws.new_file(title, f"{text}\n\n*{stamp()}*")
        return i18n.pick(f"Fatto: ho scritto «{ws.display(name)}» nella tua cartella, {self._doc_summary(text)}.", f"Done: I wrote \"{ws.display(name)}\" in your folder, {self._doc_summary(text)}.")

    async def _ricerca(self, arg: str) -> str:
        """Cerca sul web, riassume SOLO quello che ha trovato e, se c'e' una cartella, salva la nota con le fonti."""
        topic = arg.strip()
        en = i18n.is_en()
        if not topic:
            return f"{ASK}|RICERCA||" + i18n.pick("Su cosa faccio la ricerca?", "What should I research?")
        results = await self._web_results(topic, 6)
        if not results:
            return i18n.pick(f"Non ho trovato niente su {topic}.", f"I didn't find anything about {topic}.")
        digest = "\n".join(f"- {t}: {b[:300]}" for t, b, _u in results)
        raw = ""
        if self.generate is not None:
            if en:
                raw = await self.generate(RESEARCH_SYSTEM_EN, f"Topic: {topic}\n\nSearch results:\n{digest}", 650)
            else:
                raw = await self.generate(RESEARCH_SYSTEM, f"Argomento: {topic}\n\nRisultati della ricerca:\n{digest}", 650)
        in_breve, punti = _split_summary(raw or "; ".join(b[:160] for _t, b, _u in results[:3]))
        in_breve = in_breve or i18n.pick(f"Ho trovato {len(results)} risultati su {topic}.", f"I found {len(results)} results about {topic}.")
        spoken = first_sentences(in_breve)
        ws = self._ws()
        if ws is None:
            return spoken + i18n.pick(" (Per salvare le ricerche scegli una cartella nelle Impostazioni.)", " (To save research, pick a folder in Settings.)")
        sources = "\n".join(f"- {t} — {u}" if u else f"- {t}" for t, _b, u in results)
        if en:
            note = f"# Research: {topic}\n\n*{stamp()}*\n\n## In brief\n{in_breve}\n\n## Key points\n{punti or '- (no further details)'}\n\n## Sources\n{sources}"
            name = ws.new_file(f"Research - {topic}", note)
            return f"{spoken} I saved the research in \"{ws.display(name)}\"."
        note = f"# Ricerca: {topic}\n\n*{stamp()}*\n\n## In breve\n{in_breve}\n\n## Punti principali\n{punti or '- (nessun dettaglio in più)'}\n\n## Fonti\n{sources}"
        name = ws.new_file(f"Ricerca - {topic}", note)
        return f"{spoken} Ho salvato la ricerca in «{ws.display(name)}»."

    async def _lista(self, arg: str) -> str:
        """arg = 'nome della lista|voce' (es. 'della spesa|latte'): aggiunge una riga in fondo a «Lista …»."""
        ws = self._ws()
        if ws is None:
            return _no_workspace()
        which, _, item = arg.partition("|")
        which, item = which.strip(), item.strip(" .,")
        en = i18n.is_en()
        if not which:
            which = "shopping" if en else "della spesa"
        if not item:
            return f"{ASK}|LISTA|{which}|" + i18n.pick("Cosa aggiungo alla lista?", "What should I add to the list?")
        title = (_list_title_en(which) if en else f"Lista {which}")
        items = split_items(item)
        for it in items:
            ws.append(title, f"- [ ] {it}", header=title)
        t = title[0].lower() + title[1:]
        if en:
            said = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
            if len(items) > 1:
                return pick([f"Added {said} to the {t}.", f"Okay, {said} are on the {t}.", f"Done, I put {said} on the {t}."])
            return pick([f"Added \"{said}\" to the {t}.", f"Okay, \"{said}\" is on the {t}.", f"Done, I put \"{said}\" on the {t}."])
        said = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]
        if len(items) > 1:
            return pick([f"Aggiunti {said} alla {t}.", f"Ok, {said} sono nella {t}.", f"Fatto, ho messo {said} nella {t}."])
        return pick([f"Aggiunto «{said}» alla {t}.", f"Ok, «{said}» è nella {t}.", f"Fatto, ho messo «{said}» nella {t}."])

    async def _nota(self, arg: str) -> str:
        ws = self._ws()
        if ws is None:
            return _no_workspace()
        if not arg.strip():
            return f"{ASK}|NOTA||" + i18n.pick("Cosa scrivo nella nota?", "What should I write in the note?")
        name = i18n.pick("Note", "Notes")
        ws.append(name, f"- {stamp()} — {arg.strip()}", header=name)
        return pick(["Note saved.", "Done, I've noted it down.", "Okay, written."]) if i18n.is_en() else pick(["Nota salvata.", "Fatto, l'ho segnata.", "Ok, scritto."])

    async def _elenco(self, _arg: str) -> str:
        ws = self._ws()
        if ws is None:
            return _no_workspace()
        files = ws.list()
        if not files:
            return i18n.pick("La tua cartella è vuota.", "Your folder is empty.")
        from .tools import words_it
        n = len(files)
        if i18n.is_en():
            count = "only one file" if n == 1 else (f"{words_it(n)} files" if n < 60 else f"{n} files")
            return f"There are {count} in the folder. The most recent: " + ", ".join(ws.display(f) for f, _s in files[:5]) + "."
        count = "un solo file" if n == 1 else (f"{words_it(n)} file" if n < 60 else f"{n} file")
        return f"Nella cartella ci sono {count}. I più recenti: " + ", ".join(ws.display(f) for f, _s in files[:5]) + "."

    def _find(self, ws: Workspace, arg: str) -> str | None:
        return ws.find(arg)

    async def _leggi(self, arg: str) -> str:
        ws = self._ws()
        if ws is None:
            return _no_workspace()
        name = self._find(ws, arg)
        if name is None:
            return i18n.pick(f"Non trovo nessun file che somigli a «{arg.strip()}» nella tua cartella.", f"I can't find any file that looks like \"{arg.strip()}\" in your folder.")
        raw = ws.read(name)
        items = [m.group(1).strip() for m in re.finditer(r"^\s*-\s*\[ \]\s*(.+)$", raw, flags=re.M)]
        if items and i18n.is_en() and ws.display(name).lower().endswith("list"):
            title = ws.display(name)
            done = len(re.findall(r"^\s*-\s*\[x\]", raw, flags=re.M | re.I))
            said = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
            low = title[0].lower() + title[1:]
            return (f"On the {low} there's {said}." if len(items) == 1 else f"There are {_count_word(len(items))} things on the {low}: {said}.") + (f" You've already ticked off {done}." if done and len(items) > 1 else "")
        if items and ws.display(name).lower().startswith("lista"):                  # una lista della spesa si legge come la direbbe una persona
            title = ws.display(name)
            done = len(re.findall(r"^\s*-\s*\[x\]", raw, flags=re.M | re.I))
            said = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]
            return f"Nella {title[0].lower() + title[1:]} c'è {said}." if len(items) == 1 else f"Nella {title[0].lower() + title[1:]} ci sono {len(items)} cose: {said}." + (f" {done} le hai già spuntate." if done else "")
        text = plain_for_speech(raw, 650)
        if i18n.is_en():
            return f"\"{ws.display(name)}\": {text}" if text else f"\"{ws.display(name)}\" is empty."
        return f"«{ws.display(name)}»: {text}" if text else f"«{ws.display(name)}» è vuoto."

    async def _riassumi(self, arg: str) -> str:
        ws = self._ws()
        if ws is None:
            return _no_workspace()
        name = self._find(ws, arg)
        if name is None:
            return i18n.pick(f"Non trovo nessun file che somigli a «{arg.strip()}» nella tua cartella.", f"I can't find any file that looks like \"{arg.strip()}\" in your folder.")
        if self.generate is None:
            return i18n.pick("Per ora non riesco a riassumere.", "I can't summarise right now.")
        body = ws.read(name, 12000).strip()
        if not body:
            return i18n.pick(f"«{ws.display(name)}» è vuoto.", f"\"{ws.display(name)}\" is empty.")
        summary = (await self.generate(i18n.pick(SUMMARY_SYSTEM, SUMMARY_SYSTEM_EN), body, 260)).strip()
        return i18n.pick(f"«{ws.display(name)}»: ", f"\"{ws.display(name)}\": ") + first_sentences(plain_for_speech(summary, 600), 520)

    async def _apri(self, _arg: str) -> str:
        ws = self._ws()
        if ws is None:
            return _no_workspace()
        if sys.platform == "darwin":
            subprocess.run(["open", ws.root], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            os.startfile(ws.root)                                                      # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", ws.root], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return i18n.pick("Ho aperto la tua cartella.", "I opened your folder.")


_ART = re.compile(r"^(?:il|lo|la|l|i|gli|le|un|uno|una|dei|degli|delle|del|dello|della|dell)\s+", re.I)
_ART_EN = re.compile(r"^(?:the|a|an|some|more|another)\s+", re.I)


def _list_title_en(which: str) -> str:
    """«shopping» -> «Shopping list», «todo» -> «To-do list», «packing» -> «Packing list»."""
    w = re.sub(r"\s+list$", "", which.strip(), flags=re.I)
    w = {"todo": "to-do", "to do": "to-do", "groceries": "shopping", "grocery": "shopping"}.get(w.lower(), w)
    return f"{w[:1].upper()}{w[1:]} list"


def _count_word(n: int) -> str:
    from .tools import words_it
    return words_it(n) if n < 60 else str(n)


def split_items(item: str) -> list[str]:
    """«latte e uova» -> [latte, uova]; «il pane» -> [pane]. Si divide solo se ogni pezzo e' breve (1-3 parole): «pasta al forno con le melanzane» resta una voce."""
    en = i18n.is_en()
    art = _ART_EN if en else _ART
    parts = [p.strip(" .,;") for p in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+" if en else r"\s*,\s*|\s+e\s+", item) if p.strip(" .,;")]
    parts = [art.sub("", p) for p in parts]
    if len(parts) >= 2 and all(len(p.split()) <= 3 for p in parts):
        return parts
    return [art.sub("", item.strip())] if item.strip() else []


FILE_TOOLS = {"SCRIVI", "RICERCA", "LISTA", "NOTA", "ELENCO", "LEGGI", "RIASSUMI", "APRI", "SALVA"}
LONG_TOOLS = {"SCRIVI", "SALVA", "RICERCA", "RIASSUMI"}          # il chatbot lavora per qualche secondo: prima Aria dice che ci sta lavorando
