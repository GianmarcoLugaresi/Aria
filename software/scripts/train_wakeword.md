# "Hey Aria": come ottenere un buon riconoscimento della frase

Tre strade, dalla più semplice alla migliore. Aria le supporta tutte (`wake.mode` in config).

## 1. `mode: stt` — nessun addestramento (parti da qui)
Il microfono ascolta, il VAD ritaglia le frasi e Whisper le trascrive; se contengono "hey aria" (anche storpiato: "ciao arya", "ciao area")
Aria si sveglia, e il resto della frase diventa il primo comando: *«Hey Aria, che tempo fa domani?»* funziona in un colpo solo.
- Pro: funziona subito, in italiano, con qualsiasi frase.
- Contro: sul Raspberry ogni frase che senti costa 1-2 s di CPU (anche la TV), e la reazione al wake word è meno immediata.

## 2. `mode: model` — modello openWakeWord (il migliore, 0 CPU quasi)
openWakeWord (Apache 2.0) riconosce una frase con una rete minuscola e la riconferma con Whisper (`verify_with_stt: true`).
Si addestra **gratis**, senza registrare nulla, con voci sintetiche:
1. Prendi un notebook Colab di addestramento di openWakeWord (cerca "openWakeWord training colab"; ce ne sono di 2026 che girano in ~1 ora).
2. Frase: `hey aria`. Pronuncia: scrivila anche come "ciao aaria" / "ciao arìa" se la resa sintetica è strana.
3. Voci per generare gli esempi: servono voci **italiane** (Piper: `it_IT-paola-medium`, `it_IT-riccardo-x_low`; Kokoro: `if_sara`, `im_nicola`).
   Poche voci = modello meno robusto: **aggiungi tue registrazioni** (anche 40-60 clip) fatte con il vero microfono XVF3800, a 50 cm e a 2 m.
4. Esporta `hey_aria.onnx` → `software/models/` e metti `wake: {mode: model, model_path: models/hey_aria.onnx}`.
5. Tara `threshold` (0,5-0,8) tenendo la TV accesa e dicendo frasi simili ("ciao a tutti", "che aria fredda"): se scatta troppo, alza la soglia;
   se ti ignora, abbassala. Con `verify_with_stt: true` puoi tenerla bassa.

## 3. Se vuoi cambiare nome
"Aria" è una parola comune in italiano; "Hey Aria" regge, ma se i falsi positivi ti danno fastidio prova un nome meno frequente
(es. "Ciao Nova", "Ehi Luma"): basta cambiare `wake.phrase` e `name`, e riaddestrare il modello se usi `mode: model`.
