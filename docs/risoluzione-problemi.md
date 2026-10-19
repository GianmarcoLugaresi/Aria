# Se qualcosa non va

I log sono in `~/Library/Logs/Aria/backend.log` (il «cervello») e `app.log` (l'app): dal menu dell'icona, «Mostra i log».

| Problema | Cosa fare |
|---|---|
| **macOS non apre l'app scaricata («non può essere aperta», «danneggiata», «sviluppatore non verificato»)** | L'app non è notarizzata da Apple: `xattr -dr com.apple.quarantine /Applications/Aria.app` dal Terminale, poi riaprila; oppure Impostazioni di Sistema ▸ Privacy e sicurezza ▸ **Apri comunque**. Se l'hai aperta da una cartella protetta (Download), spostala prima in Applicazioni. |
| **Il menu dice «Primo avvio: sto scaricando i modelli…»** | Normale la prima volta: circa 3,5 GB, serve internet. Se la rete cade riprova da sola ogni minuto; l'avanzamento è in `backend.log`. Quando finisce, l'app parte da sola. |
| **Non mi sente** | Impostazioni di Sistema ▸ Privacy e sicurezza ▸ Microfono: Aria deve essere attiva. Se il log dice «microfono molto basso», avvicinati o alza il volume di ingresso. |
| **Non risponde a «Hey Aria»** | Prova ⌥ Spazio: se funziona, il riconoscimento della frase sbaglia (stanza rumorosa, voce bassa). Puoi cambiare la frase di attivazione dalle Impostazioni. |
| **⌥ Spazio non fa niente** | Un'altra app usa la stessa scorciatoia (macOS lascia registrarla a più app e vince l'ultima). Chiudi l'altra app o usa «Hey Aria». |
| **Dice che manca il permesso «Registrazione schermo» ma in Impostazioni è attivo** | È una voce di una versione precedente dell'app: selezionala, premi «−», chiedi di nuovo di guardare lo schermo e concedi. Se macOS lo chiede, esci da Aria e riaprila. Dopo ogni ricompilazione con firma «ad hoc» i permessi vanno ridati (vedi [installazione](installazione.md)). |
| **Si ferma da sola mentre parla** | Succede con le casse se l'eco rientra nel microfono. Usa le cuffie o abbassa il volume. |
| **Risponde lentamente / il Mac rallenta** | Impostazioni ▸ versione «Leggera». Con 8 GB di RAM evita «Pesante». Chiudi le app che usano molta memoria. |
| **Il chatbot scrive frasi strane** | Un modello da 4 miliardi di parametri sbaglia ogni tanto. Un modello più grande (Impostazioni ▸ chatbot) è più coerente ma pesa di più. |
| **«Ollama non risponde»** | Solo se hai scelto Ollama: aprilo, oppure scegli un chatbot «dentro Aria». |
| **Il Mac non va in stop con Aria aperta** | Con il microfono aperto macOS non dorme da solo. Aria chiude il microfono quando lo schermo è spento e il Mac è a batteria (`audio.sleep_on_battery`) e quando lo schermo si spegne durante un risveglio notturno. |
| **L'overlay copre qualcosa** | Lascia passare i clic; compare in basso al centro solo mentre parla. |
| **Voglio ripartire da zero** | `./app/uninstall.sh`, poi `./app/install.sh`. |

Se il problema è nuovo, apri una segnalazione con le ultime righe di `backend.log` (controlla prima che non contengano frasi che non vuoi condividere).
