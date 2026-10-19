# Stampa e montaggio

Tutto è generato da `hardware/cad/build.py`: i parametri in cima al file sono le quote del progetto. Per ogni pezzo il programma verifica: un solo corpo,
superficie chiusa, nessuna sovrapposizione con il disco, la sfera e gli ingombri di display, scheda mic, altoparlante, Raspberry e strip LED.
Le quote **reali** dei componenti (barra microfoni larga 20 mm assunta, flangia dell'altoparlante, collo della sfera) non sono state verificate su pezzi veri: per questo ci sono i provini.

Anteprima 3D interattiva (esploso, livelli, "fantasma" in magenta): apri `hardware/cad/preview.html` nel browser.

## 0. Prima di stampare

- **Piatto**: il corpo è Ø 210 mm → serve un piatto utile **≥ 215 mm** (Ender 3/V3, Prusa MK3/MK4, Bambu A1/P1/X1 vanno bene; A1 mini e simili **no**).
  Con un diametro minore (205, 200, 195 mm provati) il layout smette di entrare; per un piatto più piccolo il corpo andrebbe diviso in settori.
- **Materiale**: PETG (o ASA) nero opaco; diffusore in PETG naturale/bianco. Ugello 0,4, strato 0,2.
- Generazione: `python3 -m venv .venv && . .venv/bin/activate && pip install trimesh manifold3d numpy && python hardware/cad/build.py`.
- Misura con il **calibro** i componenti appena arrivano e, se differiscono, rilancia con i valori giusti, per esempio:
  ```bash
  python hardware/cad/build.py sphere_d=180 neck_id=110 mic_w=22 spk_frame_d=90 spk_cut_d=68 spk_depth=36
  ```
  Il programma rifà tutti i controlli e segnala se qualcosa non entra (`problemi` in `hardware/cad/report.json`).

| Parametro | Cosa misurare | Default |
|---|---|---|
| `sphere_d` | diametro esterno della sfera | 160 |
| `neck_id` | diametro **interno** dell'apertura | 100 (100–120 ok) |
| `neck_wall`, `neck_h` | spessore del vetro; altezza del tratto cilindrico del collo | 3 · 12 |
| `mic_w`, `mic_len`, `mic_pitch` | larghezza, lunghezza e passo mic della barra | 20 · 110 · 33 |
| `spk_frame_d`, `spk_cut_d`, `spk_depth` | Ø del telaio altoparlante, Ø del cono, profondità | 87 · 66 · 38 |
| `disp_w`, `disp_t` | lato e spessore del modulo display | 115 · 17 |

## 1. Stampa i provini PRIMA (3–4 ore in tutto)

| File | Verifica | Se non combacia |
|---|---|---|
| `T1_prova_collo_sfera.stl` (128×128×11) | la sfera si appoggia al piano e il "lip" entra nel collo senza forzare, con ~0,7 mm di gioco | cambia `neck_id` |
| `T2_prova_tasca_display.stl` (124×124×8) | il modulo display (115×115) entra nella tasca | cambia `disp_w`, `disp_clear` |
| `T3_prova_altoparlante.stl` (111×111×3) | il telaio dell'altoparlante entra nell'incavo e il cono passa dalla finestra | `spk_frame_d`, `spk_cut_d` |
| `T4_prova_fessura_disco.stl` (18×22×12) | il disco da 2 mm scorre nella fessura (2,5 mm) | `disc_slot` |
| `T5_prova_barra_microfoni.stl` (119×29×3) | la barra mic entra nella tasca; i 4 fori Ø2 cadono sopra i microfoni | `mic_w`, `mic_len`, `mic_pitch` |

## 2. I pezzi

Impostazioni comuni: PETG, strato 0,2 mm, **riempimento 20% gyroid** (le pareti sono già quasi piene: 2,4 mm = 6 perimetri), top/bottom 4 strati, nessun brim.
Pesi e tempi sono stime (volume × densità PETG; ~12 cm³/h): totale **≈ 490 g**, **35–45 ore**.

| File | Q.tà | Ingombro (mm) | Orientamento | Colore | Stima | Note |
|---|---|---|---|---|---|---|
| `01_corpo.stl` | 1 | 210×210×102 | fondo sul piatto (come nel file) | nero opaco | ~330 g · 18–22 h | Cuore con griglia altoparlante, piedini Pi, 6 colonne viti, tacca cavo e feritoie. **Niente supporti** |
| `02_anello_diffusore.stl` | 1 | 210×210×12 | piano | naturale/bianco traslucido | ~12 g · 1,5 h | Parete 1,2 mm: 3 perimetri, **0% riempimento**, 0 strati sopra/sotto (anello aperto). Prova una parete e controlla che faccia passare la luce |
| `03_piano_superiore.stl` | 1 | 210×210×56 | piano a terra | nero opaco | ~160 g · 12–15 h | Finestra Ø 90, lip, puntoni e forcelle a 45°, fori microfoni, 10 svasi. Supporti **solo se lo slicer li segnala** sulle forcelle (sono a 45°: di solito vengono senza) |
| `04_telaio_display.stl` | 1 | 180×145×17 | **già capovolto** nel file | nero opaco | ~45 g · 3–4 h | Tasca per il modulo + sede barra mic + 4 bossoli |
| `05_fermo_display.stl` | 1 | 124×124×2,5 | piano | nero | ~19 g · 1 h | |
| `06_fermo_altoparlante.stl` | 1 | 98×102×4 | piano | nero | ~7 g · 0,5 h | |

## 3. Lavorazioni

1. **Inserti a caldo M3** (punta del saldatore ~220–230 °C per PETG, premere dritti fino a filo):
   - 6 nelle colonne del **corpo** (foro Ø 4 mm in cima, profondo 9, sopra il bordo dell'anello);
   - 4 nei bossoli del **telaio** (dal lato libero).
2. Fori Ø 2,2 nei piedini del Pi: si usa la vite autofilettante M2,5.
3. **Disco semiriflettente**: pulisci il disco acrilico, applica la pellicola specchio **bagnata** con acqua e sapone, spingi via le bolle con una spatola di plastica, taglia il bordo.
   La faccia con la pellicola guarda **verso di te e verso il basso** (dove sta il display riflesso).

## 4. Montaggio (cavi PRIMA di chiudere)

1. **Altoparlante**: appoggia la flangia nell'incavo del corpo (cono verso il basso, sulla griglia), metti il **fermo** sopra e fissalo con 3 viti M3×8 **da sotto**, dado M3 incassato nell'orecchietta.
2. **Raspberry Pi 5** sui 4 piedini (viti M2,5×6) con raffreddamento montato. Strip LED incollata sulla parete interna dell'anello diffusore (LED verso l'esterno); i fili escono dalla tacca dietro.
3. **Scheda principale Flex** (35×86) sui 4 piedini frontali con biadesivo. Collega USB-C al Pi; collega l'altoparlante al connettore a 2 poli.
4. **Barra microfoni** nella tasca del telaio con i 4 microfoni sopra i fori (biadesivo sottile o kapton); cavo FPC fino alla scheda.
5. **Display** nella tasca del telaio (vetro verso l'alto, contro il piano), chiudi con il **fermo display** (4 viti M2,5×8, con un velo di nastro in schiuma tra fermo e modulo). HDMI e USB-C di alimentazione escono dalla tacca posteriore.
6. **Prova a banco con il piano aperto**: alimenta, controlla suono, microfono e display (`software/README.md`). Solo dopo chiudi.
7. Avvita il **piano** al **telaio** (4 M3×12 svasate). Appoggia anello e testa sul corpo e fissa il piano al corpo (6 M3×12): lascia i cavi con un po' di gioco.
8. **Piedini in gomma** sotto (nascondono eventuali viti). Cavo di alimentazione dalla tacca posteriore.
9. **Disco**: infilalo dall'alto-fronte nelle due forcelle e nella tacca posteriore, scorrendo verso il basso-retro fino in fondo; un punto di colla o un velo di kapton lo ferma.
10. **Sfera**: appoggiala con il collo sul "lip".

## 5. Cosa vedrai e come regolarlo

- `hardware/display/index.html?ghost=1&perf=1&size=512` è la pagina che il Raspberry apre a schermo intero. L'immagine va su sfondo nero; la linea è larga 82 mm (metà sfera).
- Se la linea appare troppo in alto o in basso: nel display c'è lo stesso effetto di una riflessione 1:1, quindi basta spostare il disegno (parametro `cy` nel codice di `hardware/display/index.html`) oppure il disco di qualche mm con `disc_cy`.
- Poco luminosa: pellicola con più riflessione (35% → 15% di trasmissione), luminosità del display al massimo, stanza meno illuminata, panno scuro dietro la sfera.
