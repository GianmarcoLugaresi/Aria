# Aria

A voice assistant for macOS that runs entirely on your Mac and speaks Italian and English (you pick in Settings). Wake word, speech recognition, a small language model and speech synthesis all run on Apple silicon; no account, no cloud, no audio sent anywhere.

[![Release](https://img.shields.io/github/v/release/GianmarcoLugaresi/Aria?display_name=tag)](https://github.com/GianmarcoLugaresi/Aria/releases)
[![License: MIT](https://img.shields.io/github/license/GianmarcoLugaresi/Aria)](LICENSE)
![macOS 26+](https://img.shields.io/badge/macOS-26%2B-black)
![Apple silicon](https://img.shields.io/badge/Apple%20silicon-MLX-blue)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB)
![Swift](https://img.shields.io/badge/Swift-app%20%2B%20helpers-F05138)
![Tests](https://img.shields.io/badge/tests-1800%2B-brightgreen)

<p align="center"><img src="docs/demo.gif" alt="Aria answering 'what time is it in Tokyo?': the overlay listens, thinks and shows the spoken answer word by word" width="520"></p>
<p align="center"><sub>Generated from the real backend with a recorded phrase instead of a microphone: not a screen recording, so it has no macOS glass and does not show barge-in.</sub></p>

[Versione italiana](README.it.md)

## Why

Local voice assistants are easy to demo and hard to live with. A 4-billion-parameter model on a laptop is fast enough to talk to, but it makes things up, drifts off instructions and cannot be trusted with a tool-calling interface. Aria is built around that instead of waiting for a bigger model:

- **Rules first, model second.** Obvious requests (time, weather, timers, arithmetic, reminders, "remember that…") are recognised by rules in [`intent.py`](software/aria/intent.py) before the model sees the sentence, and the tool runs immediately. `"what's fifteen times eighteen"` (or `"quanto fa quindici per diciotto"`) becomes `CALCOLA(15*18)` without a single token generated.
- **The model cannot act on your computer.** Reminders, calendar, music, apps, Shortcuts and screen features start only from a request recognised in *your* sentence. If the model writes a tool call for one of them it is refused and logged. Every power has its own switch in Settings.
- **The output is cleaned before it is spoken.** No "Certainly!", no invented personal experiences, no markdown, no foreign-language filler; [`speech.py`](software/aria/speech.py) and [`speech_en.py`](software/aria/speech_en.py) rewrite what is *read* into what is *said* ("18°C" becomes "eighteen degrees Celsius", or "diciotto gradi" in Italian).
- **Two languages, one switch.** Italian came first and is the better tested; English has its own twin of every language-dependent module (`intent_en.py`, `timeparse_en.py`, `dialog_en.py`…), its own persona prompt and an English voice. Settings ▸ Language changes the app's text, what Aria understands and how she speaks, and restarts her. The wake phrase tolerates mispronunciations ("ehi aria", "hey area").

## Quickstart

Requires an Apple silicon Mac with macOS 26 or later (16 GB RAM recommended) and about 7 GB of free disk space.

**Download the app** (no toolchain needed):

1. Download `Aria-1.0.1-macos-arm64.zip` from [Releases](https://github.com/GianmarcoLugaresi/Aria/releases), unzip it and move `Aria.app` to `/Applications`.
2. The app is not notarized, so macOS blocks it the first time. Once:

   ```bash
   xattr -dr com.apple.quarantine /Applications/Aria.app
   ```

3. Open it. The first launch downloads the models (about 3.5 GB) and asks for microphone access. When the menu bar icon says it is ready, say **"Hey Aria"** or press **⌥ Space**. Aria starts in your Mac's language (Italian if the Mac is in Italian, English otherwise); change it any time in **Settings ▸ Language**.

**Or build it from source** (needs the Xcode command line tools):

```bash
git clone https://github.com/GianmarcoLugaresi/Aria.git
cd Aria
./app/install.sh
open ~/Applications/Aria.app
```

**Run the Python side on its own** (no audio, no microphone):

```bash
cd software
python -m pip install -e ".[test]"
python -m pytest -q                                          # 1800+ tests, no audio or real models needed
python -m aria.main --config config.example.yaml --text      # text chat; needs a reachable chatbot, see the config
```

Details, permissions and uninstall: [docs/installazione.md](docs/installazione.md) (Italian).

## Key features

- **Wake word without training a model.** A light voice-activity detector (Silero, single thread) listens; when it hears speech, Whisper transcribes it and looks for "hey aria". `Hey Aria, what's the weather tomorrow?` in one breath works. Global hotkey: ⌥ Space.
- **Barge-in with the speakers on.** The mic goes through macOS Voice Processing ([`aria_vpmic.swift`](software/helpers/aria_vpmic.swift)); while Aria talks, the last second and a half of audio is transcribed and compared with the words Aria is saying: those are echo and are ignored, "stop" or "wait" ("basta", "aspetta" in Italian) stops it ([`bargein.py`](software/aria/bargein.py)).
- **Everyday tools.** Time and date (also in other cities), weather (Open-Meteo), timers, arithmetic and unit conversion, Wikipedia, web search (`ddgs` or your own SearXNG). Memory of facts about you in a local SQLite file.
- **Files in one folder only.** It writes `.md` and `.txt` and reads text, CSV, PDF and Word, inside a single folder you choose. No hidden files, no deletion, no overwrite, 120 KB per file ([`workspace.py`](software/aria/workspace.py)).
- **Mac powers, one switch each.** Reminders, Calendar, Music and volume, open apps and sites, Shortcuts (with a confirmation step). Screen reading (Vision OCR, or a vision model) and pointing at a button (Accessibility plus a click-through overlay) exist but screen reading is off by default.
- **Italian and English.** Pick the language in Settings; the speech recogniser (Whisper, or the macOS recogniser with the matching locale), the voice (Pocket TTS, English weights downloaded the first time, about 0.2 GB), the persona, the date and number parsing and every spoken answer follow it. Imperial units when the Mac (or the Windows region) uses them.
- **Settings window.** Light, Medium and Heavy profiles, model manager (download and remove models), Ollama or any OpenAI-compatible server as an alternative to the built-in MLX chatbot.
- **Built for being left on.** Single-thread idle VAD, microphone closed when the display is asleep on battery (`audio.sleep_on_battery`), watchdog with backoff for the audio device.
- **Optional natural voice** (Qwen3-TTS on MLX), 25 Pocket TTS voices otherwise, system `say` as a no-download fallback.
- **Windows port (experimental).** Tray icon, hotkey, same Python backend with Ollama and faster-whisper, in Italian and English like the Mac app (Language in the tray menu, bilingual installer). It has never been run on a real Windows machine, see [windows/README.md](windows/README.md).

## How it works

```
mic ─► VAD ─► Whisper ("hey aria") ─► VAD ends turn ─► intent rules ──► tool ─┐
                                                          │ no match          │
                                                          ▼                   ▼
                                       Gemma 3 4B (MLX) + per-turn style hints ─► cleanup ─► Pocket TTS ─► speaker
```

The chatbot is `mlx-community/gemma-3-text-4b-it-4bit`, recognition is `whisper-large-v3-turbo-q4` on MLX (or the macOS 26 built-in speech recogniser), the voice is Pocket TTS. Per-turn style hints ([`style.py`](software/aria/style.py), [`rhythm.py`](software/aria/rhythm.py)) pick a move (an opinion, a layered explanation, a question about one detail), a word budget, and never two questions in a row. The model does not use function calling: when it needs data it writes a line such as `[[METEO: Roma domani]]`, which Aria runs and feeds back. More in [docs/come-funziona.md](docs/come-funziona.md).

## Limitations

- **English is newer than Italian.** The English rules cover the core tools (time, date, weather, timers, arithmetic, reminders, calendar, music and volume, apps, lists, notes, files, screen); anything else goes to the model. It was checked with unit tests and a round trip through real Whisper with the macOS system voice (9 of 9 phrases), not with many real speakers or accents. The natural voice (Qwen3-TTS) is Italian only, translations into other languages are read with the English voice, and the Raspberry Pi / Piper configs under `software/` still ship an Italian voice (the language switch is for the Mac app and the Windows build, which use Pocket TTS).
- **Apple silicon and macOS 26+.** The app uses Liquid Glass and the macOS 26 speech recogniser; MLX does not run elsewhere.
- **Tested on one Mac** (M2 Pro, 16 GB). Other setups may surprise you.
- **A 4B model is small.** It still says odd things now and then; text it writes for you needs rereading. A larger model in Settings answers better and uses much more memory.
- **The intent rules are regular expressions.** They score 195/195 on `tests/intent_corpus.py` and 190/194 on `tests/intent_corpus2.py` (`python scripts/eval_intents2.py`), but those sets were written by the author, so expect lower numbers on real speech.
- **Not notarized.** You have to remove the quarantine flag by hand (see Quickstart). Every new download is a "new app" to macOS and optional permissions (screen, Accessibility) must be granted again.
- Wake-phrase recognition can fail in a noisy room. With speakers, interruption by voice works better with headphones.

## Contributing

Issues and pull requests are welcome, in English or Italian. Start from the issues labelled [good first issue](https://github.com/GianmarcoLugaresi/Aria/labels/good%20first%20issue).

Ground rules:

- The model must never be able to trigger an action. A new power needs a recogniser in `intent.py`, a switch in Settings and a test where the model tries to call it by itself.
- New phrasings go into `software/tests/intent_corpus*.py`; `python scripts/eval_intents2.py` prints what is still misunderstood. See [docs/sviluppo.md](docs/sviluppo.md) (Italian).
- User-facing strings exist in both languages (`i18n.pick(italian, english)`, or the `_en` twin module); new Italian phrasings go to `intent_corpus*.py`, new English ones to `tests/test_intent_en.py`. Code comments and test names are in Italian, identifiers in English.

## License

Code: [MIT](LICENSE). Downloaded models keep their own licenses (Gemma has its own terms of use); see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
