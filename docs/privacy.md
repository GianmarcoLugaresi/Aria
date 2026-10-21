# Privacy

Aria è pensata per non mandare in giro quello che dici. Questa pagina elenca, senza giri di parole, cosa resta sul tuo computer, cosa esce e cosa viene salvato.

## Cosa resta sul computer

- **L'audio**: il microfono è letto dal programma in locale; la trascrizione la fa Whisper (o il riconoscimento di macOS) sul tuo Mac. Nessuna registrazione viene inviata a nessuno.
- **Il chatbot e la voce** girano in locale.
- **La memoria**: fatti che hai detto di te (nome, città, impegni, gusti), il riassunto dell'ultima conversazione e i timer, in `~/.aria` (`memoria.db`, `timers.json`, `voce.txt`). Aria impara solo da ciò che dici, con regole esplicite, non con il chatbot.
- **Lo schermo**: se accendi la lettura dello schermo, lo cattura solo quando glielo chiedi; l'immagine sta in un file temporaneo cancellato subito dopo.

## Cosa esce in rete

| Quando | Verso dove | Cosa |
|---|---|---|
| prima installazione, cambio modelli e cambio lingua (la voce inglese) | Hugging Face | il nome del modello (e l'indirizzo IP, come ogni download) |
| «che tempo fa?» | Open-Meteo | il nome della città (o le coordinate) |
| «cerca…», fatti che cambiano, ricerche e documenti sui fatti | DuckDuckGo e altri motori (via `ddgs`), Wikipedia, le pagine trovate | il testo della domanda; per i documenti, le pagine pubbliche lette |
| briefing del mattino | il feed delle notizie (ANSA di fabbrica) | una richiesta di quel feed |

Niente telemetria, niente account, niente chiavi.

## Cosa viene salvato su disco

| Cosa | Dove | Note |
|---|---|---|
| Configurazione e carattere | `~/Library/Application Support/Aria/` | `config.yaml`, `settings.json`, `persona.md` |
| Memoria, timer, voce scelta | `~/.aria/` | si cancella togliendo la cartella |
| Log | `~/Library/Logs/Aria/` (`app.log`, `backend.log`) | contengono le frasi trascritte e le risposte; si possono cancellare |
| Modelli | `~/.cache/huggingface/hub` | si tolgono dal cestino delle Impostazioni |
| Registrazioni delle tue frasi | `~/.aria/utterances` | **solo** se accendi `audio.save_utterances` (spento di fabbrica) |

## Permessi

Microfono (sempre); Registrazione schermo e Accessibilità (solo se accendi la lettura dello schermo); Automazione (la prima volta che usa Calendario, Promemoria o Musica). Ognuno si revoca dalle Impostazioni di Sistema.

## Cancellare tutto

`./app/uninstall.sh` (e rispondi di sì), poi, se vuoi, `rm -rf ~/.cache/huggingface/hub/models--*`.
