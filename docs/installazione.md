# Installazione (Mac)

Ci sono due strade: **scaricare l'app già pronta** dalle Release (la più semplice) oppure **compilarla** dai sorgenti.

## Requisiti

- Mac con chip Apple, 16 GB di RAM consigliati (la versione «Leggera» delle Impostazioni è pensata per Mac con 8 GB, ma non è stata provata lì).
- macOS 26 o successivo.
- Circa 7 GB liberi su disco (app, modelli) e una connessione internet per il primo avvio.
- Solo per compilare dai sorgenti: gli strumenti di Xcode da riga di comando (`xcode-select --install`), che compilano l'app e i programmi di supporto in Swift.

## Scaricare l'app

1. Dalle [Release](https://github.com/GianmarcoLugaresi/Aria/releases) scarica `Aria-<versione>-macos-arm64.zip` e, se vuoi controllare che il file sia integro, anche `…zip.sha256`:

   ```bash
   cd ~/Downloads
   shasum -a 256 -c Aria-0.3.1-macos-arm64.zip.sha256
   ```

2. Decomprimi (doppio clic) e trascina `Aria.app` in **Applicazioni**. L'app pesa circa 1,6 GB perché contiene Python e le librerie (MLX, PyTorch per la voce, Whisper…): non c'è altro da installare.
3. **La prima volta macOS non la apre**, perché non è «notarizzata» da Apple (serve un abbonamento a pagamento per sviluppatori). Hai due modi, a scelta:
   - dal Terminale: `xattr -dr com.apple.quarantine /Applications/Aria.app`, poi apri l'app;
   - oppure apri l'app, ignora l'avviso, vai in Impostazioni di Sistema ▸ Privacy e sicurezza, in fondo premi **Apri comunque** e conferma.

   Lo fai una volta sola per ogni versione scaricata. Se preferisci non togliere la protezione a un'app scaricata, compilala tu dai sorgenti (sezione sotto): leggi il codice e la compili sul tuo Mac.
4. All'apertura Aria crea `~/Library/Application Support/Aria` con `config.yaml` e `persona.md` (se non ci sono) e scarica i modelli: Whisper large-v3-turbo a 4 bit (0,46 GB), il chatbot Gemma 3 4B (2,6 GB) e la voce Pocket TTS (0,25 GB). Finché scarica, nel menu in alto c'è «Primo avvio: sto scaricando i modelli…»; se la rete cade riprova da sola ogni minuto. macOS chiede il permesso per il **microfono**: concedilo.
5. Quando il menu dice che è pronta, di' «Hey Aria» o premi ⌥ Spazio.

Aggiornare: scarica la nuova versione e sostituisci `Aria.app` (esci prima dall'app). Configurazione, carattere, memoria e modelli restano dove sono. Dopo ogni nuova versione scaricata macOS considera l'app «nuova»: i permessi facoltativi (schermo, Accessibilità) vanno ridati e il comando `xattr` va ripetuto.

Togliere Aria: esci dall'app, trascina `Aria.app` nel cestino e, se vuoi cancellare anche i dati, elimina `~/Library/Application Support/Aria`, `~/Library/Logs/Aria` e `~/.aria`. I modelli scaricati stanno in `~/.cache/huggingface/hub` (si tolgono anche dal cestino delle Impostazioni).

## Compilare dai sorgenti

```bash
git clone <questo repository>
cd Aria
./app/install.sh
open ~/Applications/Aria.app
```

Lo script:

1. installa `uv` (se manca) e crea un ambiente **Python 3.12 arm64** in `~/Library/Application Support/Aria/venv` (il Python di sistema può essere x86 sotto Rosetta, lento e senza MLX: per questo se ne usa uno nativo);
2. installa le librerie: Whisper e chatbot su GPU con Apple MLX, Pocket TTS, rilevamento voce, ricerca web, lettura di PDF;
3. copia il programma in `~/Library/Application Support/Aria/software` e compila i programmi di supporto (riconoscimento vocale di macOS, microfono con filtro eco, OCR, Accessibilità, riquadro che indica);
4. crea `config.yaml` e `persona.md` nella stessa cartella, **se non esistono già**: rilanciare lo script aggiorna il programma senza toccare la tua configurazione;
5. compila l'app e la mette in `~/Applications/Aria.app`;
6. scarica i modelli: Whisper large-v3-turbo a 4 bit (0,46 GB), il chatbot Gemma 3 4B (2,6 GB) e la voce Pocket TTS (0,25 GB).

La prima volta macOS chiede il permesso per il **microfono**: concedilo. Gli altri permessi sono facoltativi e li chiede solo quando servono (vedi sotto).

## Permessi

| Permesso | Quando serve | Dove |
|---|---|---|
| Microfono | sempre | Impostazioni di Sistema ▸ Privacy e sicurezza ▸ Microfono |
| Registrazione schermo | solo per «guarda lo schermo» con l'OCR o con il modello che vede | … ▸ Registrazione schermo (se la voce di Aria è già attiva ma non funziona, toglila con «−», riaggiungila e riapri l'app) |
| Accessibilità | solo per «dov'è il pulsante X?» con precisione | … ▸ Accessibilità |
| Automazione | la prima volta che usa Calendario, Promemoria o Musica | compare «Aria vuole controllare…»: consenti |
| Documenti / Scrivania | se scegli una cartella lì dentro | la chiede macOS |

L'app non è firmata con un certificato per la distribuzione. Con la firma «ad hoc» (quella di fabbrica, anche per l'app scaricata) macOS considera **ogni ricompilazione, o ogni nuova versione scaricata, un'app nuova** e i permessi vanno ridati. Per evitarlo, `app/build_app.sh` usa un certificato di firma del codice se ne trova uno nel Portachiavi (un certificato «Apple Development» gratuito, oppure uno creato da te chiamato «Aria Local»).

## Aggiornare

```bash
git pull
./app/install.sh
```

## Togliere Aria

```bash
./app/uninstall.sh
```

Toglie l'app e, se rispondi di sì, ambiente, configurazione e memoria (`~/Library/Application Support/Aria` e `~/.aria`). I modelli scaricati restano in `~/.cache/huggingface/hub` finché non li elimini dal cestino delle Impostazioni o a mano.

## Usare Ollama invece del chatbot interno

Non serve, ma se hai già Ollama puoi sceglierlo da Impostazioni ▸ chatbot (o scrivendo `base_url: http://127.0.0.1:11434/v1` e `model: "gemma3:4b"` al posto di `kind: mlx-lm` in `config.yaml`). Se Ollama è spento, Aria lo riapre da sola.
