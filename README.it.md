# Aria

Assistente vocale da scrivania, in italiano e in inglese (si sceglie nelle Impostazioni), che gira tutto sul tuo computer: niente abbonamenti, niente account, niente audio inviato a nessuno.

Dici «Hey Aria» (o premi ⌥ Spazio), le parli come a una persona e risponde a voce. Sa chiacchierare, dire l'ora e il meteo, fare calcoli e timer, cercare sul web, ricordarsi di te, scrivere e leggere file in una cartella tua e, se glielo permetti, aprire app, mettere musica, creare promemoria ed eventi o guardare lo schermo.

[English version](README.md)

## Come funziona

```
microfono ─► «Hey Aria» ─► rilevamento voce ─► riconoscimento (Whisper) ─► chatbot locale ─► voce (Pocket TTS) ─► altoparlanti
                                                         │                     ▲
                                                         └─► strumenti: ora, meteo, timer, calcoli, ricerca, file, app…
```

- Il **chatbot** è un modello piccolo (Gemma 3 4B) che gira sul tuo Mac con Apple MLX; il riconoscimento vocale è Whisper (o quello integrato di macOS, se lo scegli); la voce è Pocket TTS. I modelli si scaricano la prima volta (circa 3,5 GB) e si gestiscono dalle Impostazioni.
- I modelli piccoli sbagliano facilmente, quindi Aria li guida: le richieste ovvie (ora, meteo, timer, calcoli, «ricordati che…») le riconosce il programma e non il chatbot; le risposte sono tenute corte e senza formule da assistente; ogni potere sul computer parte solo da una richiesta detta da te, mai da quello che scrive il modello.
- Dopo ogni risposta resta in ascolto qualche secondo: puoi continuare a parlare senza richiamarla, e puoi interromperla.

Più dettagli in [docs/come-funziona.md](docs/come-funziona.md).

## Cosa serve

- **Mac con chip Apple** (M1 o successivi), 16 GB di RAM consigliati.
- **macOS 26 o successivo**: l'app usa il vetro Liquid Glass e il riconoscimento vocale integrato di macOS 26. Su versioni precedenti non si apre.
- Circa 7 GB liberi su disco (l'app pesa 1,6 GB una volta decompressa, i modelli altri 3,5 GB).
- Gli strumenti di Xcode da riga di comando (`xcode-select --install`) **solo se la compili tu** dai sorgenti.

Su **Windows** esiste una versione sperimentale (vedi sotto). Linux e Intel Mac non sono supportati dall'app, ma il «cervello» Python si può usare da terminale.

## Installare

### Scaricando l'app (il modo più semplice)

1. Dalla pagina delle [Release](https://github.com/GianmarcoLugaresi/Aria/releases) scarica `Aria-1.0.1-macos-arm64.zip` (circa 0,5 GB) e decomprimilo: dentro c'è `Aria.app`, con Python e tutte le librerie già dentro.
2. Trascina `Aria.app` nella cartella **Applicazioni**.
3. L'app non è firmata con un certificato Apple a pagamento (non è «notarizzata»), quindi la prima volta macOS non la apre. Dal Terminale, una volta sola:

   ```bash
   xattr -dr com.apple.quarantine /Applications/Aria.app
   ```

   (oppure: prova ad aprirla, poi Impostazioni di Sistema ▸ Privacy e sicurezza ▸ **Apri comunque**).
4. Aprila. Alla prima apertura scarica i modelli (circa 3,5 GB: nel menu in alto compare «Primo avvio: sto scaricando i modelli…») e macOS chiede il permesso per il microfono: concedilo. Quando il menu dice che è pronta, di' «Hey Aria». Parte nella lingua del Mac (italiano se il Mac è in italiano, altrimenti inglese): si cambia quando vuoi da **Impostazioni ▸ Lingua**.

### Compilandola tu dai sorgenti

```bash
git clone https://github.com/GianmarcoLugaresi/Aria.git
cd Aria
./app/install.sh
open ~/Applications/Aria.app
```

Lo script crea un ambiente Python 3.12 nativo in `~/Library/Application Support/Aria`, installa le librerie, compila l'app, crea la configurazione (`config.yaml`) e il carattere (`persona.md`) e scarica i modelli. Si può rilanciare per aggiornare senza perdere la configurazione.

Per togliere tutto: `./app/uninstall.sh` (o, per l'app scaricata, vedi [docs/installazione.md](docs/installazione.md)). Altre istruzioni e i permessi facoltativi (schermo, Accessibilità, Automazione) sono nello stesso file.

## Usarla

| | |
|---|---|
| Svegliarla | «Hey Aria», anche tutto d'un fiato («Hey Aria, che tempo fa domani?»), oppure **⌥ Spazio** |
| Fermarla mentre parla | ⌥ Spazio di nuovo, oppure di' «basta» o «aspetta» |
| Cambiare voce, silenziare il microfono, avviarla all'accesso | menu dell'icona nella barra dei menu |
| Scegliere lingua, modelli e poteri | menu ▸ **Impostazioni…** |
| Capire cosa succede | menu ▸ **Mostra i log** |

Qualche frase: «che ore sono a Tokyo?», «mettimi un timer di dieci minuti», «scrivimi una poesia per mia madre» (la salva nella cartella che hai scelto), «ricordami domani alle nove di chiamare Marco», «secondo te meglio il mare o la montagna?», «dov'è il pulsante Esporta?».

## Privacy

Audio, trascrizioni, memoria e modelli restano sul tuo computer. Si esce in rete solo per: i modelli (Hugging Face, la prima volta), il meteo (Open-Meteo: la città), Wikipedia e la ricerca web quando chiedi fatti che cambiano (il testo della domanda), le pagine che legge per scrivere un documento sui fatti. L'elenco completo, cosa viene salvato su disco e come cancellarlo sono in [docs/privacy.md](docs/privacy.md).

I poteri sul Mac (promemoria, calendario, musica, app, Scorciatoie, schermo) si accendono e spengono uno per uno dalle Impostazioni; quelli che guardano lo schermo sono spenti di fabbrica.

## Windows (sperimentale)

In [windows/](windows/) c'è una versione per Windows 10/11: stessa schermata e stesso cervello, in italiano e in inglese come l'app per Mac (menu *Lingua* dell'icona, installer in due lingue), con chatbot in Ollama e Whisper con faster-whisper. È stata provata solo in parte e senza un PC Windows vero: leggi lo [stato onesto](windows/README.it.md) prima di installarla.


## Sviluppo e test

```bash
cd software
python -m pip install -e ".[test]"
python -m pytest -q          # oltre 1800 prove, senza audio né modelli veri
```

I test usano un chatbot e una voce finti. `scripts/humanness.py` fa recitare ad Aria conversazioni di prova con il chatbot vero e misura i difetti tipici dei modelli piccoli (risposte lunghe, domanda in fondo a ogni frase, formule da psicologo…). Vedi [docs/sviluppo.md](docs/sviluppo.md).

## Limiti noti

- È sviluppata e provata su un solo Mac (M2 Pro, 16 GB, macOS 26). Altre configurazioni possono dare sorprese.
- Un chatbot da 4 miliardi di parametri resta piccolo: ogni tanto scrive una frase strana, e i testi che produce vanno riletti prima di usarli. Un modello più grande (nelle Impostazioni) risponde meglio ma usa molta più memoria.
- Con le casse del Mac il microfono sente anche Aria: l'interruzione a voce usa il filtro eco di macOS e funziona meglio con le cuffie.
- Il riconoscimento di «Hey Aria» può sbagliare in ambienti rumorosi. La scorciatoia ⌥ Spazio può essere già usata da un'altra app.
- L'inglese è più recente dell'italiano: le regole coprono gli strumenti principali, il resto passa dal chatbot; provato con test automatici e con Whisper vero sulla voce di sistema inglese, non con molte voci e accenti reali. La voce naturale (Qwen3-TTS) c'è solo in italiano, e le configurazioni per Raspberry Pi / Piper in `software/` hanno ancora una voce italiana (il cambio lingua vale per l'app Mac e per la versione Windows, che usano Pocket TTS).

## Licenza e modelli

Il codice è sotto [licenza MIT](LICENSE). I modelli scaricati hanno licenze proprie (Gemma ha le sue condizioni d'uso, Pocket TTS è CC-BY-4.0, Qwen3-TTS è Apache-2.0): l'elenco è in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
