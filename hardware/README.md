# L'oggetto fisico

> **Stato: progetto, non costruito.** Il disegno meccanico è generato e verificato al computer (nessun pezzo si sovrappone agli altri), l'ottica è simulata e il software è quello dell'app per Mac. Le quote reali dei componenti e l'effetto ottico dal vivo non sono mai stati provati su pezzi veri.

Una sfera trasparente da scrivania. Dentro, una linea di luce stile Siri che respira, si muove con la voce e cambia colore. Dici «Hey Aria» e ci parli; se ti serve un'informazione, la cerca. Tutto gira in locale, senza abbonamenti.

```
         ╭─────────────╮
       ╱                 ╲      sfera Ø 16 cm (apertura 10-12 cm)
      │   ━━━ la linea ━━━ │     = riflesso nel disco, sospeso nel vuoto
      │      ╱ disco 45°   │     (specchio semiriflettente Ø 11 cm)
       ╲   ╱_____________╱
   ┌────┴─────────────────────┐
   │ display Ø 8,8 cm ↑       │  nascosto, guarda in su
   │ barra mic · strip LED    │  l'anello luminoso fa da "alone" colorato
   │ Raspberry Pi 5 · altopar.│  corpo Ø 21 cm stampato in PETG nero
   └──────────────────────────┘
```

## Come si vede la linea

Ottica «fantasma» (Pepper's ghost): lo schermo, nascosto sotto, viene riflesso da un disco semiriflettente a 45° dentro la sfera. Dove il pixel è nero non si vede nulla: resta solo la linea, sospesa a 4,6 cm sopra il piano, e la sfera rimane trasparente. Lo schermo è invisibile da qualunque angolo sotto i 40°.

Il simulatore a raggi in `prototipo/orb.html` confronta tre soluzioni:

| Soluzione | Esito |
|---|---|
| **A · Fantasma** (scelta) | solo la linea, nel vuoto, sfera trasparente; si vede da davanti (~±40°) |
| B · Sfera di cristallo piena davanti allo schermo | bellissima ma con un punto di vista di ±3–5°: inutilizzabile |
| C · Schermo dentro una sfera cava | robusta, ma si vede *uno schermo* in una bolla |

Limiti: con un display da 300 nit e uno specchio al 40–50% il fantasma sta sui 120–150 nit, ottimo in casa e debole al sole; ha come sfondo ciò che c'è dietro la sfera (contro un muro chiaro perde contrasto: aiuta una semisfera fumé o un panno scuro); si vede solo da davanti.

## Componenti principali

- **Raspberry Pi 5** (8 GB), con il software di `../software` (il «cervello» pesante gira su un altro computer di casa: vedi `bom.md`).
- **Microfoni**: ReSpeaker Flex XVF3800 *Linear* (barra da 110 mm sul bordo frontale + scheda). Cancellazione d'eco, beamforming e riduzione del rumore in hardware: senza, Aria non ti sentirebbe mentre parla e non potresti interromperla.
- **Display**: Waveshare 3,4" tondo HDMI 800×800 (il 2,8" tondo funziona solo con software proprietario su Windows).
- **Alone**: strip LED WS2812B nell'anello diffusore, in sincrono con la linea.
- **Grafica**: la stessa nuvola di neuroni dell'app Mac (`../app/Resources/neural.js`) gira sul display su sfondo nero.

## Cosa c'è in questa cartella

| | |
|---|---|
| [`bom.md`](bom.md) | cosa comprare, quanto costa, in che ordine (due fasi: ottica e stampa, poi elettronica) |
| [`stampa.md`](stampa.md) | impostazioni di stampa, provini, montaggio |
| `cad/` | generatore parametrico dei pezzi 3D (`build.py`, Python + trimesh), 11 STL pronti in `cad/stl/`, anteprima 3D interattiva `cad/preview.html` |
| `display/index.html` | la pagina che il Raspberry apre a schermo intero sul display (si collega al WebSocket di Aria) |
| `prototipo/orb.html` | simulatore ottico dell'effetto «fantasma» e pagina per provarlo con un telefono (ricordati di abbassare la luminosità del telefono al 30%: i telefoni fanno 800+ nit e il test sarebbe ottimistico) |

Il software per il Raspberry (servizi `systemd`, `config.example.yaml`, wake word con openWakeWord) è in [`../software`](../software/README.md) e [`../software/scripts/train_wakeword.md`](../software/scripts/train_wakeword.md).
