# Aria per Windows (sperimentale)

[English version](README.md)

Aria su Windows 10/11, in italiano e in inglese (si sceglie dal menu dell'icona): icona nella barra delle applicazioni, scorciatoia da tastiera, la stessa schermata con l'onda di sfere e lo stesso "cervello" Python dell'app per Mac (cartella `software/`).

> **Stato onesto.** Questa versione è stata scritta **senza un PC Windows**. Cosa è stato verificato, e come:
> - **Il cervello Python gira su Windows**: tutta la batteria di test (oltre 1500 prove: richieste, memoria, file, ritmo delle risposte, intenzioni…) è stata eseguita con un vero Python 3.12 per Windows dentro Wine, e passa (restano escluse solo le prove che usano programmi o percorsi del Mac). Da qui è uscito un difetto vero: su Windows mancano i dati dei fusi orari, e `tzdata` ora è tra le librerie.
> - **Le chiamate a Windows funzionano** (provate nello stesso modo): scorciatoia con `RegisterHotKey`, voce nel registro per l'avvio automatico, una sola copia aperta, finestra che lascia passare i clic e non ruba il focus, controllo del processo padre, tasti multimediali, lettura del menu Start. Il vetro acrilico non si è potuto provare (Wine non lo ha).
> - **Gli script PowerShell** hanno la sintassi controllata con il parser vero di PowerShell, ma non sono mai stati eseguiti.
> - **La lingua inglese su Windows** (menu Lingua, testi, voci, schermata, installer) ha prove automatiche che girano su Mac e Linux (`software/tests/test_windows_en.py`: logica del menu con `pystray` vero, cambio lingua con il programma Python vero, schermata, messaggi). Le nuove prove non sono state rifatte sotto Wine, e **i due script PowerShell, riscritti in due lingue, non sono stati eseguiti né fatti leggere a PowerShell**: hanno solo controlli statici (parentesi e virgolette bilanciate, nessun nome di variabile che si scontri senza badare alle maiuscole).
> - **Non è mai stato visto funzionare su Windows**: la schermata (WebView2), l'icona nella barra, il microfono e la voce, l'installazione completa. Aspettati qualche difetto al primo avvio e aprine uno nei problemi del progetto con il contenuto di `%LOCALAPPDATA%\Aria\Logs\app.log` e `backend.log`.

L'app per Mac (Apple Silicon, con il Liquid Glass di macOS 26) è un'altra cosa e non cambia: qui sotto trovi cosa è uguale e cosa no.

## Cosa serve

- Windows 10 (1809 o successivo) o Windows 11, 64 bit.
- Un microfono e delle casse. **Meglio le cuffie**: senza la cancellazione dell'eco di macOS, con le casse Aria può sentire la propria voce.
- ~6 GB di spazio (ambiente Python, Whisper, voce, chatbot) e 8 GB di RAM (16 consigliati).
- [Ollama](https://ollama.com) per il chatbot (l'installer lo installa con winget se vuoi) e il componente *WebView2 Runtime* di Microsoft per la schermata (c'è già in Windows 11).
- Facoltativo ma consigliato: una scheda NVIDIA, per far girare Whisper sulla GPU (`-Gpu`).

## Installare

Da PowerShell, nella cartella del progetto:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\install.ps1            # con il processore
powershell -ExecutionPolicy Bypass -File .\windows\install.ps1 -Gpu       # con una scheda NVIDIA (CUDA 12)
powershell -ExecutionPolicy Bypass -File .\windows\install.ps1 -Lingua en # Aria e l'installer in inglese (it, en o auto: come Windows)
```

Lo script crea un ambiente Python 3.12 in `%LOCALAPPDATA%\Aria`, installa le librerie, copia il programma e crea `%APPDATA%\Aria\config.yaml` e `persona.md` (che puoi modificare). Poi aggiunge «Aria» al menu Start. Si può rilanciare per aggiornare senza perdere la configurazione. Altre opzioni: `-Modello qwen3:4b` (un altro chatbot di Ollama), `-Si` (nessuna domanda), `-Lingua it|en|auto` (la lingua di Aria e dei messaggi dell'installer; di fabbrica segue Windows). Gli stessi nomi in inglese: `-Model`, `-Yes`, `-Language`.

Per toglierla: `.\windows\uninstall.ps1`.

## Usarla

| Cosa | Come |
|---|---|
| Svegliarla | di' **«Hey Aria»** o premi **Ctrl + Alt + Spazio** (Alt + Spazio su Windows apre il menu della finestra, per questo è diversa dal Mac; cambia con la variabile `ARIA_HOTKEY`, ad esempio `Ctrl+Shift+A`) |
| Fermarla mentre parla | la stessa scorciatoia, oppure il menu dell'icona |
| Cambiare lingua (Automatica, Italiano, English) | menu dell'icona ▸ *Lingua*: cambia i testi del menu e della schermata, quello che Aria capisce e la voce, e riavvia il cervello (qualche secondo; passando all'inglese scarica la voce inglese, circa 0,2 GB) |
| Cambiare voce, silenziare il microfono, avviarla con Windows | menu dell'icona (accanto all'orologio; se non la vedi, è sotto la freccia ^); in inglese l'elenco delle voci è ridotto a quelle che parlano inglese |
| Scegliere la cartella dove legge e scrive i file | menu ▸ *Cartella di Aria…* |
| Capire cosa succede | menu ▸ *Mostra i log* |

## Cosa è uguale al Mac e cosa no

**Uguale** (è lo stesso codice): italiano e inglese (scelta della lingua, riconoscimento, voce, carattere `persona.en.md`, regole, testi parlati, schermata), carattere e modo di rispondere, memoria, timer, calcoli, meteo, Wikipedia, ricerca sul web, file e documenti nella tua cartella, riconoscimento delle richieste, e la schermata con l'onda di sfere.

**Diverso, perché su Windows non esiste lo stesso pezzo:**

| Mac (Apple Silicon) | Windows | Perché |
|---|---|---|
| Chatbot e Whisper su GPU Apple (MLX) | chatbot in **Ollama**, Whisper con **faster-whisper** (processore, o NVIDIA) | MLX gira solo sui chip Apple |
| Riconoscimento vocale integrato di Apple | solo Whisper | è un'API di macOS |
| Microfono con filtro eco (Voice Processing): si interrompe Aria parlando, anche con le casse | si ferma con la scorciatoia; con le cuffie si può attivare `barge_in: true` in `config.yaml` | Windows non offre lo stesso filtro eco |
| Vetro «Liquid Glass» | vetro acrilico di Windows (o un fondo scuro se non disponibile) | è una funzione di macOS 26 |
| Voci «naturali» (Qwen3-TTS) | voci di Pocket TTS | Qwen3-TTS qui usa MLX |
| Finestra Impostazioni (versioni Leggera/Media/Pesante, scelta e download dei modelli, interruttori delle funzioni, frase per chiamarla) | non c'è: si cambia `config.yaml`, e la lingua e la voce dal menu dell'icona | la finestra è scritta in SwiftUI |
| Leggere lo schermo, indicare un pulsante | non ancora | usano OCR, Accessibilità e Registrazione schermo di macOS |
| App Promemoria («ricordami domani alle nove di chiamare Mario») | promemoria di Aria: un timer a quell'ora precisa che lo dice a voce, salvato su disco (sopravvive al riavvio; non è in un'app né si sincronizza col telefono; «che promemoria ho» li elenca) | Windows non ha un'app Promemoria da comandare |
| Calendario (aggiungere e leggere eventi), Scorciatoie, controllo dell'app Musica | non ci sono (play/pausa/avanti/indietro vanno coi tasti multimediali) | sono app e funzioni del Mac |
| Domande sul computer (batteria, nome del wifi, IP, memoria e disco liberi, versione del sistema, da quanto è acceso) | ci sono, lette da Windows | |
| Aprire app e siti, volume, play/pausa/avanti/indietro | ci sono (menu Start, tasti multimediali; il volume preciso richiede il pacchetto `pycaw`) | |

## Come è fatta

```
windows/
  aria_win/        l'involucro: icona (pystray), schermata (pywebview + WebView2), scorciatoia (RegisterHotKey), avvio del backend, WebSocket, lingua (l10n.py)
  install.ps1      installazione      uninstall.ps1   disinstallazione      (due lingue)
  config.windows.yaml   configurazione di partenza
  assets/aria.ico  l'icona
```

Il backend è `software/aria` (identico al Mac, con piccole varianti dietro `sys.platform`: `winos.py` per app/volume/musica, `power.py` per la batteria, `ollama.py` e `main.py` per i processi). La schermata è `app/Resources/overlay.html` + `neural.js`, uguali a quelle del Mac. L'involucro avvia il backend, ascolta lo stato dal WebSocket locale (`127.0.0.1:8765`) e mostra o nasconde la schermata.

## Problemi comuni

- **Non compare la schermata ma c'è l'icona**: manca WebView2 Runtime o `pywebview`; vedi `app.log`.
- **Aria non ti sente**: Impostazioni di Windows ▸ Privacy e sicurezza ▸ Microfono ▸ «Consenti alle app desktop di accedere al microfono».
- **Il menu o la schermata sono nella lingua sbagliata**: menu dell'icona ▸ *Lingua*; «Automatica» segue la lingua di visualizzazione di Windows.
- **«Ctrl+Alt+Spazio» non fa niente**: la usa un altro programma; imposta `ARIA_HOTKEY` (variabile d'ambiente utente) e riapri Aria.
- **Risponde lentamente**: usa un chatbot più piccolo (`-Modello gemma3:1b`) o, con una NVIDIA, `-Gpu`.
- **Windows Defender chiede conferma per `pythonw.exe`**: è l'ambiente Python di Aria; il programma non è firmato.
