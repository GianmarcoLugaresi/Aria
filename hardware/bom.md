# Componenti e costi

Prezzi **indicativi, in euro con IVA**, calcolati da listini 2026 trovati online; ricontrollali all'ordine (RAM e Raspberry oscillano molto quest'anno).
Dove un componente arriva dalla Cina (Seeed, Waveshare) aggiungi spedizione (~10–15 €) e l'IVA al checkout.

## Come ordinare: due fasi

La parte rischiosa è l'**ottica**, non l'elettronica. Quindi:

### Fase 1 · ottica e stampa (~70–90 €): da ordinare per prima
Serve a confermare che la linea galleggia come previsto **prima** di spendere ~500 € di elettronica, e a misurare la sfera.

| # | Pezzo | Qtà | Prezzo | Cosa controllare |
|---|---|---|---|---|
| 1 | **Sfera/globo trasparente**, Ø 150–200 mm, **con apertura (collo) da 100 a 120 mm di diametro INTERNO** | 1 (meglio 2 misure) | 15–40 € | Cerca "globo vetro trasparente per lampadario Ø 160 attacco 100". Vetro o acrilico, **non satinato**. Chiedi/misura il diametro **dell'apertura**, non solo quello della sfera. Pesa: vetro ≈ 1 kg, acrilico ≈ 0,4 kg. |
| 2 | **Disco acrilico trasparente Ø 110 mm, spessore 2 mm** | 2 | 8–15 € | Acrilico colato/estruso, taglio laser (molti negozi online "dischi plexiglass su misura"). Senza pellicola protettiva |
| 3 | **Pellicola specchio unidirezionale** ("one way mirror", pellicola per vetri argento) | 2 gradazioni (es. 15% e 35% di trasmissione) | 10–20 € | La riflessione che vuoi è ~40–50%: prendine due diverse e confronta. Si applica bagnata sul disco |
| 4 | **PETG nero opaco** 1 kg + **PETG naturale o bianco** ~250 g (diffusore) | 1 + 1 | 30–35 € | PETG o ASA (resiste al calore dell'elettronica). Il PLA si deforma sopra ~55 °C |
| 5 | Kit inserti M3 a caldo (M3×5,7) + viti assortite M2,5/M3 | 1 | 10–14 € | Inserti ×12 (10 + scorta); viti: vedi elenco sotto |

**Come usarla:** stampa i provini `T1–T5` (3–4 h in tutto, [stampa.md](stampa.md)), prova il test col telefono (`prototipo/orb.html`),
poi, se tutto torna, la fase 2.

### Fase 2 · elettronica (~430–550 €): quando il test dell'ottica convince

| # | Pezzo | Qtà | Listino | Stima € | Note e dove |
|---|---|---|---|---|---|
| 6 | **Raspberry Pi 5, 8 GB** | 1 | ~175 $ | 190–215 | Il 4 GB (~110 $, ~150 €) basta *se* userai sempre un cervello esterno. Con 8 GB puoi tenere i modelli piccoli sul Pi. Rivenditori: [elenco ufficiale](https://www.raspberrypi.com/resellers/) (in Italia: Melopero), Kiwi Electronics, The Pi Hut |
| 7 | Raffreddamento attivo ufficiale Pi 5 | 1 | — | 6 | |
| 8 | Alimentatore ufficiale 27 W USB-C | 1 | — | 15 | **non** un caricatore generico: il Pi 5 vuole 5 V/5 A |
| 9 | microSD 128 GB A2 (o SSD NVMe + HAT) | 1 | — | 15 | |
| 10 | **Waveshare 3,4" HDMI Round Touch Display 800×800** | 1 | 83,99 $ | 95–110 | [pagina prodotto](https://www.waveshare.com/3.4inch-800x800-lcd.htm). Modulo 115×115×17 mm, 300 nit, 1,5 W, alimentato da USB-C 5 V. **Non** il 2,8" (solo Windows) |
| 11 | Cavo HDMI corto (verifica il tipo di connettore: mini/micro/standard) | 1 | — | 8 | Il Pi 5 ha micro-HDMI |
| 12 | **reSpeaker Flex XVF3800 Linear-4 (USB, SENZA XIAO ESP32S3)** | 1 | 57,99 $ | 70–85 | [Seeed](https://www.seeedstudio.com/reSpeaker-Flex-XVF3800-Linear-4-p-6738.html). **Attenzione**: la versione "with XIAO ESP32S3" ha firmware I2S, non va bene. Barra mic 110 mm (4 mic, passo 33 mm) + scheda 35×86 mm + cavo FPC 20 cm; amplificatore 10 W integrato |
| 13 | **Altoparlante full-range 3" (≈ 8 cm), 8 Ω, 5–10 W** | 1 | — | 15–30 | Telaio ≤ Ø 92 mm, profondità ≤ 40 mm, cono ≤ Ø 66 mm (la griglia è Ø 66; si cambia in `build.py`). Cerca "altoparlante fullrange 3 pollici 8 ohm" |
| 14 | **Strip LED WS2812B**, 5 V, 60 LED/m, larghezza 10 mm, IP20 (senza silicone) | 1 m | — | 7 | Servono 38 LED (~65 cm) |
| 15 | Convertitore di livello 3,3→5 V (74AHCT125) | 1 | — | 2–4 | Per il dato della strip dal Raspberry |
| 16 | Cavi corti: USB-C→USB-A (Flex → Pi), USB-A→USB-C (alimentazione display), jumper dupont | 1 kit | — | 12–15 | |
| 17 | Minuteria: piedini gomma adesivi Ø15×6 mm ×4, nastro biadesivo schiuma, kapton, fascette, colla a caldo | 1 | — | 8–10 | |
| **Subtotale fase 2** | | | | **≈ 445–560 €** | |

**Totale corpo (fase 1 + 2): ≈ 520–640 €.**

### Viti e inserti (nel kit n. 5)
| Quantità | Cosa | Dove |
|---|---|---|
| 10 | inserti M3 (Ø foro 4,2 mm) | 6 colonne del corpo + 4 bossoli del telaio |
| 10 | viti M3×12 a testa svasata | piano → corpo (6), piano → telaio (4) |
| 3 + 3 | viti M3×8 + dadi M3 | fermo altoparlante (viti dal basso) |
| 4 | viti autofilettanti M2,5×8 | fermo display |
| 4 | viti M2,5×6 | Raspberry sui piedini (4 fori, passo 58×49) |

## Consumi
Pi 5 + display + microfoni + LED ≈ **7–10 W in attesa** → ~6 kWh/mese → **~2 €/mese**.

## Il «cervello»

Un modello da 2B scrive un italiano inutilizzabile, e il 4B che funziona bene (Gemma 3 4B, ~6 GB di RAM in tutto con riconoscimento e voce) non gira decentemente su un Raspberry Pi 5. Per chiacchierare davvero l'oggetto ha quindi bisogno di un **cervello esterno** (vedi `software/aria/router.py`: ogni stadio ha una lista di posti dove può girare, vince il primo raggiungibile). Il Raspberry resta comunque utile da solo per le cose semplici (ora, timer, meteo, calcoli).

| Opzione | Costo | Pro | Contro |
|---|---|---|---|
| Un Mac con chip Apple già in casa | 0 € | prima frase in 1,4–2,5 s (misurata su un M2 Pro 16 GB) | deve essere acceso |
| Mac mini M4 16/512 dedicato | circa 979 € | sempre acceso, silenzioso, 4–5 W a riposo | costo |
| Jetson Orin Nano Super 8 GB | 519–567 € in Europa | piccolo, 25 W | 8 GB stretti; il Pi 5 non lo richiede |
| Raspberry Pi 5 16 GB | circa 205 $ | nessun altro apparecchio | gli stessi 6–7 token/s dell'8 GB: non migliora la velocità |
| Mini PC Ryzen 32 GB | 520–1100 $ | veloce con modelli MoE | prezzi della RAM nel 2026; Linux/Windows da gestire |

Prima di acquistare hardware dedicato conviene provare l'app per Mac e vedere se voce, tempi e carattere bastano.

## Cosa NON serve
Abbonamenti, chiavi API, account cloud, un secondo Raspberry, un amplificatore a parte (il Flex ha il suo da 10 W), un DAC.
