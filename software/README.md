# aria (pacchetto Python)

Il «cervello» di Aria: conversazione, intenzioni, strumenti, memoria. Lo usano sia l'app per Mac (`../app`) sia la versione per Windows (`../windows`); può girare anche da solo, da terminale.

La documentazione è nella cartella [`../docs`](../docs): [come funziona](../docs/come-funziona.md), [configurazione](../docs/configurazione.md), [sviluppo e test](../docs/sviluppo.md).

```bash
python -m pip install -e ".[test]"
python -m pytest -q                                   # oltre 1500 prove, senza audio né modelli veri
python -m aria.main --config config.example.yaml --text    # chat testuale (serve un chatbot raggiungibile, vedi config)
python -m aria.main --help
```

| Cartella | Cosa c'è |
|---|---|
| `aria/` | il pacchetto (un modulo per argomento: vedi la mappa in `docs/come-funziona.md`) |
| `tests/` | le prove: richieste capite, conversazione con componenti finti, strumenti, file, ritmo delle risposte… |
| `scripts/` | strumenti per chi sviluppa: [indice](scripts/README.md) |
| `helpers/` | programmi di supporto in Swift per macOS (riconoscimento vocale, microfono con filtro eco, OCR, Accessibilità, riquadro che indica) |
| `systemd/` | servizi per l'oggetto fisico su Raspberry Pi |
| `config.example.yaml`, `config.mac.yaml` | configurazioni d'esempio per Raspberry e per provare tutto sul Mac con Ollama |
