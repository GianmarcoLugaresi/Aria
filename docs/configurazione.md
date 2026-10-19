# Configurazione

Ci sono tre livelli, dal più «fisso» al più «vivo»:

1. **`config.yaml`** (`~/Library/Application Support/Aria/config.yaml`): la configurazione di base, modificabile a mano. Dopo averla cambiata, esci da Aria dal menu e riaprila. Il modello è `app/config.app.yaml`, che ha un commento per ogni voce.
2. **`settings.json`** (stessa cartella): le scelte fatte dalla finestra Impostazioni (versione, modelli, poteri, cartella, frase di attivazione). Si *sovrappone* a `config.yaml` senza riscriverlo: per tornare indietro basta scegliere «Media» o cancellare il file.
3. **`persona.md`** (stessa cartella): il carattere di Aria, il prompt che le dice come parlare. Puoi cambiarlo a piacere; il modello per i modelli piccoli è `anima/persona_compatta.md`, quello esteso `anima/persona.md`.

## Le voci principali di `config.yaml`

| Voce | Cosa fa |
|---|---|
| `wake.phrase` | la frase di attivazione (di fabbrica «hey aria»; si cambia anche dalle Impostazioni) |
| `audio.input_device` / `output_device` | microfono e altoparlante (`null` = quelli predefiniti; un numero o parte del nome; `python -m aria.main --list-devices` li elenca) |
| `audio.voice_processing` | il microfono passa dal filtro eco di macOS: permette di interrompere Aria a voce anche con le casse |
| `audio.barge_in_words` | l'interruzione a parole (riascolta il microfono mentre parla e si ferma con «basta», «aspetta»…) |
| `audio.save_utterances` | salva come file audio le ultime 40 frasi che dici (spento di fabbrica: serve solo per capire errori di riconoscimento) |
| `audio.sleep_on_battery` | a batteria, con lo schermo spento da un minuto, smette di ascoltare e lascia dormire il Mac |
| `turn.end_silence_ms`, `turn.follow_up_timeout_s` | quanto silenzio chiude la tua frase; quanto resta in ascolto dopo una risposta |
| `brains` | chatbot, riconoscimento vocale e voce (vedi sotto) |
| `tools.web_search` | motore di ricerca (`ddgs`, oppure un tuo SearXNG) |
| `tools.news_feed` | feed delle notizie per il briefing (ANSA; `""` lo spegne) |
| `memory` | `enabled`, quanti fatti mettere nel prompt, quanti turni ricordare |
| `human.*` | le «finezze» da conversazione: ognuna si spegne (`greet`, `dialog_acts`, `hints`, `rhythm`, `clean_replies`, `pauses`, `ask_again`) e i tetti di lunghezza (`max_sentences`, `max_sentences_long`) |
| `location` | città, latitudine e longitudine per meteo e ora (di fabbrica vuoto: Aria te lo chiede) |

## Chatbot, riconoscimento, voce

```yaml
brains:
  - name: mac
    llm:
      kind: mlx-lm                                       # dentro Aria, con Apple MLX
      model: "mlx-community/gemma-3-text-4b-it-4bit"
      temperature: 0.65                                  # sotto 0.7 un modello piccolo resta coerente
    stt: {kind: mlx-whisper, model: "mlx-community/whisper-large-v3-turbo-q4"}
    tts: {kind: pocket, language: italian, voice: lola}
```

- **Chatbot**: `kind: mlx-lm` (MLX, dentro Aria) oppure un server compatibile OpenAI (`base_url`, `model`): Ollama, llama.cpp, LM Studio… Per i modelli che «ragionano» prima di rispondere (Qwen 3.5, Gemma 4) Aria imposta `reasoning_effort: none`, altrimenti consumano tutti i token senza rispondere.
- **Riconoscimento**: `mlx-whisper` (Mac), `apple` (riconoscimento integrato di macOS 26, scelto dalle Impostazioni), `faster-whisper` (CPU/GPU NVIDIA, usato su Windows), o un server compatibile OpenAI.
- **Voce**: `pocket` (Pocket TTS, 25 voci, solo CPU), `say` (la voce di sistema, nessun download), Piper o Kokoro. La «voce naturale» (Qwen3-TTS) è un potere a parte.
- Si possono elencare **più cervelli** per stadio: vince il primo raggiungibile e si passa al successivo se cade.

## I poteri (Impostazioni ▸ «Cosa può fare Aria sul tuo Mac»)

Ognuno ha un interruttore. Accesi di fabbrica: Scorciatoie, Promemoria, Calendario, Musica e volume, App e siti, Documenti, Briefing, indicare le cose sullo schermo, Accessibilità, riposo a batteria. **Spenti** di fabbrica: leggere lo schermo (con l'OCR o con un modello che vede; uno solo alla volta) e la voce naturale.

Regole che valgono sempre, scritte nel programma e non affidate al chatbot:

- i poteri partono solo da una richiesta riconosciuta nella tua frase; se il chatbot prova a lanciarne uno, viene rifiutato e finisce nel log;
- i tuoi testi arrivano agli script come argomenti separati, mai dentro il testo dello script;
- si aprono solo app installate e solo indirizzi `https` di siti pubblici (mai `file://`, indirizzi IP o `localhost`);
- le Scorciatoie chiedono prima «Vuoi che esegua…?»; si possono limitare a un elenco (`tools: {shortcuts: {allow: ["Buonanotte"]}}`);
- nessun potere cancella file, esegue comandi di terminale o manda messaggi a tuo nome.

## La cartella di Aria

Impostazioni ▸ «Cartella di Aria». Aria legge e scrive solo lì dentro: solo file di testo (`.md`, `.txt`; in lettura anche `.csv`, PDF e Word), mai file nascosti, niente cancellazioni né sovrascritture (se il nome esiste crea `… (2).md`), massimo 120 KB per file. Non accetta la Home intera, il disco, le cartelle di sistema o la Libreria.

## Da terminale

```bash
cd ~/Library/Application\ Support/Aria/software
PYTHONPATH=. ../venv/bin/python -m aria.models status --config ../config.yaml
PYTHONPATH=. ../venv/bin/python -m aria.models power screen_mac on --config ../config.yaml
PYTHONPATH=. ../venv/bin/python -m aria.models workspace set ~/Documents/Aria --config ../config.yaml
PYTHONPATH=. ../venv/bin/python -m aria.main --config ../config.yaml --text      # chat testuale, senza audio
```
