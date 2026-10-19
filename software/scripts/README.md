# Script

Strumenti per chi sviluppa Aria. Si lanciano da `software/` con l'ambiente Python di Aria (o uno con le stesse librerie).

| Script | Cosa fa |
|---|---|
| `try_persona.py` | prova carattere, strumenti e velocità del cervello senza audio |
| `dialogo_prova.py` | una conversazione intera con chatbot e voce veri ma senza microfono; può salvare l'audio in un WAV |
| `humanness.py` | quanto «umane» suonano le risposte: fa recitare conversazioni di prova al chatbot vero e conta i difetti tipici (risposte lunghe, domanda in fondo a ogni frase, formule da assistente…); `--rhythm` prova il motore del ritmo |
| `eval_intents.py`, `eval_intents2.py` | quante richieste dette «come le direbbe una persona» vengono capite; stampano i casi sbagliati |
| `sim_dialog.py` | conversazione col chatbot vero e strumenti finti (niente promemoria o eventi veri) |
| `bench_llm.py`, `bench_stt.py` | confronto tra chatbot (MLX) e tra motori di dettatura, su frasi pulite e degradate |
| `stt_real.py` | confronta i motori di dettatura sulle registrazioni salvate con `audio.save_utterances` |
| `tts_check.py` | controlla se la voce «mangia» parole: sintetizza, riconosce con Whisper e dice cosa si perde |
| `audition_voices.py` | genera la stessa frase con più voci per sceglierle all'orecchio |
| `analyze_aec.py` | analizza la cancellazione dell'eco sull'ultima risposta (richiede `audio.aec_debug: true`) |
| `app_integration_test.py`, `e2e_file_test.py` | provano il backend via WebSocket o con audio da file |
| `demo_display.py` | stati finti sul WebSocket, per provare `hardware/display/index.html` |
| `setup_mac.sh`, `setup_pi.sh` | ambiente di sviluppo su Mac e su Raspberry Pi |
| `train_wakeword.md` | come ottenere un buon riconoscimento di «Hey Aria» (tre strade) |

## Un benchmark di esempio

```bash
PYTHONPATH=. python scripts/humanness.py --persona ../anima/persona_compatta.md \
    --model mlx-community/gemma-4-e4b-it-4bit --no-think --temp 0.65 --top-p 0.92 --min-p 0.05 --rep 1.05 --rhythm --show
```

Stampa, per ogni scena, la risposta e i difetti trovati; alla fine la lunghezza media, la quota di risposte che finiscono con una domanda e i difetti per tipo. Senza `--rhythm` mostra com'era prima del motore del ritmo.
