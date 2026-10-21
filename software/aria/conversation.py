"""Il ciclo di vita di Aria: attesa -> ascolto -> pensiero -> parola, con interruzioni, finestra di follow-up e strumenti."""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
from typing import AsyncIterator

import numpy as np

from .audio import CHIME_DONE, CHIME_ERROR, CHIME_TIMER, CHIME_WAKE, tone
from . import dialog, i18n, intent, intent_en, learn, rhythm, style
from .state import Hub, State
from .filetools import LONG_TOOLS
from .powers import ASK, CONFIRM, PASS
from .textutil import ToolCall, normalize
from .tools import MODEL_TOOLS, NEED_CITY, REFUSED, REFUSED_EN, SPEAK_VERBATIM
from .textutil import SentenceChunker, TagFilter, is_stop_command, matches_phrase, strip_emoji, strip_think
from .speech import shape_pause, speechify, trim_silence
from .vad import Endpointer

log = logging.getLogger("aria.conv")
FRAME_MS = 32.0
FRAME_SAMPLES = 512                                                  # 32 ms a 16 kHz
FILLERS = ["Mh, vediamo.", "Allora…", "Un attimo.", "Aspetta che guardo.", "Dunque."]
TOOL_FILLERS = ["Aspetta che controllo.", "Vediamo un attimo.", "Guardo subito."]
ASK_NAME = ["A proposito, non ci siamo ancora presentati: come ti chiami?", "Ah, dimenticavo: come ti chiami? Mi piacerebbe saperlo.",
            "Piuttosto, io non so ancora il tuo nome. Come ti chiami?"]
ASK_CITY = ["E dimmi, di che città sei? Così so che tempo fa dove stai.", "Mi dici in che città abiti? Così ti so dire il meteo giusto."]
SLOW_LABEL = {"SCRIVI": "Scrivo il documento", "SALVA": "Scrivo il documento", "RICERCA": "Faccio la ricerca", "RIASSUMI": "Leggo e riassumo", "DOCUMENTO": "Preparo il documento",
              "BRIEFING": "Preparo il riepilogo", "AGENDA": "Guardo l'agenda", "SCHERMO": "Guardo lo schermo"}
SLOW_TOOLS = LONG_TOOLS | {"DOCUMENTO", "BRIEFING", "AGENDA", "SCHERMO"}          # lavorano qualche secondo: prima Aria dice che ci sta lavorando
NEEDS_FOLDER = {"SCRIVI", "RIASSUMI", "DOCUMENTO"}                      # senza cartella rispondono subito "scegli una cartella": niente "ci lavoro"
_YES = re.compile(r"^(?:si|certo|ok|okay|va bene|esegui|eseguila|fallo|fai pure|confermo|conferma|procedi|vai|sicuro|assolutamente|per favore|volentieri)\b")
_NO = re.compile(r"^(?:no|non|annulla|annullala|lascia stare|lascia perdere|niente|neanche|ferma|aspetta)\b")
WORKING = ["Va bene, ci lavoro un momento.", "Ok, mi metto al lavoro: ci vogliono pochi secondi.", "Certo, dammi qualche secondo."]
WORKING_SCREEN = ["Guardo lo schermo, un attimo.", "Dammi un secondo, ci guardo.", "Ok, do un'occhiata allo schermo."]
WORKING_DOC = ["Va bene, lo scrivo per bene, controllo e lo rileggo: ci vuole circa un minuto.", "Ok, cerco le informazioni giuste, scrivo il documento e lo rivedo: dammi un minutino.", "Certo, lo scrivo con calma e lo ricontrollo: ci metto un po'."]
VOICE_SAMPLE = "Eccomi, sono Aria. Ti piace questa voce?"     # senza "hey Aria": non deve far scattare l'attivazione dal microfono
# ---- inglese (la lingua si sceglie nelle Impostazioni, vedi i18n.py): le stesse frasi, in inglese
FILLERS_EN = ["Hmm, let's see.", "Well…", "One moment.", "Let me look.", "So."]
TOOL_FILLERS_EN = ["Let me check.", "One moment, let's see.", "Looking now."]
ASK_NAME_EN = ["By the way, we haven't really met: what's your name?", "Oh, I forgot: what's your name? I'd like to know.", "Actually, I don't know your name yet. What is it?"]
ASK_CITY_EN = ["And tell me, what city are you in? That way I know the weather where you are.", "Which city do you live in? Then I can give you the right forecast."]
SLOW_LABEL_EN = {"SCRIVI": "Writing the document", "SALVA": "Writing the document", "RICERCA": "Doing the research", "RIASSUMI": "Reading and summarizing", "DOCUMENTO": "Preparing the document",
                 "BRIEFING": "Preparing the summary", "AGENDA": "Checking the agenda", "SCHERMO": "Looking at the screen"}
_YES_EN = re.compile(r"^(?:yes|yeah|yep|yup|sure|of course|ok|okay|alright|go ahead|do it|run it|confirm|confirmed|proceed|go|absolutely|please do|please|sounds good|why not|certainly|definitely|fine)\b")
_NO_EN = re.compile(r"^(?:no|nope|nah|not|don t|do not|cancel|never mind|forget it|leave it|skip it|nothing|neither|stop|wait|hold on)\b")
WORKING_EN = ["Okay, give me a moment on this.", "Sure, getting to work: it only takes a few seconds.", "Of course, give me a few seconds."]
WORKING_SCREEN_EN = ["Looking at the screen, one moment.", "Give me a second, I'm taking a look.", "Okay, let me glance at the screen."]
WORKING_DOC_EN = ["Okay, I'll write it properly, check it and read it over: it takes about a minute.", "Sure, I'll look up the right information, write the document and review it: give me a minute.",
                  "Of course, I'll write it carefully and double-check it: it'll take a little while."]
VOICE_SAMPLE_EN = "Here I am, I'm Aria. Do you like this voice?"


def _fillers() -> list[str]:
    return FILLERS_EN if i18n.is_en() else FILLERS


def _tool_fillers() -> list[str]:
    return TOOL_FILLERS_EN if i18n.is_en() else TOOL_FILLERS


def _voice_sample() -> str:
    return VOICE_SAMPLE_EN if i18n.is_en() else VOICE_SAMPLE


def _working(kind: str = "") -> list[str]:
    if i18n.is_en():
        return WORKING_DOC_EN if kind == "doc" else WORKING_SCREEN_EN if kind == "screen" else WORKING_EN
    return WORKING_DOC if kind == "doc" else WORKING_SCREEN if kind == "screen" else WORKING
ASK_MAX = 3                                      # quante volte, in tutto, chiede la stessa cosa prima di smettere
ASK_EVERY_H = 20                                 # e al massimo una volta al giorno


_END = re.compile(r"[.!?…][\"»)]*$")


def _clip_sentences(chunk: str, cap: int, done: int, open_frag: bool) -> tuple[str, int, bool, bool]:
    """Un pezzo di risposta tagliato in modo da non superare `cap` frasi COMPLETE. Il primo pezzo puo' finire a una virgola (per partire prima):
    quel frammento non conta come frase e la frase si completa col pezzo dopo. Restituisce (testo, frasi_complete, frase_aperta, tetto_raggiunto)."""
    take: list[str] = []
    for part in [p for p in re.split(r"(?<=[.!?…])\s+", chunk.strip()) if p]:
        if done >= cap and not open_frag:
            break
        take.append(part)
        if _END.search(part):
            done += 1
            open_frag = False
        else:
            open_frag = True
    return " ".join(take), done, open_frag, done >= cap and not open_frag


def alternating(history: list[dict]) -> list[dict]:
    """I template di Gemma pretendono utente/assistente a turni: unisce i messaggi consecutivi dello stesso ruolo (es. risposta + domanda «come ti chiami?»)
    e toglie quelli all'inizio che non sono dell'utente (il saluto di Aria): il chatbot non ne ha bisogno."""
    out: list[dict] = []
    for m in history:
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {"role": m["role"], "content": (out[-1]["content"].rstrip() + " " + m["content"].lstrip()).strip()}
        else:
            out.append({"role": m["role"], "content": m["content"]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def strip_wake(text: str, phrase: str) -> str:
    """Toglie 'hey aria' dall'inizio della trascrizione (anche storpiato: 'ehi aria', 'hey arya').
    Un 'ciao' da solo NON viene tolto: e' un saluto vero."""
    text = re.sub(r"(?<=[A-Za-z])([,.!?;:])(?=[A-Za-z])", r"\1 ", text)        # «Hey Aria,what time is it»: la virgola attaccata non deve mangiare la prima parola del comando
    words = text.split()
    n = len(phrase.split())
    head = " ".join(words[:n])
    thr = 0.6 if len(words) >= n else 0.85
    if words and matches_phrase(head, phrase, thr):
        return " ".join(words[n:]).lstrip(",.!? ")
    return text


def rms_level(frame: np.ndarray, gain: float = 10.0) -> float:
    x = frame.astype(np.float32) / 32768.0
    return float(min(1.0, np.sqrt(np.mean(x * x)) * gain))


class Aria:
    def __init__(self, cfg: dict, hub: Hub, mic, speaker, wake, vad, router, tools, memory, persona_text: str):
        from .persona import build_system
        self.cfg, self.hub, self.mic, self.speaker = cfg, hub, mic, speaker
        self.wake, self.vad, self.router, self.tools, self.memory = wake, vad, router, tools, memory
        self.persona = persona_text
        self._build_system = build_system
        self.ring: deque = deque(maxlen=64)                       # ~2 s di audio recente (per verificare il wake word)
        self.fillers: list[tuple[np.ndarray, int]] = []
        self.history: list[dict] = []
        self.sys_prompt = ""
        self.t = cfg["turn"]
        self.in_session = False
        self.pending_confirm: ToolCall | None = None   # azione che aspetta il si' dell'utente (es. eseguire una scorciatoia)
        self.pending_slot: ToolCall | None = None      # richiesta lasciata a meta' ("ricordami di chiamare Mario" -> "per quando?"): la prossima frase la completa
        self._list_ctx: tuple[str, int] | None = None  # (lista, numero del turno) dell'ultima voce aggiunta: «aggiungi anche le uova» continua la stessa lista
        self._turn_no = 0
        self._said_now: list[str] = []                                   # le frasi della risposta in corso (per l'interruzione a voce)
        self._bi_stt = None                                              # il riconoscimento usato per l'interruzione (None = da creare, False = non disponibile)
        self._voice_check = None                                         # il «revisore» della voce (None = da creare, False = non disponibile)
        self._vad_gain = 2.0                                             # volume dato al rilevatore di voce (si adatta a quanto parla piano l'utente)
        self._name_turn = -99                                            # l'ultima volta che ha detto il nome dell'utente (a voce o nella risposta): una persona non lo ripete a ogni frase
        self._last_query: str | None = None             # l'ultima ricerca web (per «fammi una ricerca e salvala»)
        self._last_power: ToolCall | None = None        # l'ultimo promemoria/evento/lista/nota creato (per «no, come promemoria», «cambia X con Y»)
        self.pending: str | None = None               # domanda fatta da Aria e in attesa di risposta: "name" | "city"
        self._weather_day: str | None = None          # "oggi"/"domani": il meteo chiesto prima di sapere la citta'
        self._preview: asyncio.Future | None = None   # anteprima della voce appena scelta
        self._asked_session = False                   # al massimo una domanda personale per conversazione
        self._pause_why: str | None = None             # perche' il microfono e' chiuso: 'battery' (risparmio) o 'sleep' (il Mac dorme)
        self._paused = False                          # a batteria con lo schermo spento il microfono si chiude (vedi _power_saver): il Mac puo' andare in stop
        self.idle_vad = None                          # rilevatore di voce leggero per l'attesa di «hey aria» (vad.make_idle_vad); None = quello normale
        self._last_active = time.monotonic()          # l'ultima volta che l'utente ha chiamato Aria (serve a non svegliare il Mac inutilmente quando sta ferma)
        self._voice_wake = False                      # chiamata a voce («hey aria»): risponde con un saluto; col tasto no
        self._last_end: float | None = None           # quando e' finita l'ultima conversazione (per «rieccomi»)
        self._last_closing: str | None = None         # l'ultimo saluto/ringraziamento detto: non lo ripete di fila
        self._said_goodbye = False
        self._hint = ""                               # novita' da dire al modello solo per questo turno ("si e' appena presentato")
        self._rhythm_prev: str | None = None
        self._rhythm: rhythm.Turn | None = None        # la «mossa» di questo turno (parere, spiegazione a cipolla, traino…): la decide _refresh_prompt, la usa reply_events
        self.pending_text: str | None = None          # comando detto insieme al wake word (modalità 'stt')
        self.wake_stt = None                          # riconoscitore leggero (Whisper tiny/base) per ascoltare "hey aria"
        self.muted = False                            # microfono "silenziato": il wake word e' spento, il tasto funziona
        self._wake_req = False
        self._stop_evt = asyncio.Event()
        self._tool_busy = False                       # uno strumento lento (un documento) sta lavorando
        self._aec_dbg: list = []
        hub.on_command(self._on_command)
        if getattr(router, "revive", None) is None:
            router.revive = self._revive
        if getattr(tools, "generate", None) is None:
            tools.generate = self._generate_text                                # per scrivere testi e riassunti nella cartella di Aria
        if getattr(tools, "progress", "n/a") is None:
            tools.progress = hub.progress                                       # l'avanzamento dei documenti diventa la barra in basso nell'overlay

    async def _run_tool(self, call: ToolCall) -> str:
        """Esegue uno strumento; se e' lento (un documento, una ricerca) l'overlay mostra una barra di caricamento in basso, che sparisce a lavoro finito."""
        slow = call.name in SLOW_TOOLS
        self._tool_busy = slow
        if slow:
            self.hub.progress((SLOW_LABEL_EN if i18n.is_en() else SLOW_LABEL).get(call.name, i18n.pick("Ci sto lavorando", "Working on it")))                       # senza sapere quanto manca: barra che scorre (i documenti poi la precisano)
        try:
            return await self.tools.run(call)
        finally:
            self._tool_busy = False
            if slow:
                self.hub.progress_done()

    # ---------------------------------------------------------------- comandi (tasto, menu, app)
    def _on_command(self, cmd: dict) -> None:
        name = cmd.get("cmd")
        if name == "wake" and self.hub.state in (State.SPEAKING, State.THINKING, State.LISTENING):
            name = "stop"                                                    # l'app puo' avere uno stato vecchio («riposo») mentre Aria parla: il tasto vale lo stesso come stop
        if name == "wake":
            if self._paused:
                self._pause_listening(False)                                 # (a batteria con lo schermo spento: il tasto la risveglia subito)
            self._wake_req = True
        elif name == "stop":
            self._stop_evt.set()
            self.speaker.stop()
        elif name == "screen_perm":                                         # diagnosi: Aria ha il permesso «Registrazione schermo»? (ask=true lo chiede a macOS)
            self._bg_once(self._screen_perm(bool(cmd.get("ask"))))
        elif name in ("mute", "unmute"):
            self.muted = name == "mute"
            self.hub.set_info(muted=self.muted)
        elif name == "voice" and cmd.get("name"):
            for tts in self.router.objects("tts"):
                if hasattr(tts, "set_voice"):
                    try:
                        tts.set_voice(cmd["name"])
                    except Exception as e:                                  # noqa: BLE001
                        log.warning("voce '%s' non disponibile: %s", cmd["name"], e)
            self.hub.set_info(voice=cmd["name"])
            if self.t.get("filler_after_ms"):
                self._bg_once(self._prepare_fillers())                      # rigenera gli intercalari con la voce nuova
            self._start_voice_preview()                                     # e la fa sentire subito: si capisce se piace

    async def _screen_perm(self, ask: bool) -> None:
        try:
            ok = await self.tools._ocr_helper().permission(ask=ask)
            log.info("permesso Registrazione schermo (%s): %s", "richiesto a macOS" if ask else "controllo", "CONCESSO" if ok else "NEGATO")
        except Exception as e:                                                  # noqa: BLE001
            log.warning("permesso Registrazione schermo: controllo non riuscito (%s)", str(e)[:120])

    # ---------------------------------------------------------------- anteprima della voce
    def _start_voice_preview(self) -> None:
        if self.in_session:                                                 # sta parlando con l'utente: niente interruzioni
            return
        if self._preview is not None and not self._preview.done():          # ha cambiato voce di nuovo: la prova precedente si ferma
            self._preview.cancel()
            self.speaker.stop()
        self._preview = asyncio.ensure_future(self._voice_preview())

    async def _voice_preview(self) -> None:
        ticker = None
        try:
            pcm, sr = await self.router.synthesize(_voice_sample())
            if self.in_session:
                return
            log.info("ANTEPRIMA VOCE: %s", self._current_voice())
            self.hub.transcript("aria", _voice_sample(), final=False)
            self.hub.set_state(State.SPEAKING)                              # la schermata compare con la rete che "parla"
            ticker = asyncio.create_task(self._speaking_level())
            self.speaker.play(pcm, sr)
            await self.speaker.wait_done()
        except asyncio.CancelledError:
            self.speaker.stop()
            raise
        except Exception as e:                                              # noqa: BLE001
            log.warning("anteprima della voce non riuscita: %s", e)
        finally:
            if ticker:
                ticker.cancel()
            if not self.in_session and self.hub.state == State.SPEAKING:
                self.hub.set_state(State.IDLE)

    async def _tts(self, text: str):
        """Il testo diventa voce: numeri e simboli a parole, e il silenzio dopo la frase regolato dalla punteggiatura (il ritmo del parlato)."""
        spoken = speechify(text)
        if not re.search(r"[A-Za-zÀ-ÿ0-9]", spoken):                           # niente da dire (solo simboli/parentesi): un attimo di silenzio, non un errore della voce
            return np.zeros(int(0.15 * self.cfg["audio"]["output_rate"]), dtype=np.int16), int(self.cfg["audio"]["output_rate"])
        from . import voicecheck
        chunk = self.router.tts_chunk(int(self.cfg.get("human", {}).get("tts_chunk_chars", 30)))
        pcm, sr = await self._synth_parts(voicecheck.split_long(spoken, chunk))           # le frasi lunghe Pocket TTS le taglia: a pezzi no (la voce naturale regge frasi intere)
        pcm, sr = await self._verify_voice(spoken, pcm, sr)
        if self.cfg.get("human", {}).get("pauses", True):
            pcm = trim_silence(pcm, sr, lead_ms=40.0, tail_ms=60.0)                  # via anche il silenzio davanti (0,4-0,6 s con Pocket TTS): una risposta parte prima e le frasi non si staccano
            pcm = shape_pause(pcm, sr, text, min_gap_ms=self._listen_gap_ms())
        return pcm, sr

    def _listen_gap_ms(self) -> int:
        """Con le casse (senza cuffie) l'utente puo' interrompere solo quando Aria e' zitta: tra una frase e l'altra lascia un respiro piu' lungo, come fa una persona."""
        a = self.cfg["audio"]
        if a.get("barge_in") or not a.get("barge_in_gaps", True) or getattr(self.mic, "cleaned", False):
            return 0                                                         # (col filtro eco del Mac l'interruzione non aspetta le pause: ritmo normale)
        return int(self.cfg.get("human", {}).get("listen_gap_ms", 480))

    async def _synth_parts(self, parts: list[str]):
        """Sintetizza i pezzi di una frase e li unisce con un respiro (piu' lungo dopo la virgola)."""
        if len(parts) == 1:
            return await self.router.synthesize(parts[0])
        wavs, sr = [], 0
        for i, part in enumerate(parts):
            pcm, sr = await self.router.synthesize(part)
            w = trim_silence(np.asarray(pcm).reshape(-1), sr)                 # senza il silenzio che il sintetizzatore lascia: la pausa la decide la punteggiatura (prima ogni pezzo aggiungeva ~1,5 s)
            if i:
                comma = 0.34 if self._listen_gap_ms() else 0.20                     # (con le casse le virgole sono anche i punti dove l'utente puo' inserirsi)
                wavs.append(np.zeros(int(sr * (comma if parts[i - 1][-1:] in ",;:" else 0.07)), dtype=w.dtype))
            wavs.append(w)
        return np.concatenate(wavs), sr

    async def _verify_voice(self, spoken: str, pcm: np.ndarray, sr: int):
        """Riascolta la frase appena sintetizzata (riconoscimento integrato del Mac) e, se la voce ha tagliato la fine, la rifa' (al massimo `voice_retries` volte, tiene la migliore)."""
        h = self.cfg.get("human", {})
        if not h.get("verify_voice", True) or self._voice_check is False or len(spoken.split()) < 3:
            return pcm, sr
        if re.match(r"^In (?:inglese|francese|spagnolo|tedesco|portoghese|olandese|latino|rumeno|polacco|svedese|catalano):", spoken):
            return pcm, sr                                                      # una traduzione: il riascolto e' in italiano e non capirebbe niente
        from . import voicecheck
        from .audio import resample
        if self._voice_check is None:
            from .stt import AppleSTT, apple_helper_path
            import os
            if not os.path.exists(apple_helper_path()):
                self._voice_check = False
                log.info("controllo della voce non attivo: manca il programma di supporto di Apple")
                return pcm, sr
            self._voice_check = AppleSTT({})
        best, best_score = (pcm, sr), -9.0
        t0 = time.monotonic()
        retries = int(h.get("voice_retries", 1))
        for attempt in range(1 + retries):
            try:
                heard = await self._voice_check.transcribe(resample(pcm, sr, 16000), 16000)
            except Exception as e:                                       # noqa: BLE001
                self._vc_fails = getattr(self, "_vc_fails", 0) + 1
                log.warning("controllo della voce non riuscito (%s)", str(e)[:120])
                getattr(self._voice_check, "close", lambda: None)()          # riparte pulito alla prossima frase; dopo 5 errori di fila si spegne
                if self._vc_fails >= 5:
                    self._voice_check = False
                return best[0], best[1]
            self._vc_fails = 0
            ok, sc, missing = voicecheck.score(spoken, heard, self._user_name())
            if sc > best_score:
                best, best_score = (pcm, sr), sc
            if ok:
                return pcm, sr
            log.info("voce: frase tagliata (mancano %s) -> la rifaccio [%r]", missing or "parole", spoken[:50])
            if time.monotonic() - t0 > 3.0 or attempt >= retries:
                break
            fine = max(20, int(self.router.tts_chunk(int(h.get("tts_chunk_chars", 30))) * 0.65))             # rifatta uguale verrebbe tagliata uguale: stavolta a pezzi piu' corti
            pcm, sr = await self._synth_parts(voicecheck.split_long(spoken, fine))
        return best[0], best[1]

    # ---------------------------------------------------------------- ciclo principale
    async def _audio_watchdog(self) -> None:
        """Se colleghi o scolleghi gli AirPods (o il microfono smette di mandare audio) riapre microfono e casse sul dispositivo giusto: prima Aria restava sorda fino al riavvio.

        Con lo schermo spento (Mac chiuso, o uno dei risvegli notturni «DarkWake» di macOS ogni ~15 minuti) il microfono NON manda audio, ed e' normale: riaprirlo non serve a niente,
        anzi (osservato: ~500 riaperture in 53 minuti, una ogni 6 secondi; ognuna accende e spegne l'indicatore del microfono di macOS e lo tiene sveglio con «PreventUserIdleSystemSleep»:
        il Mac non tornava a dormire e la barra dei menu, MenuBarAgent/ControlCenter, restava al 100 % fino al riavvio). Quindi: schermo spento e microfono muto -> si CHIUDE il microfono
        (il Mac puo' dormire) e si riapre quando lo schermo si riaccende (_power_saver); e, se proprio serve riaprire, a intervalli sempre piu' lunghi."""
        from . import audio, power
        if not hasattr(self.mic, "last_frame") or not hasattr(self.speaker, "start"):
            return                                                          # (i test e il collaudo da file non hanno schede audio)
        ids = audio.default_devices()
        a = self.cfg["audio"]
        follow = a.get("input_device") is None and a.get("output_device") is None
        bad = 0                                                             # quante volte di fila ha dovuto riaprire: se il sistema audio e' bloccato non lo si martella ogni 7 secondi
        reopened = time.monotonic()                                         # (dopo una riapertura last_frame vale «adesso» per finta: un microfono ancora muto sembra sano per 4 secondi, e il conteggio si azzerava)
        while True:
            await asyncio.sleep(3.0)
            if self._paused:
                continue                                                    # (microfono chiuso apposta: per la batteria o perche' lo schermo e' spento)
            now = audio.default_devices()
            why = audio.audio_problem(ids, now, time.monotonic() - self.mic.last_frame, self.speaker.playing or self.hub.state == State.SPEAKING, follow)
            if not why:
                if bad and time.monotonic() - reopened > 60.0:
                    bad = 0                                                 # solo dopo un minuto di audio vero ci si dimentica dei guasti
                continue
            if why == "ferma" and not self.in_session and power.display_asleep() is True:
                self._pause_listening(True, "sleep")                        # schermo spento e microfono muto: sta dormendo (o e' un risveglio notturno); chiudo e lascio dormire
                continue
            if bad:
                await asyncio.sleep(min(300.0, 5.0 * 2 ** bad))
            bad += 1
            log.warning("audio: %s -> riapro microfono e casse sul dispositivo predefinito", "il microfono non manda piu' niente" if why == "ferma" else "il dispositivo predefinito e' cambiato")
            try:
                await asyncio.to_thread(audio.reinit_audio, self.mic, self.speaker)
                reopened = time.monotonic()
                if getattr(self, "_aec", None) is not None:
                    self._aec.reset()                                       # un'altra stanza/altre casse: il filtro riparte
                ids = audio.default_devices()
            except Exception as e:                                          # noqa: BLE001
                log.warning("audio: non riesco a riaprire i dispositivi (%s)", str(e)[:120])
                ids = now
                await asyncio.sleep(10)

    async def _open_mic(self) -> None:
        """All'avvio il microfono puo' non aprirsi (al primo avvio macOS non ha ancora avuto il permesso, o la scheda audio e' occupata): si riprova a intervalli invece di cadere e
        ripartire con un errore ogni pochi secondi (osservato: 109 ripartenze di fila finche' il permesso non e' stato dato)."""
        n = 0
        while True:
            try:
                await self.mic.start()
                if n:
                    log.info("microfono aperto dopo %d tentativi", n)
                return
            except Exception as e:                                          # noqa: BLE001
                n += 1
                if n == 1 or n % 12 == 0:
                    log.warning("microfono non disponibile (%s): riprovo ogni pochi secondi. Se e' il primo avvio, dai il permesso Microfono ad Aria in Impostazioni di Sistema > Privacy e sicurezza.", str(e)[:100])
                await asyncio.sleep(min(10.0, 1.0 + n))

    async def run(self) -> None:
        await self._open_mic()
        self.speaker.start()
        self._bg = [asyncio.create_task(c) for c in (self._audio_watchdog(), self._power_saver(), self._prepare_fillers(), self._warm_screen(), self._prime_llm())]   # (riferimenti tenuti: asyncio tiene i compiti solo con riferimenti deboli)
        if hasattr(self.tools, "restore_timers"):
            try:
                n = await self.tools.restore_timers()                       # timer e sveglie rimasti da prima della chiusura
                if n:
                    log.info("riarmati %d timer", n)
            except Exception as e:                                          # noqa: BLE001
                log.warning("timer non riarmati: %s", e)
        log.info("Aria e' pronta: di' '%s'", self.cfg["wake"]["phrase"])
        try:
            while True:
                self._mic_filter(False)                                      # a riposo il microfono normale (il filtro eco costa batteria)
                await self.wait_for_wake()
                self._last_active = time.monotonic()
                self._mic_filter(True)                                       # in conversazione il filtro eco: si puo' interrompere Aria a voce
                await self.session()
        finally:
            await self.mic.stop()
            self.speaker.close()

    async def _power_saver(self, every: float = 5.0, after: float = 60.0) -> None:
        """A batteria, con lo schermo spento da un minuto e Aria a riposo, chiude il microfono: con il microfono aperto macOS non manda mai il Mac in stop da solo
        (coreaudiod lo tiene sveglio), e un Mac sveglio tutta la notte a batteria e' il consumo piu' grande di tutti. Riapre appena lo schermo si accende, il Mac va
        all'alimentatore o premi il tasto. `audio: sleep_on_battery: false` lo spegne (Aria ascolta sempre).
        Qui si riapre anche il microfono chiuso dal guardiano audio perche' il Mac dormiva (`_pause_why == "sleep"`): appena lo schermo si riaccende."""
        from . import power
        if not hasattr(self.mic, "close_sync") or not hasattr(self.speaker, "start"):
            return
        from . import profiles as P
        battery_rule = bool(self.cfg["audio"].get("sleep_on_battery", True))
        since = None
        while True:
            await asyncio.sleep(every)
            try:
                if self._paused and self._pause_why == "sleep":
                    if power.display_asleep() is not True:
                        self._pause_listening(False)                        # lo schermo e' tornato: si ascolta di nuovo
                    continue
                if not battery_rule:
                    continue
                idle = not self.in_session and self.hub.state == State.IDLE and not self.speaker.playing
                allowed = P.get_powers(self.cfg.get("_config_path")).get("battery_rest", True) if self.cfg.get("_config_path") else True      # (interruttore nelle Impostazioni)
                save = idle and allowed and power.on_battery() is True and power.display_asleep() is True
                if save:
                    since = since or time.monotonic()
                    if not self._paused and time.monotonic() - since >= after:
                        self._pause_listening(True)
                else:
                    since = None
                    if self._paused and (not allowed or power.on_battery() is not True or power.display_asleep() is not True):
                        self._pause_listening(False)
            except Exception as e:                                          # noqa: BLE001
                log.warning("risparmio batteria: %s", str(e)[:100])

    def _pause_listening(self, on: bool, why: str = "battery") -> None:
        if on == self._paused:
            return
        try:
            if on:
                self.mic.close_sync()
                self._pause_why = why
                if why == "sleep":
                    log.info("schermo spento e microfono muto: il Mac dorme -> chiudo il microfono (si riapre con lo schermo)")
                else:
                    log.info("risparmio batteria: schermo spento e Mac a batteria -> smetto di ascoltare (il Mac puo' andare in stop)")
            else:
                self.mic.start_sync()
                self.mic.last_frame = time.monotonic()
                log.info("riprendo ad ascoltare")
                self._pause_why = None
            self._paused = on
            self.hub.set_info(paused=on)
        except Exception as e:                                              # noqa: BLE001
            log.warning("non riesco a %s il microfono (%s)", "chiudere" if on else "riaprire", str(e)[:100])

    def _bg_once(self, coro) -> None:
        """Un lavoro in sottofondo che finisce da solo: il riferimento si tiene finche' non ha finito."""
        tasks = self.__dict__.setdefault("_bg_tasks", set())
        t = asyncio.create_task(coro)
        tasks.add(t)
        t.add_done_callback(tasks.discard)

    def _mic_filter(self, on: bool) -> None:
        fn = getattr(self.mic, "engage" if on else "release", None)
        if fn is not None:
            try:
                fn()
            except Exception as e:                                          # noqa: BLE001
                log.warning("filtro eco del microfono: %s", str(e)[:100])

    async def _warm_screen(self) -> None:
        """Se l'OCR del Mac e' acceso, lo tiene «caldo»: macOS prepara il suo modello alla prima lettura (anche un minuto: misurato 59 s dopo ~10 minuti di pausa, 0,3 s subito dopo) e,
        se non lo si usa per un po', lo butta via. Una lettura minuscola ogni paio di minuti (0,1 s) fa si' che la prima richiesta vera sia veloce."""
        await asyncio.sleep(20)                                                 # dopo che il chatbot si e' caricato
        every = float((self.cfg.get("screen") or {}).get("keep_warm_s", 150))
        while True:
            try:
                from . import power
                if (time.monotonic() - self._last_active < 1800.0 and getattr(self.tools, "_screen_engine", lambda: None)() == "mac"           # (solo se la usi: a riposo non sveglia il Mac ogni due minuti)
                        and power.display_asleep() is not True                       # (mai nei risvegli notturni: il clock monotonico non conta il tempo di sonno, la «mezz'ora» durerebbe tutta la notte)
                        and self.tools._ocr_helper().available() and not self._tool_busy):
                    await self.tools._ocr_helper().warmup()
            except Exception as e:                                              # noqa: BLE001
                log.info("OCR del Mac: riscaldamento saltato (%s)", str(e)[:100])
            await asyncio.sleep(max(30.0, every))

    async def _prime_llm(self) -> None:
        """Se il chatbot e' interno (MLX), tiene gia' in cache il carattere di Aria: la prima risposta non lo rielabora."""
        import datetime as dt
        for _ in range(120):                                         # aspetta che il chatbot sia stato creato e caricato dal riscaldamento
            llms = [o for o in self.router.objects("llm") if hasattr(o, "prime")]
            if llms and getattr(llms[0], "model", None) is not None:
                break
            await asyncio.sleep(1.0)
        else:
            return
        a = self._build_system(self.persona, self.cfg, "", dt.datetime(2000, 1, 3, 4, 5))
        b = self._build_system(self.persona, self.cfg, "", dt.datetime(2031, 12, 29, 21, 47))
        for llm in llms:
            try:
                n = await llm.prime(a, b)
                log.info("chatbot scaldato: %d token del carattere di Aria in cache", n)
            except Exception as e:                                   # noqa: BLE001
                log.warning("scaldamento del chatbot non riuscito: %s", e)

    def _current_voice(self) -> str:
        for tts in self.router.objects("tts"):
            if getattr(tts, "voice", None):
                return str(tts.voice)
        return ""

    async def _prepare_fillers(self) -> None:
        """Intercalari parlati ("Mh, vediamo."): solo se turn.filler_after_ms > 0. Sono legati alla voce con cui sono stati generati."""
        self.fillers = []
        if not self.t.get("filler_after_ms"):
            return
        voice = self._current_voice()
        for f in _fillers() + _tool_fillers():
            try:
                self.fillers.append((f, *await self.router.synthesize(f), voice))
            except Exception as e:                                  # noqa: BLE001
                log.debug("filler non generato (%s)", e)
                return

    def _filler(self, tool: bool = False):
        v = self._current_voice()
        pool = [x for x in self.fillers if (x[0] in _tool_fillers()) == tool and x[3] == v]      # mai con una voce diversa da quella scelta
        return random.choice(pool) if pool else None

    # ---------------------------------------------------------------- attesa
    async def wait_for_wake(self) -> None:
        self.hub.set_state(State.IDLE)
        self.hub.set_level(0.0)
        self.ring.clear()
        self.mic.flush()
        if self.cfg["wake"].get("mode") == "stt":
            return await self._wait_wake_stt()
        async for frame in self.mic.frames():
            self.ring.append(frame)
            if self._wake_req:
                self._wake_req = False
                self._voice_wake = False
                self.hub.set_state(State.LISTENING)
                return
            if not self.muted and self.wake.feed(frame) and await self._verify_wake():
                self._voice_wake = True
                return

    def _boost(self, frame: np.ndarray) -> np.ndarray:
        """Il fotogramma per il rilevatore di voce: se l'utente parla piano lo si alza (a Whisper l'audio arriva comunque normalizzato). Senza, il rilevatore
        si accorge della voce con 200-300 ms di ritardo e l'inizio della parola va perso."""
        g = self.cfg.get("vad", {}).get("gain", "auto")
        g = self._vad_gain if g == "auto" else float(g)
        if g <= 1.05:
            return frame
        return np.clip(frame.astype(np.float32) * g, -32768, 32767).astype(np.int16)

    def _learn_level(self, audio: np.ndarray) -> None:
        """Dopo ogni frase: quanto parla piano? (rms in dB) -> il volume dato al rilevatore la prossima volta, tra 1x e 4x."""
        x = audio.astype(np.float32) / 32768.0
        if len(x) == 0:
            return
        rms_db = 20 * float(np.log10(float(np.sqrt(np.mean(x * x))) + 1e-9))
        target = max(1.0, min(4.0, 10 ** ((-30.0 - rms_db) / 20)))
        self._vad_gain = 0.5 * self._vad_gain + 0.5 * target

    async def _wait_wake_stt(self) -> None:
        """Senza modello addestrato: segmenta il parlato con il VAD, trascrive ogni frase breve e cerca 'hey aria'.
        Piu' pesante del modello dedicato, ma funziona subito. Il resto della frase diventa il primo comando."""
        phrase = self.cfg["wake"]["phrase"]
        ep = Endpointer(FRAME_MS, 96, 500, 200, 4.0, 0, self.cfg["vad"]["threshold"], 0.35)
        vad = self.idle_vad or self.vad                                  # (quello leggero: qui si aspetta tutto il giorno)
        vad.reset()
        preroll: deque = deque(maxlen=int(self.t["preroll_ms"] / FRAME_MS))
        frames: list[np.ndarray] = []
        speaking = False
        async for frame in self.mic.frames():
            if self._wake_req:
                self._wake_req = False
                self._voice_wake = False
                self.hub.set_state(State.LISTENING)
                return
            if self.muted:
                continue
            ev = ep.push(vad.prob(self._boost(frame)))
            if not speaking:
                preroll.append(frame)
            if ev == "start":
                speaking, frames = True, list(preroll)
            elif speaking:
                frames.append(frame)
            if ev == "end":
                speaking = False
                try:
                    stt = self.wake_stt or self.router
                    text = await stt.transcribe(np.concatenate(frames), self.cfg["audio"]["input_rate"])
                except Exception as e:                                  # noqa: BLE001
                    log.warning("riconoscimento (attesa) fallito: %s", e)
                    ep.reset()                                          # (senza: l'Endpointer restava in «fine frase» e ritentava a OGNI blocco la stessa frase:
                    frames = []                                         #  1157 errori in 47 s, mentre il riconoscimento si stava riavviando)
                    await asyncio.sleep(0.5)
                    continue
                if matches_phrase(text, phrase, 0.72):
                    rest = strip_wake(text, phrase).strip()
                    self.pending_text = rest if rest and rest != text.strip() else None
                    log.info("wake word (stt): %r", text)
                    self._voice_wake = True
                    self.hub.set_state(State.LISTENING)
                    return
                ep.reset()

    async def _verify_wake(self) -> bool:
        w = self.cfg["wake"]
        self.hub.set_state(State.LISTENING)                        # reazione immediata, poi si controlla
        if not w.get("verify_with_stt", True) or not hasattr(self.wake, "last_score"):
            return True
        try:
            audio = np.concatenate(list(self.ring))
            text = await self.router.transcribe(audio, self.cfg["audio"]["input_rate"])
        except Exception as e:                                      # noqa: BLE001
            log.warning("verifica wake word non riuscita (%s): accetto", e)
            return True
        ok = matches_phrase(text, w["phrase"], 0.6)
        log.info("wake word %s (score %.2f, sentito: %r)", "OK" if ok else "RIFIUTATO", getattr(self.wake, "last_score", 0), text)
        if not ok:
            self.hub.set_state(State.IDLE)
        return ok

    # ---------------------------------------------------------------- sessione
    async def session(self) -> None:
        self.in_session = True
        ctx = self.memory.context(None, self.cfg["memory"]["max_facts_in_prompt"], include_last=True) if self.memory else ""
        self.sys_prompt = self._build_system(self.persona, self.cfg, ctx)
        self.history = []
        self._rhythm_prev = None                                       # la mossa del turno prima (un parere si difende anche alla frase dopo)
        self._said_goodbye = False
        self.pending, self._weather_day, self._asked_session, self._hint = None, None, False, ""
        self.pending_confirm, self.pending_slot, self._list_ctx, self._turn_no = None, None, None, 0
        self._last_query, self._last_power = None, None
        self._unclear = 0
        carry, first, empties = None, True, 0
        self._stop_evt.clear()                                                  # (uno stop di prima non deve chiudere questa conversazione; uno premuto DURANTE si'')
        try:
            if self._voice_wake and not self.pending_text and self.cfg.get("human", {}).get("greet", True):
                await self._greet()                                             # chiamata a voce, senza una richiesta: risponde come una persona
            else:
                self._play_chime(CHIME_WAKE)
            while True:
                audio = None
                if self.pending_text:
                    text, self.pending_text = self.pending_text, None
                else:
                    audio = await self.listen(self.t["first_turn_timeout_s"] if first else self.t["follow_up_timeout_s"], carry)
                    carry = None
                    if audio is None:
                        break
                    self.hub.set_state(State.THINKING)
                    try:
                        text = strip_wake(await self.router.transcribe(audio, self.cfg["audio"]["input_rate"]), self.cfg["wake"]["phrase"])
                        if text.strip() and dialog.looks_unfinished(text):      # si e' fermato a meta' frase («e poi…»): gli lascia un attimo per continuare
                            more = await self.listen(float(self.t.get("continue_wait_s", 1.8)))
                            if more is not None:
                                self.hub.set_state(State.THINKING)
                                gap = np.zeros(int(0.2 * self.cfg["audio"]["input_rate"]), dtype=audio.dtype)
                                audio = np.concatenate([audio, gap, more])
                                text = strip_wake(await self.router.transcribe(audio, self.cfg["audio"]["input_rate"]), self.cfg["wake"]["phrase"])
                    except Exception as e:                              # noqa: BLE001
                        log.error("riconoscimento vocale: %s", e)
                        self._play_chime(CHIME_ERROR)
                        break
                first = False
                self.hub.set_state(State.THINKING)
                text = self._fix_heard(text)
                if audio is not None:
                    self._record_utterance(audio, text)
                else:
                    log.info("TU: %s", text)
                if audio is not None and text.strip() and self.cfg.get("human", {}).get("ask_again", True) and self._low_confidence(text):
                    self._unclear += 1                                          # Whisper stesso non e' sicuro: meglio chiedere che rispondere a qualcosa che non hai detto
                    log.info("(poco chiaro: %s) chiede di ripetere", self._stt_conf())
                    if self._unclear <= 2:
                        await self._say(dialog.unclear_reply(self._unclear - 1, self._last_closing))
                        carry = None
                        continue
                else:
                    self._unclear = 0
                if text.strip():
                    self.hub.transcript("user", text)
                if not text.strip():
                    empties += 1
                    if empties >= 2:
                        break
                    continue
                empties = 0
                if is_stop_command(text):
                    self.speaker.stop()
                    break
                if self.pending_confirm is not None:
                    action, self.pending_confirm = self.pending_confirm, None
                    t = normalize(text)
                    if (_YES_EN if i18n.is_en() else _YES).match(t):
                        self.history.append({"role": "user", "content": text})
                        await self._say(i18n.pick("Ok, la eseguo.", "Okay, running it."))
                        await self._say(await self.tools.run(action))
                        carry = None
                        continue
                    if (_NO_EN if i18n.is_en() else _NO).match(t):
                        self.history.append({"role": "user", "content": text})
                        await self._say(i18n.pick("Va bene, non la eseguo.", "Alright, I won't run it."))
                        carry = None
                        continue                                                 # altrimenti e' un'altra richiesta: si tratta normalmente
                if self.pending_slot is None and self.pending is None and self.cfg.get("human", {}).get("dialog_acts", True):
                    act = await self._dialog_act(text)                           # saluti, grazie, «ok», risate, «come?»: risposte da persona, senza chatbot
                    if act == "end":
                        break
                    if act:
                        carry = None
                        continue
                ack, rewrite = self._learn(text)
                if rewrite:
                    text = rewrite
                self.history.append({"role": "user", "content": text})
                self._refresh_prompt(text)
                if ack:                                                     # presentazione/risposta alla domanda: risponde Aria, senza modello (niente invenzioni)
                    self._rhythm = None
                    await self._say(ack)
                    carry = None
                    continue
                carry = await self.respond()
                if self._stop_evt.is_set():                                 # "stop" dal tasto/menu: chiude la conversazione
                    break
                if carry is None:
                    await self._maybe_ask()
        finally:
            self.in_session = False
            self._voice_wake = False
            self._last_end = time.time()
            if not self._said_goodbye:                                          # dopo «buonanotte!» un suono di chiusura sarebbe fuori posto
                self._play_chime(CHIME_DONE)
            self.hub.set_state(State.IDLE)
            self._keep_last_topic()
            if self.memory and sum(1 for m in self.history if m["role"] == "user") >= 2:
                self._bg_once(self._remember_session(list(self.history)))

    def _stt_conf(self) -> dict | None:
        for o in self.router.objects("stt"):
            c = getattr(o, "last_conf", None)
            if c:
                return c
        return None

    def _low_confidence(self, text: str) -> bool:
        """True se la dettatura e' probabilmente sbagliata: Whisper e' poco sicuro (avg_logprob basso), ripete lo stesso pezzo, o esce spazzatura.
        Soglie tarate sulle frasi vere dell'utente: quelle giuste stanno tra -0.1 e -0.65, gli errori ('Corriva', 'Quella', rumore) sotto -0.8."""
        if "\ufffd" in text or not re.search(r"[A-Za-zÀ-ÿ]{2}", text):
            return True
        c = self._stt_conf()
        if not c:
            return False
        limit = -0.9 if len(text.split()) <= 12 else -1.1
        return c["avg_logprob"] < limit or c["compression"] > 2.4

    def _keep_last_topic(self) -> None:
        """A fine conversazione ricorda UNA frase detta dall'utente (la piu' lunga tra quelle che non erano domande o comandi): la volta dopo Aria puo'
        riprenderla con un «com'e' andata?». Sono parole sue, mai un riassunto del modello."""
        if not self.memory:
            return
        best = ""
        for m in self.history:
            if m["role"] != "user":
                continue
            t = m["content"].strip()
            if len(t.split()) >= 6 and not t.endswith("?") and intent.detect(t) is None and len(t) > len(best):
                best = t
        if best:
            self.memory.set_last_topic(best)

    # ---------------------------------------------------------------- come una persona: saluto, congedo, ringraziamenti
    def _user_name(self) -> str | None:
        return self.memory.get_profile("name") if self.memory else None

    def _last_aria(self) -> str:
        return next((m["content"] for m in reversed(self.history) if m["role"] == "assistant"), "")

    async def _greet(self) -> None:
        """«Hey Aria» da solo: risponde con un saluto adatto all'ora (e a quanto e' passato dall'ultima volta). Se c'e' un impegno di cui
        aveva parlato e che e' passato («com'e' andato l'esame?») lo chiede subito, come farebbe un'amica."""
        import datetime as dt
        since = (time.time() - self._last_end) if self._last_end else None
        if self.memory and not self._user_name():                              # non sa ancora come ti chiami: si presenta e lo chiede, come con una persona nuova
            n, last = self.memory.times_asked("name")
            if n < ASK_MAX and time.time() - last >= ASK_EVERY_H * 3600:
                self.memory.mark_asked("name")
                self.pending, self._asked_session = "name", True
                await self._say(dialog.greeting_and_name(dt.datetime.now()))
                return
        fu = asyncio.create_task(self._followup_question())                  # intanto che saluta, prepara la domanda
        hello = dialog.greeting(dt.datetime.now(), self._user_name(), since)
        await self._say(hello)
        try:
            q = await asyncio.wait_for(fu, 6.0)
        except Exception:                                                   # noqa: BLE001
            q = None
        if q:
            await self._say(q)

    async def _followup_question(self) -> str | None:
        if not self.memory or not hasattr(self.memory, "pending_followups"):
            return None
        due = self.memory.pending_followups()
        if not due:
            return None
        fid, text, days = due[0]
        when = ({-1: "yesterday", -2: "the day before yesterday"}.get(days, "a few days ago") if i18n.is_en() else {-1: "ieri", -2: "l'altro ieri"}.get(days, "qualche giorno fa"))
        self.memory.mark_followed(fid)
        try:
            if i18n.is_en():
                out = await self._generate_text(
                    "Write ONE single sentence: a short, warm and natural question in English, to ask a friend how something they had told you about went. "
                    "No greeting, no name, no explanation: just the question.",
                    f"A friend had told you (\"{text}\") {when}. How do you ask them how it went?", 40)
            else:
                out = await self._generate_text(
                    "Scrivi UNA sola frase: una domanda breve, calda e naturale in italiano, per chiedere a un amico come è andata una cosa di cui ti aveva parlato. "
                    "Nessun saluto, nessun nome, nessuna spiegazione: solo la domanda.",
                    f"Un amico ti aveva detto («{text}») {when}. Come gli chiedi com'è andata?", 40)
        except Exception as e:                                              # noqa: BLE001
            log.debug("domanda di follow-up non riuscita: %s", e)
            out = ""
        q = re.split(r"(?<=[?])\s", style.clean_reply(strip_emoji(out)).strip())[0] if out else ""
        if q.endswith("?") and 3 <= len(q.split()) <= 20 and "\n" not in q:
            return q
        return i18n.pick("Com'è andata quella cosa di cui mi avevi parlato?", "How did that thing you told me about go?")

    async def _dialog_act(self, text: str) -> str | None:
        """Gli «atti» che una persona gestisce senza pensarci. Restituisce 'end' (ha salutato: la conversazione finisce), True (gestito) o None."""
        import datetime as dt
        name = self._user_name()
        users_before = sum(1 for m in self.history if m["role"] == "user")
        if dialog.is_greeting(text) and users_before == 0:                   # un «ciao» come prima frase e' un saluto: risponde al saluto
            self.history.append({"role": "user", "content": text})
            await self._say(dialog.greeting(dt.datetime.now(), name))
            return True
        if dialog.is_dismissal(text):                                        # «spegniti», «vai in background»: torna in disparte (prima di qualsiasi strumento: «spegni» e' anche la musica)
            self.history.append({"role": "user", "content": text})
            self._last_closing = random.choice([r for r in dialog.dismiss_replies() if r != self._last_closing] or dialog.dismiss_replies())
            self._said_goodbye = True
            await self._say(self._last_closing)
            return "end"
        vr = dialog.voice_request(text)
        if vr:                                                               # «cambia voce», «usa la voce di Marco», «attiva la voce naturale»
            self.history.append({"role": "user", "content": text})
            await self._voice_act(*vr)
            return True
        if dialog.is_farewell(text) and users_before >= 1:
            reply = dialog.farewell_reply(dt.datetime.now(), name, text, self._last_closing)
            self.history.append({"role": "user", "content": text})
            self._last_closing = reply
            self._said_goodbye = True
            await self._say(reply)
            return "end"
        if dialog.is_thanks(text):
            self.history.append({"role": "user", "content": text})
            self._last_closing = dialog.thanks_reply(self._last_closing)
            await self._say(self._last_closing)
            return True
        if dialog.is_laugh(text) and users_before >= 1:
            if random.random() < 0.7:
                self.history.append({"role": "user", "content": text})
                await self._say(dialog.laugh_reply(self._last_closing))
            return True
        if dialog.is_presence_check(text) and users_before >= 1:
            self.history.append({"role": "user", "content": text})
            await self._say(dialog.presence_reply(self._last_closing))
            return True
        if dialog.is_apology(text):
            self.history.append({"role": "user", "content": text})
            await self._say(dialog.apology_reply(self._last_closing))
            return True
        kind = dialog.complaint_kind(text)
        if kind:                                                             # «ti mangi le parole», «ti sei bloccata»: lo riconosce e basta, senza far inventare il chatbot
            self.history.append({"role": "user", "content": text})
            reply = dialog.complaint_reply(kind, self._last_closing)
            self._last_closing = reply
            await self._say(reply)
            return True
        prev = self._last_aria()
        if prev and dialog.is_repeat_request(text):
            self.history.append({"role": "user", "content": text})
            await self._say(dialog.repeat_reply(prev))
            return True
        if dialog.is_ack(text) and prev and not prev.rstrip().endswith("?"):
            log.info("(un «%s» dopo un'affermazione: non serve rispondere)", text.strip())
            return True                                                      # un «ok» dopo un'affermazione: ascolta e basta, come farebbe una persona
        return None

    async def _voice_act(self, kind: str, arg: str) -> None:
        """La voce di Aria a richiesta: accende/spegne la «voce naturale» (Impostazioni → poteri) e passa da una voce all'altra."""
        if i18n.is_en():
            await self._voice_act_en(kind, arg)
            return
        from . import profiles as P
        from .tts import QwenTTS
        path = self.cfg.get("_config_path")
        auto = next((o for o in self.router.objects("tts") if hasattr(o, "qwen")), None)
        if auto is None or not path:
            await self._say(i18n.pick("Per ora ho una voce sola, mi dispiace.", "For now I only have one voice, sorry."))
            return
        q = auto.qwen
        if kind == "natural_off":
            P.set_power(path, "voice_natural", False)
            q._on_cache = (0.0, False)
            await self._say(i18n.pick("Fatto, torno alla voce di prima.", "Done, I'm going back to the previous voice."))
            return
        if kind == "natural_on" or not q.enabled():
            if q.enabled():
                await self._say(i18n.pick("La voce naturale è già accesa.", "The natural voice is already on."))
                return
            if kind != "natural_on":                                         # «cambia voce» con una voce sola: dice cosa si puo' fare
                await self._say(i18n.pick("Con questa voce non posso cambiare. Se vuoi, dimmi «attiva la voce naturale»: ne ho tante, da donna e anche da uomo: sono quelle che trovi anche nell'elenco delle voci.",
                                      "I can't change this voice. If you like, say \"turn on the natural voice\": I have plenty, female and male, the same ones you find in the voice list."))
                return
            P.set_power(path, "voice_natural", True)
            q._on_cache = (0.0, True)
            first = not q.downloaded()
            q.usable()                                                       # parte subito: scarica il modello o lo carica in memoria
            await self._say(i18n.pick("Va bene, la accendo. La prima volta devo scaricare il modello, ci vuole un po': intanto parlo come prima e poi cambio da sola." if first
                                      else "Va bene, la accendo. Ci metto qualche secondo a caricarla, poi parlo con la voce nuova.",
                                      "Okay, turning it on. The first time I have to download the model, which takes a while: meanwhile I'll talk as before and then switch by myself." if first
                                      else "Okay, turning it on. It takes a few seconds to load, then I'll talk with the new voice."))
            return
        if not q.usable():
            await self._say(i18n.pick("La voce naturale si sta ancora preparando: tra poco potrò cambiarla.", "The natural voice is still getting ready: I'll be able to change it in a moment."))
            return
        name = arg if kind == "set" else QwenTTS.VOICES[(QwenTTS.VOICES.index(q.voice) + 1) % len(QwenTTS.VOICES)]
        self.hub.dispatch_command({"cmd": "voice", "name": name})            # come dal menu: la imposta e la ricorda
        await self._say(i18n.pick(f"Ecco, questa è la voce di {name.capitalize()}. Ti piace?", f"Here it is, this is the voice of {name.capitalize()}. Do you like it?"))

    async def _voice_act_en(self, kind: str, arg: str) -> None:
        """Cambiare voce in inglese: si sceglie tra le voci inglesi di Pocket TTS (per nome, «a male voice», o la prossima dell'elenco). La voce naturale (Qwen3-TTS) c'e' solo in italiano."""
        pocket = any(hasattr(o, "pocket") or hasattr(o, "VOICES_F") for o in self.router.objects("tts"))
        if kind in ("natural_on", "natural_off"):
            await self._say("The natural voice is only available in Italian for now. In English you can pick another voice: say, for example, use the voice of George." if kind == "natural_on"
                            else "I'm already using the standard voice.")
            return
        if not pocket:
            await self._say("With this setup I only have one voice, sorry.")
            return
        voices = i18n.EN_VOICES
        current = (self._current_voice() or "").lower()
        name = arg if kind == "set" else voices[(voices.index(current) + 1) % len(voices) if current in voices else 0]
        self.hub.dispatch_command({"cmd": "voice", "name": name})            # come dal menu: la imposta e la ricorda
        await self._say(f"Here it is, this is the voice of {name.capitalize()}. Do you like it?")

    # ---------------------------------------------------------------- ascolto
    async def _frames(self, carry):
        for f in carry or []:
            yield f
        async for f in self.mic.frames():
            yield f

    async def listen(self, timeout: float, carry=None) -> np.ndarray | None:
        self.hub.set_state(State.LISTENING)
        t = self.t
        ep = Endpointer(FRAME_MS, 96, t["end_silence_ms"], t["min_speech_ms"], t["max_utterance_s"], timeout, self.cfg["vad"]["threshold"], 0.35)
        self.vad.reset()
        preroll: deque = deque(maxlen=max(1, int(t["preroll_ms"] / FRAME_MS)))
        frames: list[np.ndarray] = []
        speaking = False
        async for frame in self._frames(carry):
            if self._stop_evt.is_set():                                      # «stop» dal tasto/menu mentre ti ascolta: chiude la conversazione subito (prima non faceva niente)
                return None
            ev = ep.push(self.vad.prob(self._boost(frame)))
            self.hub.set_level(rms_level(frame))
            if not speaking:
                preroll.append(frame)
            if ev == "start":
                speaking, frames = True, list(preroll)
            elif speaking:
                frames.append(frame)
            if ev == "end":
                audio = np.concatenate(frames)
                self._learn_level(audio)
                if ep.run >= ep.end_frames:                                  # chiuso dal silenzio: tieni solo ~250 ms di coda
                    cut = (ep.end_frames - 8) * len(frames[0])
                    if 0 < cut < len(audio) - 4000:
                        audio = audio[:-cut]
                return audio
            if ev == "timeout":
                return None
        return None

    # ---------------------------------------------------------------- risposta
    @staticmethod
    def _tool_followup(call, result: str) -> list[dict]:
        return [{"role": "assistant", "content": f"[[{call.name}: {call.arg}]]"},
                {"role": "user", "content": (f"(System data, not said by the user: {result})\n"
                                             f"Now answer the user out loud, in one or two sentences, in your own words, as if you knew it yourself. "
                                             f"Don't mention the system, don't say 'searched', no commands.") if i18n.is_en() else
                                            (f"(Dati dal sistema, non detti dall'utente: {result})\n"
                                             f"Rispondi ora all'utente a voce, in una o due frasi, con parole tue, come se lo sapessi tu. "
                                             f"Non nominare il sistema, non dire 'cercato', nessun comando.")}]

    def _llm_temperature(self) -> float:
        """La temperatura di base del chatbot in uso (config): la «mossa» del turno la sposta un po' (piu' ferma per spiegare, piu' libera per i pareri)."""
        for b in self.router.brains:
            if isinstance(b.get("llm"), dict) and b["llm"].get("temperature") is not None:
                return float(b["llm"]["temperature"])
        return 0.7

    def _sentence_cap(self, user_text: str) -> int:
        """Quante frasi al massimo: poche per una chiacchiera, di piu' se chiede di spiegare. Un modello piccolo, lasciato libero, fa dei monologhi."""
        n = int(self.cfg.get("human", {}).get("max_sentences", 3))
        kind = style.long_kind(user_text)
        if kind == "explain":
            return int(self.cfg.get("human", {}).get("max_sentences_long", 20))      # glielo ha chiesto: puo' distendersi
        if kind == "quiz":
            return 4
        t = normalize(user_text)
        if style._QUESTION_WORDS.match(t) or len(user_text.split()) >= 28:
            return n + 2
        return n

    def _thin_name(self, s: str) -> str:
        """Il nome dell'utente in una frase del chatbot: lo si lascia una volta ogni tanto, altrimenti si toglie (e si evita di farlo storpiare alla voce)."""
        name = self._user_name()
        if not name or not re.search(rf"\b{re.escape(name)}\b", s):
            return s
        if self._turn_no - self._name_turn >= int(self.cfg.get("human", {}).get("name_every", 6)):
            self._name_turn = self._turn_no
            return s
        return style.strip_vocative(s, name)

    async def _llm_intent(self, text: str) -> ToolCall | None:
        """Chiede al chatbot di «decodificare» una richiesta d'azione che le regole non hanno capito. Vedi llmintent.py per le garanzie."""
        from . import llmintent
        system, user = llmintent.prompt(text)
        try:
            out = await self._generate_text(system, user, max_tokens=70, temperature=0.0)
        except Exception as e:                                                  # noqa: BLE001
            log.warning("decodifica con il chatbot non riuscita: %s", e)
            return None
        call = llmintent.parse(out)
        if call and call.name == "SCHERMO" and call.arg.startswith("parere"):
            call = ToolCall("SCHERMO", "parere|" + text.strip(" .!?"))                          # la domanda com'e' stata detta
        if call and call.name in ("CONVERTI", "DATA", "CASO", "AIUTO"):                          # strumenti che leggono la frase intera (se non capiscono, lo dicono: meglio di un chatbot che inventa)
            call = ToolCall(call.name, "" if call.name == "AIUTO" else text)
        ok = bool(call and llmintent.grounded(call, text) and llmintent.plausible(call, text))
        log.info("DECODIFICA (chatbot) %r -> %r (%s)", text, out.strip()[:90], "ok" if ok else "scartata" if call else "nessuno")
        return call if ok else None

    def _ungrounded(self, call: ToolCall, user_text: str) -> str | None:
        """None se quello che il chatbot ha chiesto a uno strumento e' coerente con cio' che l'utente ha detto; altrimenti una risposta onesta.
        I modelli piccoli, davanti a «prova a creare un promemoria», inventano un [[TIMER: 10:00 | caffe']] mai chiesto."""
        t = normalize(user_text)
        if call.name == "TIMER":
            from .timeparse import parse_when
            import datetime as dt
            from .tools import parse_duration
            w = parse_when(user_text, dt.datetime.now())
            if not (parse_duration(t) or (w and w.has_time)):
                return i18n.pick("Non ho capito per quanto tempo o a che ora. Dimmelo, ad esempio: metti un timer di dieci minuti.", "I didn't catch how long or at what time. Tell me, for example: set a timer for ten minutes.")
        if call.name == "CALCOLA":                                              # «controlla se funziona» -> [[CALCOLA: 10 - 0]]: un calcolo che nessuno ha chiesto
            want = {int(n) for n in re.findall(r"\d+", call.arg)}
            said = {int(n) for n in re.findall(r"\d+", t)}
            for w in t.split():
                v = intent.number_it(w) if not i18n.is_en() else intent_en.number_en(w)
                if v is not None:
                    said.add(v)
            if not want or not want <= said:
                return i18n.pick("Che calcolo vuoi che faccia? Dimmi i numeri, ad esempio: quanto fa dodici per sette.", "What should I calculate? Tell me the numbers, for example: what is twelve times seven.")
        if call.name == "RICORDA" and not re.search(r"\b(?:ricord\w*|segnat\w*|tieni a mente|non dimenticare|memorizza\w*|annota\w*|appunta\w*|remember|note|keep in mind|don t forget|memorize|write down|jot down|make a note)\b", t):
            return i18n.pick("Se vuoi che me lo ricordi dimmelo così: ricordati che, e poi quello che vuoi.", "If you want me to remember it, say it like this: remember that, and then whatever you want.")
        return None

    def _workspace_files(self) -> list[str] | None:
        """I nomi dei file nella cartella di Aria (per riconoscere «cosa dice il contratto…»), oppure None se non c'e' una cartella."""
        try:
            ws = self.tools._ws()
            return [n for n, _sz in ws.list()] if ws is not None else None
        except Exception:                                                       # noqa: BLE001
            return None

    def _fix_heard(self, text: str) -> str:
        """Il riconoscimento scrive «a orecchio» i nomi che non conosce («Maria» per «Mario», «Sonnium» per «Somnium»): torna la parola che Aria conosce
        (nome e citta' dell'utente, nomi dei file nella sua cartella). Vedi lexicon.py."""
        if not text.strip() or not self.cfg.get("human", {}).get("fix_names", True):
            return text
        try:
            from .lexicon import Lexicon
            lex = Lexicon()
            if self.memory:
                prof = self.memory.profile()
                lex.add_all([prof.get(k, "") for k in ("name", "city")], loose=True)
            for n in self._workspace_files() or []:
                lex.add_all(re.split(r"[\s_\-.]+", n.rsplit(".", 1)[0]))
            fixed = lex.correct(text)
            if fixed != text:
                log.info("nome corretto: %r -> %r", text, fixed)
            return fixed
        except Exception as e:                                                  # noqa: BLE001
            log.debug("correzione dei nomi non riuscita: %s", e)
            return text

    async def reply_events(self, messages: list[dict]) -> AsyncIterator[tuple[str, object]]:
        """Genera ('sentence', testo) e ('tool_start', ToolCall). Le richieste ovvie (meteo, timer, calcoli...) partono
        subito (intent.detect); per il resto il modello puo' chiedere uno strumento con [[COMANDO: ...]] (fino a 2 giri)."""
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        turn, self._rhythm = self._rhythm, None                                  # la mossa vale per questa risposta e basta (non per il giro dopo uno strumento)
        self._turn_no += 1
        files = self._workspace_files()
        pre = None
        slot, self.pending_slot = self.pending_slot, None
        if slot is not None:                                                    # aveva chiesto un pezzo mancante: questa frase e' la risposta (a meno che cambi discorso)
            if intent.slot_cancelled(last_user):
                msg = random.choice(["Va bene, lascio stare.", "Ok, niente.", "Va bene, annullo."])
                self.history.append({"role": "assistant", "content": msg})
                yield "sentence", msg
                return
            other = intent.detect(last_user, files, screen_on=bool(getattr(self.tools, "_screen_engine", lambda: None)()))
            if other is None or other.name == slot.name or other.name == "NON_SO":       # «chiamare il commercialista alle nove» e' il CONTENUTO del promemoria, non un ordine di telefonare
                pre = intent.merge_slot(slot, last_user)
        convert_note = ""
        if pre is None and self.cfg.get("tools", {}).get("intent", True):
            pre = intent.detect(last_user, files, screen_on=bool(getattr(self.tools, "_screen_engine", lambda: None)()))
            if pre is None and self._list_ctx and self._list_ctx[1] == self._turn_no - 1:      # «aggiungi anche le uova»
                pre = intent.list_followup(last_user, self._list_ctx[0])
            if pre is None and self._last_query and intent.is_save_last(last_user):               # «mettila nella cartella» dopo una ricerca
                pre = ToolCall("RICERCA", self._last_query)
            if pre is None and self._last_power is not None:                                       # «lo metti come promemoria, non come evento» / «cambia caffè con tabacchi»
                target = intent.convert_target(last_user)
                if target and target != self._last_power.name and self._last_power.name in ("EVENTO", "PROMEMORIA"):
                    pre = ToolCall(target, self._last_power.arg)
                    convert_note = (i18n.pick("L'evento che avevo messo prima resta in calendario: toglilo tu, se non ti serve.", "The event I added before stays in the calendar: remove it yourself if you don't need it.") if target == "PROMEMORIA"
                                    else i18n.pick("Il promemoria di prima resta: toglilo tu, se non ti serve.", "The earlier reminder stays: remove it yourself if you don't need it."))
                rep = intent.replace_words(last_user)
                if pre is None and rep and rep[0].lower() in self._last_power.arg.lower():
                    pre = ToolCall(self._last_power.name, re.sub(re.escape(rep[0]), rep[1], self._last_power.arg, count=1, flags=re.I))
                    convert_note = i18n.pick("Quello di prima non lo so cancellare: resta, toglilo tu dall'app.", "I can't delete the earlier one: it stays, remove it yourself from the app.")
        if pre is None and (kind_save := intent.is_save_reply(last_user)):                    # «scrivimi tutta la ricetta in un file», «mettilo nella cartella»: salva QUELLO DI CUI STATE PARLANDO
            import json as _json
            past = self.history[:-1] if self.history and self.history[-1]["role"] == "user" and self.history[-1]["content"] == last_user else self.history
            earlier = [m for m in past[-9:] if m["content"].strip()]                         # senza la frase di adesso
            last_long = next((m["content"] for m in reversed(earlier) if m["role"] == "assistant" and len(m["content"]) >= 160), None)
            dictated = len(last_user) >= 200                                                  # il testo con cui lavorare e' nella stessa frase («ti leggo questo testo… scrivi le altre strofe e mettile in un file»)
            if last_long or len(earlier) >= 2 or dictated:
                pre = ToolCall("SALVA", _json.dumps({"kind": kind_save, "request": last_user, "source": last_long or "",
                                                    "history": [{"role": m["role"], "content": m["content"][:1800]} for m in earlier[-8:]]}, ensure_ascii=False))
            else:                                                                           # non c'e' niente da salvare: lo dice, non promette
                guard = i18n.pick("Non ho ancora niente da mettere in un file. Dimmi di cosa lo vuoi, ad esempio: scrivimi la ricetta degli gnocchi alla romana in un file.", "I don't have anything to put in a file yet. Tell me what it should be about, for example: write me the recipe for carbonara in a file.")
                log.info("richiesta di file senza argomento: %r", last_user)
                self.history.append({"role": "assistant", "content": guard})
                yield "sentence", guard
                return
        if pre is not None and pre.name == "SCHERMO" and pre.arg == "indica|" and not getattr(self.tools, "recent_found", lambda: False)():
            pre = None                                                                          # «mostramelo» senza aver appena cercato qualcosa sullo schermo: parlava d'altro
        if pre is not None and pre.name == "RICERCA" and not pre.arg.strip() and self._last_query:
            pre = ToolCall("RICERCA", self._last_query)                                          # «fammi una ricerca e salvala»: su quello di cui stavate parlando
        if pre is None and self.cfg.get("human", {}).get("action_guard", True):
            domain = intent.action_like(last_user) or intent.file_attempt(last_user) or intent.screen_attempt(last_user)             # sembra una richiesta d'azione ma le regole non l'hanno capita
            if self.cfg.get("human", {}).get("llm_intent", True) and ((domain and not domain[2]) or (domain is None and intent.request_like(last_user))):
                pre = await self._llm_intent(last_user)                                          # ultima rete: il chatbot la «decodifica» (solo con parole dette dall'utente)
            guard = None
            if pre is None:
                guard = intent.not_understood(domain) if domain else None                       # altrimenti lo dice onestamente, non lascia inventare al chatbot
                if guard is None and self._last_power is not None and intent.replace_words(last_user):
                    guard = i18n.pick("Cambiare quello che ho già creato non so farlo. Dimmelo da capo, completo, e ne creo uno nuovo.", "I can't change what I already created. Tell me again from the start, in full, and I'll create a new one.")
            if guard:
                log.info("richiesta d'azione non capita: %r", last_user)
                self.history.append({"role": "assistant", "content": guard})
                yield "sentence", guard
                return
        if pre is not None:
            if pre.name in SLOW_TOOLS and (pre.name not in NEEDS_FOLDER or self.tools._ws() is not None) and (pre.arg.split("|")[-1].strip() or pre.name in ("BRIEFING", "SCHERMO")) \
                    and (pre.name != "SCHERMO" or getattr(self.tools, "_screen_engine", lambda: None)()):
                yield "tool_start", pre
                yield "sentence", random.choice(_working("doc" if pre.name in ("SCRIVI", "SALVA") else "screen" if pre.name == "SCHERMO" else ""))                # lavora qualche secondo: intanto lo dice
            else:
                yield "tool_start", pre
            result = await self._run_tool(pre)
            if result == PASS:                                                  # non era un comando vero ("apri il tuo cuore"): ne parla il chatbot
                pre = None
        if pre is not None:
            if result.startswith(CONFIRM + "|"):                                # es. una scorciatoia: parte solo dopo il si' a voce
                _c, tool, targ, question = result.split("|", 3)
                self.pending_confirm = ToolCall(tool, targ)
                self.history.append({"role": "assistant", "content": question})
                yield "sentence", question
                return
            if result.startswith(ASK + "|"):                                    # manca un pezzo (quando? cosa?): lo chiede e aspetta la risposta
                _a, tool, partial, question = result.split("|", 3)
                self.pending_slot = ToolCall(tool, partial)
                self.history.append({"role": "assistant", "content": question})
                yield "sentence", question
                return
            if pre.name == "LISTA":
                self._list_ctx = (pre.arg.split("|")[0], self._turn_no)
            if pre.name in ("EVENTO", "PROMEMORIA", "LISTA", "NOTA") and result.startswith(("Fatto", "Va bene", "Ok", "Aggiunto", "Nota", "Done", "All right", "Okay", "Added", "Note")):
                self._last_power = pre                                                           # ricorda cosa ha appena creato
            if pre.name == "CERCA":
                self._last_query = pre.arg
            log.info("STRUMENTO (a monte) %s(%s) -> %s", pre.name, pre.arg, result[:120])
            if result == NEED_CITY:
                async for ev in self._ask_city_for_weather(pre.arg):
                    yield ev
                return
            if pre.name in SPEAK_VERBATIM and self.cfg.get("tools", {}).get("speak_verbatim", True):
                ch = SentenceChunker(first_min=1, min_len=1)               # la risposta dello strumento e' gia' una frase: si legge cosi'
                parts = [s for s in ch.push(result + " ")] + list(ch.flush())
                for s in parts:
                    yield "sentence", s
                if convert_note:
                    yield "sentence", convert_note
                    result = result + " " + convert_note
                self.history.append({"role": "assistant", "content": result})
                return
            messages = messages + self._tool_followup(pre, result)
        cap = self._sentence_cap(last_user)
        for hop in range(3):
            chunker, tf, call = SentenceChunker(first_min=int(self.t.get("first_chunk_min_chars", 30))), TagFilter(), None
            spoken: list[str] = []
            capped, n_sent, open_frag, claimed = False, 0, False, False
            tn = turn if hop == 0 else None                                      # dopo uno strumento si risponde con i dati, non con la «mossa»
            gov = rhythm.Governor(tn)
            long_kw = {"max_tokens": int(self.cfg.get("human", {}).get("long_max_tokens", 900))} if style.long_kind(last_user) == "explain" else {}
            cap_h = cap
            if tn:
                long_kw = {"max_tokens": tn.max_tokens, "temperature": rhythm.temperature(tn, self._llm_temperature())}
                cap_h = min(cap, tn.max_sentences)
            async for tok in self.router.llm_stream(messages, **long_kw):
                text, calls = tf.push(tok)
                for s in chunker.push(text):
                    if self.cfg.get("human", {}).get("clean_replies", True):
                        if not spoken:
                            s = style.clean_reply(s)                            # via «Certamente!», «Aria:» e simili in testa alla risposta
                        if style.has_false_claim(s):
                            claimed = True                                      # «Fatto, ho aggiunto…» senza che sia partito niente: non si dice
                        s = style.drop_fabrications(s, last_user)               # via le esperienze inventate («ho letto che…»)
                        s = self._thin_name(style.strip_markdown(s))
                        s = style.polish(s, prior=bool(spoken))                 # via i connettivi da tema e le chiusure da assistente («sono qui se vuoi parlarne»)
                        if not s.strip():
                            continue
                    s, n_sent, open_frag, capped = _clip_sentences(s, cap_h, n_sent, open_frag)   # una chiacchiera non e' un discorso: oltre il tetto si ferma (a fine frase)
                    s = gov.take(s) if s else s                                 # la mossa del turno: niente domande dove non vanno, lunghezza nel budget
                    if s:
                        spoken.append(s)
                        yield "sentence", s
                    if (capped or gov.done) and not calls:
                        capped = True
                        break
                    capped = False
                if calls:
                    call = calls[0]
                    break
                if (n_sent >= cap_h and not open_frag) or gov.done:
                    capped = True
                    break
            if call is None:
                if not capped:
                    for s in list(chunker.flush()) + [tf.flush().strip()]:
                        if not s:
                            continue
                        if spoken and not re.search(r"[.!?…»\")]$", s.strip()):    # risposta tagliata a meta' dal limite di lunghezza: il pezzo senza fine non si dice
                            continue
                        if self.cfg.get("human", {}).get("clean_replies", True):
                            if not spoken:
                                s = style.clean_reply(s)
                            claimed = claimed or style.has_false_claim(s)
                            s = style.drop_fabrications(s, last_user)
                            s = self._thin_name(style.strip_markdown(s))
                            s = style.polish(s, prior=bool(spoken))
                            if not s.strip():
                                continue
                        s, n_sent, open_frag, hit = _clip_sentences(s, cap_h, n_sent, open_frag)
                        s = gov.take(s) if s else s
                        if s:
                            spoken.append(s)
                            yield "sentence", s
                        if hit or gov.done:
                            break
                if not spoken and claimed:                                      # aveva solo detto di aver fatto qualcosa che non ha fatto: lo dice onestamente
                    spoken.append(style.not_understood())
                    yield "sentence", style.not_understood()
                self.history.append({"role": "assistant", "content": " ".join(spoken).strip()})
                return
            for s in chunker.flush():
                spoken.append(s)
                yield "sentence", s
            yield "tool_start", call
            if call.name not in MODEL_TOOLS:                                    # file e Mac partono solo da una richiesta dell'utente
                log.warning("il chatbot ha provato a lanciare %s: rifiutato", call.name)
                result = i18n.pick(REFUSED, REFUSED_EN)
            elif (why := self._ungrounded(call, last_user)) is not None:         # il chatbot si e' inventato i dati (un timer di 10:00 «per il caffe'» mai chiesto)
                log.warning("il chatbot ha lanciato %s(%s) senza che l'utente l'avesse chiesto: rifiutato", call.name, call.arg)
                self.history.append({"role": "assistant", "content": why})
                yield "sentence", why
                return
            else:
                result = await self._run_tool(call)
            if result.startswith(ASK + "|"):                                    # manca un pezzo (per quanto tempo?): lo chiede, non lo fa dire al modello
                _a, tool, partial, question = result.split("|", 3)
                self.pending_slot = ToolCall(tool, partial)
                self.history.append({"role": "assistant", "content": question})
                yield "sentence", question
                return
            if call.name == "CERCA":
                self._last_query = call.arg
            log.info("STRUMENTO %s(%s) -> %s", call.name, call.arg, result[:120])
            if result == NEED_CITY:
                async for ev in self._ask_city_for_weather(call.arg):
                    yield ev
                return
            messages = messages + self._tool_followup(call, result)
        yield "sentence", i18n.pick("Scusa, mi sono incartata.", "Sorry, I got tangled up.")

    async def respond(self):
        """Parla la risposta. Se l'utente interrompe, ferma tutto e restituisce i frame gia' catturati."""
        messages = [{"role": "system", "content": self.sys_prompt}] + alternating(self.history[-self.cfg["memory"]["history_turns"] * 2:])
        q: asyncio.Queue = asyncio.Queue()
        gen = asyncio.create_task(self._produce(messages, q))
        play = asyncio.create_task(self._consume(q))
        self._said_now = []
        self._cap_sent = {}
        if self.cfg["audio"]["barge_in"]:
            mon = asyncio.create_task(self._monitor_barge_in())                  # con le cuffie: basta il rilevatore di voce
        elif self.cfg["audio"].get("barge_in_words", True):
            mon = asyncio.create_task(self._monitor_barge_in_words())            # con le casse: si guardano le parole
        else:
            mon = None
        stop = asyncio.create_task(self._stop_evt.wait())
        waiting = {play, stop} | ({mon} if mon else set())
        while True:
            done, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            if mon and mon in done and not (mon.cancelled() or mon.exception() or mon.result()) and not ({play, stop} & done):
                waiting.discard(mon)                                       # l'interruzione a voce non e' disponibile: si continua ad aspettare la fine della frase o lo stop
                continue
            break
        stop.cancel()
        carry = None
        mon_res = mon.result() if (mon and mon in done and not mon.cancelled() and not mon.exception()) else None
        if stop in done:
            log.info("fermata dall'utente (stop)")
            self.speaker.stop()
            for t in (gen, play, mon):                                     # (anche il monitor dell'interruzione a voce: se restava vivo, respond() aspettava che l'utente dicesse qualcosa
                if t is not None:                                          #  e Aria sembrava ancora «sta parlando» a voce spenta)
                    t.cancel()
        elif mon_res:
            log.info("interrotta dall'utente")
            carry = mon_res
            self.speaker.stop()
            for t in (gen, play):
                t.cancel()
            if self.history and self.history[-1]["role"] == "user":
                pass
        else:
            if mon:
                mon.cancel()
            await asyncio.gather(gen, return_exceptions=True)
        await asyncio.gather(gen, play, *( [mon] if mon else []), return_exceptions=True)
        aec = getattr(self, "_aec", None)
        if aec is not None and aec.conv < 0.999:
            log.info("eco di Aria nel microfono: resta il %.0f%% dell'energia dopo il filtro (azzerato %d volte)", aec.conv * 100, aec.resets)
        if self._aec_dbg:
            self._save_aec_debug()
        if carry is None and not getattr(self.mic, "cleaned", False):          # (col filtro eco del Mac il microfono ha solo l'utente: se ha gia' cominciato a parlare non si butta niente)
            if not self.cfg["audio"]["barge_in"]:
                await asyncio.sleep(0.3)                                   # senza eco-cancellazione: lascia spegnere la "coda" del suono
            self.mic.flush()
        return carry

    async def _produce(self, messages: list[dict], q: asyncio.Queue) -> None:
        got_sentence = False
        started = asyncio.get_running_loop().time()

        async def filler_timer():
            await asyncio.sleep(self.t["filler_after_ms"] / 1000)
            if not got_sentence and (f := self._filler()):
                await q.put((f[0], asyncio.ensure_future(self._const(f[1], f[2]))))

        ft = asyncio.create_task(filler_timer())
        try:
            async for kind, val in self.reply_events(messages):
                if kind == "sentence":
                    val = strip_emoji(val)
                    if not val:
                        continue
                    got_sentence = True
                    log.info("ARIA: %s", val)
                    self._said_now.append(val)                                  # per riconoscere la sua voce che rientra nel microfono (interruzione a voce)
                    if not self._captions_synced():
                        self.hub.transcript("aria", val, final=False)
                    await q.put((val, asyncio.create_task(self._tts(val))))
                elif kind == "tool_start" and not got_sentence and (f := self._filler(tool=True)):
                    got_sentence = True
                    await q.put((f[0], asyncio.ensure_future(self._const(f[1], f[2]))))
        except Exception as e:                                       # noqa: BLE001
            log.error("generazione fallita: %s", e)
            if not got_sentence:
                self._play_chime(CHIME_ERROR)
                await q.put((self._brain_down_message(), asyncio.create_task(self.router.synthesize(self._brain_down_message()))))
        finally:
            ft.cancel()
            await q.put(None)

    @staticmethod
    async def _const(pcm, sr):
        return pcm, sr

    async def _consume(self, q: asyncio.Queue) -> None:
        first = True
        ticker = None
        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                text = None
                if isinstance(item, tuple):                          # (testo, sintesi): il testo serve a riconoscere l'eco di quello che sta dicendo
                    text, item = item
                try:
                    pcm, sr = await item
                except Exception as e:                               # noqa: BLE001
                    log.error("sintesi vocale fallita: %s", e)
                    continue
                if first:
                    self.hub.set_state(State.SPEAKING)
                    ticker = asyncio.create_task(self._speaking_level())
                    first = False
                self.speaker.next_text = text
                self.speaker.play(pcm, sr)
            await self.speaker.wait_done()
        finally:
            if ticker:
                ticker.cancel()

    def _captions_synced(self) -> bool:
        """I sottotitoli seguono la voce (parola per parola) se le casse sanno dire cosa stanno suonando; altrimenti compaiono quando la frase e' pronta."""
        return bool(self.cfg.get("human", {}).get("captions_sync", True)) and hasattr(self.speaker, "captions")

    def _sync_captions(self) -> None:
        """Ai 30 Hz: per la frase che la voce sta dicendo manda allo schermo il testo fino alla parola a cui e' arrivata (un filo in anticipo, per leggerla mentre la senti).
        Prima apparivano tutte le frasi appena scritte dal chatbot e, se erano troppe per lo spazio, si vedeva solo la fine."""
        sp = self.speaker
        played = sp.played_samples
        look = int(0.25 * sp.rate)
        sent = self._cap_sent
        for start, end, text in list(sp.captions):
            if start > played + look:
                break
            if sent.get(end, 0) >= len(text):
                continue
            frac = (played + look - start) / max(1, end - start)
            n = len(text) if frac >= 0.92 else int(len(text) * frac / 0.92)            # la coda dell'audio e' la pausa dopo la frase, non parlato
            if n < len(text):
                j = text.find(" ", max(1, n))
                n = len(text) if j < 0 else j                                          # mai a meta' parola
            if n > sent.get(end, 0):
                sent[end] = n
                self.hub.transcript("aria", text[:n], final=False, sid=end)

    async def _speaking_level(self) -> None:
        self._cap_sent = {}
        while True:
            self.hub.set_level(self.speaker.level)
            if self._captions_synced():
                try:
                    self._sync_captions()
                except Exception as e:                                                  # noqa: BLE001
                    log.debug("sottotitoli a tempo: %s", e)
            await asyncio.sleep(1 / 30)

    async def _monitor_barge_in(self):
        """Mentre parla ascolta: se sente la voce dell'utente per ~260 ms, restituisce i frame raccolti."""
        need = max(2, int(self.t["barge_in_ms"] / FRAME_MS))
        run, tail = 0, deque(maxlen=need + 10)
        async for frame in self.mic.frames():
            tail.append(frame)
            if self.vad.prob(frame) >= 0.7:
                run += 1
                if run >= need:
                    return list(tail)
            else:
                run = max(0, run - 1)
        return None

    async def _monitor_barge_in_words(self):
        """Interruzione a voce senza cancellare l'eco: vedi bargein.py. Restituisce i frame da cui riprendere l'ascolto (o None)."""
        import os
        from . import bargein
        from .stt import AppleSTT, apple_helper_path
        if self._bi_stt is None:
            if not os.path.exists(apple_helper_path()):
                self._bi_stt = False
            else:
                self._bi_stt = AppleSTT({})
        words = self._bi_stt is not False                                 # senza il riconoscimento di Apple resta solo l'ascolto nelle pause
        if not words and not (self.cfg["audio"].get("barge_in_gaps", True) and hasattr(self.speaker, "ref_at")):
            return None
        self.mic.flush()                                                  # il microfono ha accumulato le parole che l'utente ha appena detto: non sono un'interruzione
        win: deque = deque(maxlen=int(1.6 * 16000 / FRAME_SAMPLES))
        clean = bool(getattr(self.mic, "cleaned", False))                 # il microfono ha gia' l'eco tolto dal Mac (audio.VoiceMic): niente filtro nostro, niente attesa delle pause
        aec = None if clean else self._echo_canceller()
        if aec is not None:
            aec.soft_reset()
        gap = None
        if not clean and self.cfg["audio"].get("barge_in_gaps", True) and hasattr(self.speaker, "ref_at"):
            gap = bargein.GapListener(self.vad)                           # nelle pause tra le frasi le casse sono zitte: li' la voce e' dell'utente (vedi bargein.GapListener)
        if gap is not None or clean:
            self.vad.reset()
        voiced: deque = deque(maxlen=12)                                  # (solo con l'eco tolto) i blocchi degli ultimi ~0,4 s in cui c'e' voce: senza voce non si riconosce niente
        every = 6 if clean else 14                                        # una volta ogni ~190 ms (con l'eco tolto) o ~450 ms
        stats = {"windows": 0, "voiced": 0, "heard": ""}
        try:
            return await self._barge_in_loop(win, voiced, every, clean, aec, gap, words, stats)
        finally:
            if stats["windows"] or stats["voiced"] > 20:
                log.info("interruzione a voce%s: %d finestre riconosciute, %d blocchi con voce, ultimo sentito %r", " (microfono senza eco)" if clean else "", stats["windows"], stats["voiced"], stats["heard"][:50])

    async def _barge_in_loop(self, win, voiced, every, clean, aec, gap, words, stats):
        from . import bargein
        n, fails = 0, 0
        decider = bargein.Interrupter()                                  # conferma le decisioni deboli: la stessa parola in due finestre di fila (l'eco capito male cambia ogni volta)
        async for frame in self.mic.frames():
            win.append(self._cancel_echo(aec, frame) if aec is not None else frame)
            n += 1
            if clean:
                v = len(frame) == FRAME_SAMPLES and self.vad.prob(self._boost(frame)) >= 0.5
                voiced.append(bool(v))
                stats["voiced"] += int(v)
            if gap is not None and len(frame) == FRAME_SAMPLES:
                try:
                    ref = self.speaker.ref_at(getattr(frame, "adc", None), FRAME_SAMPLES, 16000)
                    if gap.push(self._boost(frame), ref) and not self._tool_busy:
                        log.info("interrotta a voce (nella pausa tra due frasi)")
                        return list(win)[-22:]
                except Exception as e:                                   # noqa: BLE001
                    log.warning("interruzione nelle pause non riuscita (%s): la spengo per questa risposta", str(e)[:100])
                    gap = None
            if not words or n % every or len(win) < 20:
                continue
            if clean and sum(voiced) < 3:
                continue
            try:
                heard = await self._bi_stt.transcribe(np.concatenate(list(win)), 16000)
                stats["windows"] += 1
                stats["heard"] = heard or stats["heard"]
                fails = 0
            except Exception as e:                                       # noqa: BLE001
                fails += 1
                log.warning("interruzione a voce: riconoscimento non riuscito (%s)", str(e)[:120])
                getattr(self._bi_stt, "close", lambda: None)()           # si riparte pulito alla prossima finestra; solo dopo 3 errori di fila lascia perdere (per questa risposta)
                if fails >= 3:
                    return None
                continue
            kind = decider.feed(heard, self._recent_said(), clean)
            if kind == "talk" and self._tool_busy:                       # sta scrivendo un documento: un po' di rumore o una voce lontana non lo annullano, «stop» si
                continue
            if kind:
                log.info("interrotta a voce (%s): sentito %r", kind, heard[:60])
                return list(win)[-(32 if clean else 22):] if kind == "talk" else [np.zeros(FRAME_SAMPLES, dtype=np.int16)]
        return None

    def _save_aec_debug(self) -> None:
        """Salva (sovrascrivendo) microfono / riferimento / residuo dell'ultima risposta in ~/.aria/aec_ultima.npz: restano sul Mac e servono solo a capire come va il filtro."""
        import os
        frames, self._aec_dbg = self._aec_dbg, []
        if len(frames) < 40:
            return
        try:
            d = os.path.join(self.cfg["data_dir"])
            os.makedirs(d, exist_ok=True)
            np.savez_compressed(os.path.join(d, "aec_ultima.npz"), mic=np.concatenate([f[0] for f in frames]), ref=np.concatenate([f[1] for f in frames]),
                                res=np.concatenate([f[2] for f in frames]), adc=np.array([f[3] for f in frames]), words=" ".join(self._said_now)[:2000])
        except Exception as e:                                                  # noqa: BLE001
            log.info("aec: non riesco a salvare la diagnosi (%s)", str(e)[:80])

    def _recent_said(self) -> str:
        """Il testo di cui l'eco puo' essere nel microfono adesso: le frasi che le casse stanno suonando (non tutta la risposta, che include frasi ancora da dire)."""
        if hasattr(self.speaker, "recent_text"):
            return self.speaker.recent_text()                    # se non sta uscendo niente, qualunque parola e' dell'utente
        return " ".join(self._said_now)

    def _echo_canceller(self):
        """Il filtro che toglie dal microfono la voce di Aria (aec.py): solo se le casse sanno dire cosa stanno suonando; vive quanto Aria (la stanza non cambia)."""
        if not self.cfg["audio"].get("aec", True) or not hasattr(self.speaker, "ref_at") or int(self.cfg["audio"].get("input_rate", 16000)) != 16000:
            return None
        if getattr(self, "_aec", None) is None:
            from .aec import EchoCanceller
            self._aec = EchoCanceller(FRAME_SAMPLES, 16, 0.35)
        return self._aec

    def _cancel_echo(self, aec, frame):
        t = getattr(frame, "adc", None)
        if t is None or len(frame) != FRAME_SAMPLES:
            return frame
        try:
            ref = self.speaker.ref_at(t, FRAME_SAMPLES, 16000)
            if ref is None:
                return frame
            x = np.asarray(frame, dtype=np.float32) / 32768.0
            e = aec.process(x, ref)
            if self.cfg["audio"].get("aec_debug", False) and len(self._aec_dbg) < 1500:                    # ~48 s: microfono, riferimento e residuo dell'ultima risposta, per analizzarli (e tarare il filtro)
                self._aec_dbg.append((x.astype(np.float16), ref.astype(np.float16), e.astype(np.float16), float(getattr(frame, "adc", 0.0))))
            return (np.clip(e, -1.0, 1.0) * 32767.0).astype(np.int16)
        except Exception as ex:                                              # noqa: BLE001
            log.warning("cancellazione dell'eco non riuscita (%s): la spengo", str(ex)[:100])
            self._aec = None
            self.cfg["audio"]["aec"] = False
            return frame

    # ---------------------------------------------------------------- diagnosi del microfono
    def _record_utterance(self, audio, text: str) -> None:
        """Log con durata e livello (picco/rms in dBFS) e, se audio.save_utterances, il WAV in <data_dir>/utterances (ultimi 40)."""
        from .stt import audio_stats
        peak, rms = audio_stats(audio)
        log.info("TU (%.1fs, picco %.0f dB, rms %.0f dB): %s", len(audio) / 16000, peak, rms, text)
        if peak < -40:
            log.warning("microfono molto basso (picco %.0f dB): avvicinati o alza il volume di ingresso in Impostazioni di Sistema", peak)
        elif peak > -1:
            log.warning("microfono in saturazione (picco %.0f dB): abbassa il volume di ingresso", peak)
        if not self.cfg["audio"].get("save_utterances"):
            return
        import os
        import time as _t
        import wave
        d = os.path.join(self.cfg["data_dir"], "utterances")
        os.makedirs(d, exist_ok=True)
        slug = "".join(ch if ch.isalnum() else "_" for ch in text)[:40]
        with wave.open(os.path.join(d, f"{_t.strftime('%H%M%S')}_{slug}.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(audio.astype(np.int16).tobytes())
        for old in sorted(os.listdir(d))[:-40]:
            os.unlink(os.path.join(d, old))

    # ---------------------------------------------------------------- varie
    def _play_chime(self, freqs: list[float]) -> None:
        try:
            self.speaker.play(tone(freqs, sr=self.cfg["audio"]["output_rate"]), self.cfg["audio"]["output_rate"])
        except Exception:                                            # noqa: BLE001
            pass

    async def announce(self, text: str) -> None:
        """Parla fuori da una conversazione (es. timer scaduto): aspetta che Aria sia a riposo."""
        for _ in range(120):
            if not self.in_session and self.hub.state == State.IDLE:
                break
            await asyncio.sleep(0.5)
        try:
            self._play_chime(CHIME_TIMER)
            pcm, sr = await self._tts(text)
            self.hub.set_state(State.SPEAKING)
            self.speaker.play(pcm, sr)
            await self.speaker.wait_done()
        finally:
            self.hub.set_state(State.IDLE)

    # ---------------------------------------------------------------- memoria: imparare, chiedere, ricordare
    def _refresh_prompt(self, query: str) -> None:
        """Ad ogni frase il prompt riporta quello che Aria sa e che c'entra con quello che hai appena detto."""
        import datetime as dt
        ctx = self.memory.context(query, self.cfg["memory"]["max_facts_in_prompt"], include_last=sum(1 for m in self.history if m["role"] == "user") <= 2) if self.memory else ""
        notes: list[str] = []
        if self.cfg.get("human", {}).get("hints", True):                           # le «note di regia»: umore del giorno + come rispondere a QUESTA frase
            gender = self.memory.get_profile("gender") if self.memory else None
            past = self.history[:-1]
            self._rhythm = rhythm.plan(past, query, style.detect_mood(query), style.long_kind(query), prev=self._rhythm_prev) if self.cfg.get("human", {}).get("rhythm", True) else None
            self._rhythm_prev = self._rhythm.mode if self._rhythm else None
            notes = [style.session_tone(dt.datetime.now()), style.turn_hint(past, query, gender, turn=self._rhythm)]
        self.sys_prompt = self._build_system(self.persona, self.cfg, "\n".join(x for x in (ctx, self._hint, *notes) if x))
        self._hint = ""

    def _learn(self, text: str) -> tuple[str | None, str | None]:
        """Impara da cio' che l'utente ha detto (solo regole esplicite: vedi learn.py). Restituisce (risposta_di_Aria, frase_da_rifare):
        la risposta c'e' se l'utente si e' solo presentato/ha solo risposto alla domanda; la frase da rifare e' il meteo chiesto prima di sapere la citta'."""
        if not self.memory:
            return None, None
        mem, pending, self.pending = self.memory, self.pending, None
        if pending and intent.detect(text) is not None:                           # una richiesta («metti della musica») non e' la risposta a «come ti chiami?»
            pending = None
        gender = learn.parse_gender(text)                                      # «sono stanca»: cosi' sa se dire «stanco» o «stanca»
        if gender and mem.get_profile("gender") != gender:
            mem.set_profile("gender", gender)
            log.info("MEMORIA: genere = %s", gender)
        short = len(text.split()) <= 7
        if pending and learn.is_decline(text):
            return i18n.pick("Va bene, nessun problema.", "Okay, no problem."), None
        old_name = mem.get_profile("name")
        denied = learn.parse_name_denial(text)
        if denied and old_name and denied.lower() == old_name.lower():
            mem.del_profile("name")
            self.pending = "name"
            return i18n.pick("Scusa, ho capito male. Come ti chiami?", "Sorry, I got that wrong. What's your name?"), None
        ack = rewrite = None
        name = learn.parse_name(text, expect=(pending == "name"))
        if name:
            mem.set_profile("name", name)
            log.info("MEMORIA: nome = %s", name)
            self._hint = i18n.pick(f"Si è appena presentato: si chiama {name}.", f"They just introduced themselves: their name is {name}.")
            if short or pending == "name":
                ack = i18n.pick(f"Piacere, {name}!" + (" Aggiornato." if old_name and old_name != name else " Se ho capito male il nome, correggimi pure."),
                                f"Nice to meet you, {name}!" + (" Updated." if old_name and old_name != name else " If I got the name wrong, just correct me."))
        old_city = mem.get_profile("city")
        denied = learn.parse_city_denial(text)
        if denied and old_city and denied.lower() == old_city.lower():
            mem.del_profile("city")
        city = None if name and pending != "city" else learn.parse_city(text, expect=(pending == "city"))
        if city:
            mem.set_profile("city", city)
            log.info("MEMORIA: città = %s", city)
            self._hint = (self._hint + " " if self._hint else "") + i18n.pick(f"Ha detto che abita a {city}.", f"They said they live in {city}.")
            if self._weather_day and pending == "city":
                rewrite, self._weather_day = i18n.pick(f"che tempo fa {self._weather_day}", f"what's the weather {self._weather_day}"), None
            elif short or pending == "city":
                ack = ack or i18n.pick(f"{city}, bene. Me la segno.", f"{city}, nice. I'll note it down.")
        if pending == "city" and not city:
            self._weather_day = None
        for f in learn.extract(text):
            if mem.add_fact(f.text, f.importance, f.due, f.kind):
                log.info("MEMORIA: %s (importanza %d)", f.text, f.importance)
        return (None if rewrite else ack), rewrite

    async def _say(self, text: str) -> None:
        """Dice una frase gia' pronta (con stato, livelli e sottotitoli come una risposta normale)."""
        text = strip_emoji(text)
        name = self._user_name()
        if name and re.search(rf"\b{re.escape(name)}\b", text):
            self._name_turn = self._turn_no
        log.info("ARIA: %s", text)
        if not self._captions_synced():
            self.hub.transcript("aria", text, final=False)
        q: asyncio.Queue = asyncio.Queue()
        await q.put((text, asyncio.create_task(self._tts(text))) if self._captions_synced() else asyncio.create_task(self._tts(text)))
        await q.put(None)
        await self._consume(q)
        if not getattr(self.mic, "cleaned", False):
            if not self.cfg["audio"]["barge_in"]:
                await asyncio.sleep(0.3)
            self.mic.flush()
        self.history.append({"role": "assistant", "content": text})

    def _hour(self) -> int:
        """L'ora locale (un metodo a parte: i test la fissano, cosi' non dipendono da quando girano)."""
        import datetime as dt
        return dt.datetime.now().hour

    async def _maybe_ask(self) -> None:
        """Dopo la prima risposta, se non conosce il nome (o la citta') lo chiede, una volta sola per conversazione e senza insistere."""
        if not self.memory or self._asked_session or self.pending or self.pending_slot is not None or self.pending_confirm is not None:
            return                                                              # ha appena fatto una domanda sua (o aspetta un si'): non ne aggiunge un'altra
        recent = [m["content"] for m in self.history if m["role"] == "user"][-3:]
        hour = self._hour()
        if any(style.detect_mood(t) in ("triste", "ansioso", "arrabbiato", "malato", "insonnia", "stanco") for t in recent) or hour >= 23 or hour < 6:
            return                                                              # una domanda personale non si fa a chi e' giu', agitato o sveglio a notte fonda
        now = time.time()
        for what, phrases in (("name", ASK_NAME_EN if i18n.is_en() else ASK_NAME), ("city", ASK_CITY_EN if i18n.is_en() else ASK_CITY)):
            if self.memory.get_profile(what):
                continue
            n, last = self.memory.times_asked(what)
            if n >= ASK_MAX or now - last < ASK_EVERY_H * 3600:
                continue
            self._asked_session = True
            self.memory.mark_asked(what)
            self.pending = what
            await self._say(random.choice(phrases))
            return

    async def _ask_city_for_weather(self, arg: str):
        """Il meteo serve ma non si sa dove abita: lo chiede e, appena risponde, rifa' la domanda del meteo."""
        self._weather_day = (("tomorrow" if "tomorrow" in arg.lower() else "today") if i18n.is_en() else ("domani" if "domani" in arg.lower() else "oggi"))
        self.pending = "city"
        if self.memory:
            self.memory.mark_asked("city")
        msg = i18n.pick("Per dirti che tempo fa mi serve la città: dove abiti?", "To tell you the weather I need the city: where do you live?")
        self.history.append({"role": "assistant", "content": msg})
        yield "sentence", msg

    async def _generate_text(self, system: str, user: str, max_tokens: int = 600, temperature: float | None = None) -> str:
        """Una richiesta al chatbot fuori dal carattere di Aria e piu' lunga di una frase parlata (testi, riassunti)."""
        kw = {"temperature": temperature} if temperature is not None else {}
        out = "".join([t async for t in self.router.llm_stream([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                                                 max_tokens=max_tokens, **kw)])
        return strip_think(out).strip()

    def _brain_down_message(self) -> str:
        if any((b.get("llm") or {}).get("kind") == "mlx-lm" for b in self.router.brains):
            return i18n.pick("Scusa, non riesco a pensare adesso. Controlla nelle Impostazioni che il chatbot sia scaricato.", "Sorry, I can't think right now. Check in Settings that the chatbot has been downloaded.")
        return i18n.pick("Scusa, non riesco a pensare adesso. Controlla che Ollama sia acceso.", "Sorry, I can't think right now. Check that Ollama is running.")

    async def _revive(self, stage: str) -> bool:
        """Nessun chatbot risponde: se e' Ollama (locale) lo riapre e aspetta che sia pronto."""
        from . import ollama
        if stage != "llm" or not any(ollama.is_local((b.get("llm") or {}).get("base_url")) for b in self.router.brains):
            return False
        try:
            pcm, sr = await self.router.synthesize(i18n.pick("Un attimo, sto svegliando il mio cervello.", "One moment, I'm waking up my brain."))
            self.speaker.play(pcm, sr)
        except Exception:                                            # noqa: BLE001
            pass
        return await asyncio.to_thread(ollama.ensure_running, 30.0)

    async def _remember_session(self, history: list[dict]) -> None:
        """A fine conversazione: chiede al modello fatti durevoli sull'utente + un riassunto di una riga."""
        if not self.cfg.get("memory", {}).get("auto_extract", False):    # spento: il modello piccolo inventava nomi e luoghi ("Luca", "Roma")
            return
        convo = "\n".join(f"{('User' if i18n.is_en() else 'Utente') if m['role'] == 'user' else 'Aria'}: {m['content']}" for m in history[-12:])
        prompt = (i18n.pick("Leggi questa conversazione. Scrivi, una per riga, fino a 3 informazioni DUREVOLI sull'utente "
                            "(nome, famiglia, gusti, impegni, progetti) con il prefisso 'FATTO: '. Se non ce ne sono, nessuna riga FATTO. "
                            "Poi una riga 'RIASSUNTO: ' di massimo 15 parole su cosa vi siete detti.",
                            "Read this conversation. Write, one per line, up to 3 LASTING facts about the user "
                            "(name, family, tastes, commitments, projects) with the prefix 'FATTO: '. If there are none, no FATTO line. "
                            "Then one line 'RIASSUNTO: ' of at most 15 words about what you talked about.") + "\n\n" + convo)
        try:
            out = "".join([t async for t in self.router.llm_stream([{"role": "user", "content": prompt}])])
        except Exception as e:                                       # noqa: BLE001
            log.debug("riassunto non riuscito: %s", e)
            return
        for line in strip_think(out).splitlines():
            line = line.strip()
            if line.upper().startswith("FATTO:"):
                self.memory.add_fact(line[6:])
            elif line.upper().startswith("RIASSUNTO:"):
                self.memory.add_session(line[10:])
