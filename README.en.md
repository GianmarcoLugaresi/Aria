# Aria

A voice assistant for your desk, in Italian, that runs entirely on your own computer: no subscriptions, no accounts, no audio sent to anyone.

Say "Hey Aria" (or press ⌥ Space), talk to it like a person and it answers out loud. It can chat, tell the time and the weather, do maths and timers, search the web, remember things about you, read and write files in a folder you choose and, if you allow it, open apps, play music, create reminders and events, or look at your screen.

[Versione italiana](README.md)

> The assistant speaks and understands **Italian only**. The code and the documentation are in Italian too.

## How it works

```
microphone ─► "Hey Aria" ─► voice detection ─► speech recognition (Whisper) ─► local chatbot ─► voice (Pocket TTS) ─► speakers
                                                          │                        ▲
                                                          └─► tools: time, weather, timers, maths, search, files, apps…
```

- The chatbot is a small model (Gemma 3 4B) running on your Mac with Apple MLX; speech recognition is Whisper (or macOS' built-in recognizer if you pick it); the voice is Pocket TTS. Models are downloaded on first run (about 3.5 GB) and managed from the Settings window.
- Small models make mistakes, so Aria steers them: obvious requests (time, weather, timers, maths) are recognised by the program rather than the model; replies are kept short and free of assistant boilerplate; every power over the computer starts only from something *you* said, never from text the model wrote.
- After each answer it keeps listening for a few seconds, so you can carry on without calling it again, and you can interrupt it.

See [docs/come-funziona.md](docs/come-funziona.md) (Italian).

## Requirements

- A Mac with Apple silicon (M1 or later), 16 GB of RAM recommended.
- macOS 26 or later: the app uses the Liquid Glass material and macOS 26's built-in speech recognition. It will not open on earlier versions.
- About 7 GB of free disk space (the app is 1.6 GB unpacked, the models another 3.5 GB).
- The Xcode command line tools (`xcode-select --install`) **only if you build it yourself** from source.

There is an **experimental Windows port** in [windows/](windows/). Linux and Intel Macs are not supported by the app, but the Python "brain" can be used from a terminal.

## Install

### Download the app (easiest)

1. From the [Releases](https://github.com/GianmarcoLugaresi/Aria/releases) page download `Aria-0.3.1-macos-arm64.zip` (about 0.5 GB) and unzip it: `Aria.app` already contains Python and every library.
2. Drag `Aria.app` into **Applications**.
3. The app is not signed with a paid Apple certificate (it is not notarized), so macOS refuses to open it the first time. Once, from Terminal:

   ```bash
   xattr -dr com.apple.quarantine /Applications/Aria.app
   ```

   (or try to open it, then System Settings ▸ Privacy & Security ▸ **Open Anyway**).
4. Open it. The first launch downloads the models (about 3.5 GB; the menu shows "Primo avvio: sto scaricando i modelli…") and macOS asks for microphone permission. When the menu says it is ready, say "Hey Aria" (the assistant speaks Italian).

### Build it yourself from source

```bash
git clone https://github.com/GianmarcoLugaresi/Aria.git
cd Aria
./app/install.sh
open ~/Applications/Aria.app
```

The script creates a native Python 3.12 environment in `~/Library/Application Support/Aria`, installs the libraries, builds the app, writes the configuration (`config.yaml`) and the character (`persona.md`) and downloads the models. Running it again updates without touching your configuration. To remove everything: `./app/uninstall.sh`.

## Privacy

Audio, transcripts, memory and models stay on your computer. Network access is only used for: model downloads (Hugging Face, first run), the weather (Open-Meteo: the city name), Wikipedia and web search when you ask for things that change over time (the text of the question), and the pages it reads to write a factual document. Powers over your Mac (reminders, calendar, music, apps, Shortcuts, screen) can be switched on and off one by one in Settings; the ones that look at the screen are off by default. Details: [docs/privacy.md](docs/privacy.md).

## The physical object

The project started as a transparent desk sphere with a line of light inside (display, half-silvered mirror, Raspberry Pi 5, echo-cancelling microphones). The mechanical design, bill of materials, printable files and an optical simulator are in [hardware/](hardware/). **It has not been built**: the Mac app is the working part of the project.

## Development

```bash
cd software
python -m pip install -e ".[test]"
python -m pytest -q          # 1500+ tests, no audio and no real models needed
```

## Known limits

- Developed and tested on a single Mac (M2 Pro, 16 GB, macOS 26). Other setups may surprise you.
- A 4-billion-parameter chatbot is small: it occasionally writes a strange sentence, and the documents it produces should be proof-read.
- With the Mac's speakers the microphone also hears Aria; voice interruption relies on macOS' echo filter and works best with headphones.
- Wake-word detection can misfire in noisy rooms. ⌥ Space may already be taken by another app.

## License

The code is released under the [MIT license](LICENSE). Downloaded models have their own licenses (Gemma has its own terms of use, Pocket TTS is CC-BY-4.0, Qwen3-TTS is Apache-2.0): see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
