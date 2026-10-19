# Sviluppo e test

## Ambiente

```bash
cd software
python3.12 -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[test]"
python -m pytest -q
```

Le prove non usano né microfono né modelli veri: il chatbot, la voce, il riconoscimento e l'audio sono finti (`tests/test_conversation.py` ha i componenti di base). Una sola prova prova un modellino vero se è già in cache (`ARIA_SKIP_REAL_MODEL=1` la salta). Sul Mac servono anche gli strumenti di Xcode per compilare l'app, ma non per i test Python.

Le prove che usano i programmi di supporto di macOS o percorsi POSIX si saltano da sole su altri sistemi (`tests/conftest.py`): la suite gira anche con Python per Windows.

## Come è organizzato il codice

Un modulo per argomento (mappa in [come-funziona.md](come-funziona.md)). Alcune convenzioni:

- **Il linguaggio è l'italiano**: nomi dei test, commenti, messaggi, regole di riconoscimento delle richieste. I nomi degli oggetti nel codice sono in inglese.
- **Il modello non decide cosa eseguire**: le richieste d'azione le riconosce `intent.py` con regole; i poteri sul computer (`powers.py`, `filetools.py`, `screen.py`) hanno controlli propri e il chatbot non può lanciarli. Ogni nuova azione va gestita così e coperta da una prova che verifichi anche il caso in cui il modello provi a lanciarla da solo.
- **I testi detti a voce non finiscono mai dentro un comando**: si passano come argomenti separati (`macos.py` per AppleScript, `winos.py` per Windows).
- **Ogni abbellimento «da persona» si può spegnere** da `config.yaml` (`human.*`).
- Le prove che confrontano frasi esatte usano `textutil.VARIETY = False` (di fabbrica nei test): le conferme sono sempre la prima variante.

## Aggiungere o cambiare una richiesta

1. Le regole sono in `aria/intent.py`; le forme di cortesia («potresti…», «mi dici…») le toglie `phrasing.canonical`.
2. Aggiungi la frase a uno dei corpora in `tests/intent_corpus*.py` (frase, strumento atteso, parti dell'argomento): sono prove parametrizzate che scoprono subito le regressioni.
3. `scripts/eval_intents.py` e `eval_intents2.py` stampano le frasi sbagliate di due liste di richieste «dette come le direbbe una persona».

## Misurare lo stile delle risposte

`scripts/humanness.py` fa recitare ad Aria scene di prova con un chatbot vero e conta i difetti tipici dei modelli piccoli. Si usa per confrontare due versioni dello stesso comportamento sulle stesse scene (con più semi casuali: una singola prova varia parecchio):

```bash
PYTHONPATH=. python scripts/humanness.py --persona ../anima/persona_compatta.md --model mlx-community/gemma-4-e4b-it-4bit \
    --no-think --temp 0.65 --top-p 0.92 --min-p 0.05 --rep 1.05 --seed 7 --show               # com'era
... --rhythm                                                                                    # con il motore del ritmo
```

## L'app per Mac

```bash
./app/build_app.sh build            # compila e assembla build/Aria.app
```

Serve l'SDK di macOS 26. Con la firma «ad hoc» i permessi di macOS vanno ridati a ogni ricompilazione (vedi [installazione](installazione.md)).

### L'app scaricabile

```bash
./app/package_release.sh [cartella]     # crea Aria-<versione>-macos-arm64.zip (+ .sha256), default app/dist
```

Lo script compila l'app, copia dentro `Aria.app/Contents/Resources/backend` un Python 3.12 portatile (quello di `uv`) con le librerie di `app/release-requirements.txt` (versioni fissate), il pacchetto `aria` e i programmi di supporto compilati per macOS 26 (in `Resources/bin`, che l'app passa al Python con `ARIA_BIN`), toglie il superfluo, precompila il bytecode, firma tutto «ad hoc» e comprime. Non c'è notarizzazione: chi scarica deve togliere la quarantena (vedi [installazione](installazione.md)).

All'avvio `Paths.swift` guarda se esiste `Resources/backend`: se c'è usa quello, altrimenti l'ambiente creato da `install.sh` (`paths.json`). Per provare l'app senza toccare la tua cartella di Aria: `ARIA_HOME=/percorso/finto` sposta cartella personale, log e configurazione, e `ARIA_FAKE_AUDIO=frase.wav` (WAV mono 16 kHz) sostituisce microfono e altoparlanti con un file. `app/Package.swift` descrive il pacchetto; le sorgenti sono in `app/Sources/Aria`. Per provare l'overlay senza backend: `ARIA_NO_BACKEND=1 build/Aria.app/Contents/MacOS/Aria`.

## Windows

`windows/` è l'involucro per Windows e `software/aria/winos.py` il corrispettivo di `macos.py`. Le chiamate a Windows sono dietro `sys.platform == "win32"` e dentro `try/except`: se una non funziona la funzione si degrada invece di rompersi. Vedi [windows/README.md](../windows/README.md) per lo stato.
