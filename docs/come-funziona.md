# Come funziona

## Il ciclo

```
attesa ──► «Hey Aria» ──► ascolto ──► pensiero ──► parola ──► (resta in ascolto ~8 s) ──► attesa
              │                         │              │
          VAD + Whisper            intenzioni      frasi inviate alla voce
          cercano la frase         + chatbot       appena sono complete
```

1. **Attesa.** Un rilevatore di voce leggero (Silero, su un solo thread) guarda il microfono; quando sente parlare, il riconoscimento vocale trascrive e cerca la frase «hey aria» (anche storpiata: «ehi aria»). Se la frase continua («Hey Aria, che tempo fa?»), il resto è già il comando.
2. **Ascolto.** Il rilevatore segue la tua frase e chiude il turno dopo ~0,8 s di silenzio (più a lungo se ti fermi dopo un «e poi…»).
3. **Intenzioni** (`intent.py`). Le richieste ovvie le riconosce il programma con regole, prima del chatbot: ora e data, meteo, timer, calcoli, «ricordati che…», file, app, musica, schermo… Lo strumento parte subito e, per i più semplici, la risposta è letta così com'è.
4. **Chatbot.** Il resto lo risponde il chatbot, con un prompt breve (carattere + data + cosa sa di te) e, per ogni frase, poche «note di regia» (`style.py`, `rhythm.py`, `examples.py`): come sembri stare, quanto lunga la risposta, che tipo di mossa (un parere netto, una spiegazione a strati, una domanda su un dettaglio…), niente due domande di fila. L'output è ripulito prima di essere detto: via «Certamente!», le esperienze inventate («ho letto che…»), il markdown, le parole inglesi.
5. **Strumenti.** Il modello non usa il «function calling» (inaffidabile sui modelli piccoli): se serve un dato scrive una riga come `[[METEO: Roma domani]]`, Aria la esegue e gli ridà il risultato per la risposta a voce. I poteri sul computer (`powers.py`, `filetools.py`, `screen.py`) non possono essere lanciati dal modello: partono solo da una richiesta riconosciuta nella tua frase.
6. **Voce.** Le frasi vanno alla sintesi appena complete, spezzate dove si respira. `speech.py` trasforma ciò che si *legge* in ciò che si *dice* («18°C» → «diciotto gradi»). Dopo la sintesi si controlla che la frase non sia stata tagliata (`voicecheck.py`).

## Interrompere Aria

Il microfono, durante la risposta, sente anche la sua voce. Sul Mac si risolve in due modi, secondo la configurazione:

- con il **filtro eco di macOS** (Voice Processing, `software/helpers/aria_vpmic.swift`) la voce di Aria sparisce dal microfono e ciò che resta è l'utente: ogni ~0,2 s, se c'è voce, si trascrive e si guardano le *parole* (`bargein.py`);
- senza, un filtro adattivo (`aec.py`) toglie l'eco e/o si ascolta nelle pause tra una frase e l'altra.

Le parole che coincidono con quelle che Aria sta dicendo sono eco e si ignorano; «basta», «aspetta», «stop», «fermati» fermano subito.

## Mappa dei moduli (`software/aria/`)

| | |
|---|---|
| `conversation.py` | il ciclo: attesa, ascolto, pensiero, parola; interruzioni; strumenti |
| `main.py`, `config.py`, `persona.py` | avvio, configurazione (YAML + Impostazioni), prompt di sistema |
| `intent.py`, `phrasing.py`, `llmintent.py`, `timeparse.py` | capire le richieste: regole, forme di cortesia, ultima rete col chatbot, date e orari in italiano |
| `tools.py`, `everyday.py`, `worldclock.py` | ora, meteo, Wikipedia, ricerca, timer, calcoli, conversioni, fusi orari |
| `powers.py`, `macos.py`, `winos.py` | promemoria, calendario, musica, app, Scorciatoie (macOS); app e volume (Windows) |
| `filetools.py`, `workspace.py`, `docs.py` | scrivere e leggere file nella sola cartella di Aria; testo da PDF e Word |
| `screen.py`, `vision.py` | guardare lo schermo (OCR, Accessibilità, modello che vede) e indicare cose |
| `style.py`, `rhythm.py`, `examples.py`, `dialog.py`, `learn.py`, `memory.py`, `lexicon.py` | tono, ritmo, saluti, memoria, vocabolario |
| `stt.py`, `llm.py`, `tts.py`, `router.py`, `mlxpool.py`, `ollama.py`, `qwentts_server.py` | adattatori per riconoscimento, chatbot e voce; failover tra «cervelli» |
| `audio.py`, `vad.py`, `aec.py`, `bargein.py`, `wake.py`, `power.py` | microfono, altoparlante, rilevamento voce, eco, interruzione, batteria |
| `display.py`, `state.py`, `leds.py` | stato e WebSocket per l'overlay, il display e l'anello LED |
| `models.py`, `profiles.py` | Impostazioni: versioni (Leggera/Media/Pesante), modelli installati, poteri |

## Cervelli con failover (`router.py`)

Per ogni stadio (chatbot, riconoscimento, voce) la configurazione elenca più «cervelli» in ordine di preferenza; vince il primo raggiungibile e, se uno cade a metà, si passa al successivo. È pensato per l'oggetto fisico (un computer di casa veloce e un Raspberry di scorta), ma sul Mac basta un cervello solo.

## L'app (`app/`)

È un'app Swift senza finestre (`LSUIElement`): icona nella barra dei menu, scorciatoia globale (⌥ Spazio con `RegisterEventHotKey`), overlay (un `NSPanel` trasparente con la pagina `overlay.html`, in vetro Liquid Glass su macOS 26) e la finestra delle Impostazioni (SwiftUI). Avvia il backend Python come processo figlio, lo riavvia se cade e parla con lui per WebSocket locale (`127.0.0.1:8765`: stato, livello della voce, sottotitoli, comandi `wake`, `stop`, `mute`, `voice`). Le Impostazioni usano gli stessi moduli Python (`python -m aria.models …`).
