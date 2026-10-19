# Componenti di terze parti

Aria non include i modelli: li scarica al primo avvio da Hugging Face. Ogni modello ha le sue condizioni, che vanno lette prima di usare Aria per scopi diversi dall'uso personale.

## Modelli

| Modello | Uso | Licenza |
|---|---|---|
| `mlx-community/gemma-3-text-4b-it-4bit` (da Gemma 3 di Google) | chatbot di fabbrica | **Gemma Terms of Use** (non è una licenza open source standard: vedi <https://ai.google.dev/gemma/terms>) |
| `mlx-community/gemma-4-e4b-it-4bit`, `gemma-2-9b-it-4bit` e altri Gemma | chatbot a scelta nelle Impostazioni | Gemma Terms of Use |
| `mlx-community/whisper-large-v3-turbo-q4` (da OpenAI Whisper) | riconoscimento vocale di fabbrica | pesi di Whisper rilasciati con licenza MIT (la scheda di questa conversione non dichiara una licenza: controlla quella del modello originale) |
| `kyutai/pocket-tts` | voce di fabbrica (Pocket TTS) | codice MIT, **pesi CC-BY-4.0**: serve citare Kyutai |
| `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit`, `…-1.7B-VoiceDesign-4bit` | «voce naturale» facoltativa | Apache-2.0 |
| Silero VAD (inclusa nei pacchetti `pysilero-vad` e `faster-whisper`) | rilevamento della voce | MIT |

I file in `software/aria/voices/` sono voci di riferimento sintetiche usate dalla «voce naturale» (prodotte con modelli di sintesi vocale come quelli elencati sopra).

## Librerie Python

Le versioni sono quelle installate da `app/install.sh`; le licenze vengono dai metadati dei pacchetti.

| Pacchetto | Licenza |
|---|---|
| numpy | BSD-3-Clause (con parti MIT, Zlib, CC0) |
| httpx | BSD-3-Clause |
| pyyaml | MIT |
| websockets | BSD-3-Clause |
| sounddevice | MIT |
| faster-whisper | MIT |
| mlx, mlx-lm, mlx-vlm, mlx-whisper, mlx-audio | MIT |
| pysilero-vad | MIT |
| pocket-tts | MIT |
| ddgs | MIT |
| pypdf | BSD-3-Clause |
| pillow | MIT-CMU |
| onnxruntime | MIT |
| miniaudio | MIT |
| huggingface-hub | Apache-2.0 |
| transformers | Apache-2.0 |
| tzdata (solo Windows) | Apache-2.0 |
| pystray, pywebview (solo Windows) | LGPL-3.0, BSD-3-Clause: controllare le versioni installate |

## L'app scaricabile (Release)

`Aria.app` scaricata dalle Release contiene, oltre alle librerie qui sopra, un interprete Python 3.12 (licenza PSF-2.0, distribuzione `python-build-standalone`) e le dipendenze indirette elencate con la versione in `app/release-requirements.txt`. Le principali: PyTorch (BSD-3-Clause e altre licenze permissive, usato dalla voce Pocket TTS), SciPy (BSD-3-Clause), numba e llvmlite (BSD-2-Clause; Apache-2.0 con eccezione LLVM), sympy e mpmath (BSD), tokenizers e transformers (Apache-2.0), lxml (BSD-3-Clause), PyAV (BSD-3-Clause, con le librerie FFmpeg incluse nella sua ruota: le loro condizioni sono nella cartella del pacchetto), certifi e tqdm (MPL-2.0). Il testo di ogni licenza è nella cartella `<pacchetto>.dist-info` dentro `Aria.app/Contents/Resources/backend/lib/python3.12/site-packages`.

## Servizi usati in rete

Open-Meteo (meteo e geocodifica), Wikipedia, DuckDuckGo e altri motori tramite `ddgs`, Hugging Face (download dei modelli). Ognuno ha le proprie condizioni d'uso.
