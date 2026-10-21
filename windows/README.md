# Aria for Windows (experimental)

[Versione italiana](README.it.md)

Aria on Windows 10/11, in Italian and English (you pick in the tray icon menu): tray icon, keyboard shortcut, the same wave-of-spheres overlay and the same Python "brain" as the Mac app (the `software/` folder).

> **Honest status.** This version was written **without a Windows PC**. What has been checked, and how:
> - **The Python brain runs on Windows**: the whole test suite (over 1500 tests at the time: requests, memory, files, answer rhythm, intents…) was run with a real Windows Python 3.12 inside Wine, and passed (only the tests that use Mac programs or paths are left out). It turned up one real bug: Windows has no time-zone data, so `tzdata` is now one of the libraries.
> - **The Windows calls work** (checked the same way): the shortcut with `RegisterHotKey`, the autostart entry in the registry, a single running copy, a click-through window that does not steal focus, the parent-process check, media keys, reading the Start menu. The acrylic glass could not be tried (Wine does not have it).
> - **English on Windows** (Language menu, texts, voices, overlay, installer) has automatic tests that run on Mac and Linux (`software/tests/test_windows_en.py`: the menu logic with the real `pystray`, the language switch with the real Python program, the overlay, the messages). Those new tests were not re-run under Wine, and **the two PowerShell scripts, rewritten in two languages, have not been run or fed to PowerShell**: they only have static checks (balanced quotes and brackets, no variable names that clash when case is ignored).
> - **It has never been seen working on Windows**: the overlay (WebView2), the tray icon, the microphone and the voice, the complete installation. Expect a few defects on first launch and open an issue with the contents of `%LOCALAPPDATA%\Aria\Logs\app.log` and `backend.log`.

The Mac app (Apple silicon, with macOS 26's Liquid Glass) is a different thing and does not change: below you will find what is the same and what is not.

## What you need

- Windows 10 (1809 or later) or Windows 11, 64-bit.
- A microphone and speakers. **Headphones are better**: without macOS's echo cancellation, with speakers Aria can hear her own voice.
- ~6 GB of disk (Python environment, Whisper, voice, chatbot) and 8 GB of RAM (16 recommended).
- [Ollama](https://ollama.com) for the chatbot (the installer can install it with winget) and Microsoft's *WebView2 Runtime* for the overlay (Windows 11 already has it).
- Optional but recommended: an NVIDIA card, to run Whisper on the GPU (`-Gpu`).

## Install

From PowerShell, in the project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\install.ps1            # with the processor
powershell -ExecutionPolicy Bypass -File .\windows\install.ps1 -Gpu       # with an NVIDIA card (CUDA 12)
powershell -ExecutionPolicy Bypass -File .\windows\install.ps1 -Language en   # Aria and the installer in English (it, en or auto: like Windows)
```

The script creates a Python 3.12 environment in `%LOCALAPPDATA%\Aria`, installs the libraries, copies the program and creates `%APPDATA%\Aria\config.yaml` and `persona.md` (which you can edit). Then it adds "Aria" to the Start menu. You can run it again to update without losing your configuration. Other options: `-Model qwen3:4b` (another Ollama chatbot), `-Yes` (ask nothing), `-Language it|en|auto` (Aria's language and the installer's messages; by default it follows Windows). The same options in Italian: `-Modello`, `-Si`, `-Lingua`.

To remove it: `.\windows\uninstall.ps1`.

## Use

| What | How |
|---|---|
| Wake her | say **"Hey Aria"** or press **Ctrl + Alt + Space** (Alt + Space opens the window menu on Windows, which is why it differs from the Mac; change it with the `ARIA_HOTKEY` variable, for example `Ctrl+Shift+A`) |
| Stop her while she talks | the same shortcut, or the icon menu |
| Change language (Automatic, Italiano, English) | icon menu ▸ *Language*: it changes the text of the menu and of the overlay, what Aria understands and how she speaks, and restarts the brain (a few seconds; switching to English downloads the English voice, about 0.2 GB) |
| Change voice, mute the microphone, start with Windows | icon menu (next to the clock; if you cannot see it, it is under the ^ arrow); in English the list of voices is cut down to the ones that speak English |
| Choose the folder where she reads and writes files | menu ▸ *Aria's folder…* |
| Understand what is going on | menu ▸ *Show logs* |

## What is the same as the Mac and what is not

**The same** (it is the same code): Italian and English (language choice, recognition, voice, the `persona.en.md` personality, rules, spoken texts, overlay), personality and way of answering, memory, timers, calculations, weather, Wikipedia, web search, files and documents in your folder, understanding requests, and the wave-of-spheres overlay.

**Different, because Windows has no equivalent:**

| Mac (Apple silicon) | Windows | Why |
|---|---|---|
| Chatbot and Whisper on the Apple GPU (MLX) | chatbot in **Ollama**, Whisper with **faster-whisper** (processor, or NVIDIA) | MLX only runs on Apple chips |
| Apple's built-in speech recogniser | Whisper only | it is a macOS API |
| Microphone with echo filter (Voice Processing): you can interrupt Aria by speaking, even with speakers | stop with the shortcut; with headphones you can turn on `barge_in: true` in `config.yaml` | Windows has no equivalent echo filter |
| "Liquid Glass" | Windows acrylic (or a dark background if unavailable) | it is a macOS 26 feature |
| "Natural" voices (Qwen3-TTS, Italian only) | Pocket TTS voices | Qwen3-TTS uses MLX here |
| Settings window (Light/Medium/Heavy versions, choosing and downloading models, feature switches, wake phrase) | none: edit `config.yaml`; language and voice from the icon menu | the window is written in SwiftUI |
| Reading the screen, pointing at a button | not yet | they use macOS OCR, Accessibility and Screen Recording |
| Reminders app ("remind me tomorrow at nine to call Mark") | Aria's own reminders: a timer at that exact time that says it aloud, saved on disk so it survives a restart (not in an app, not synced to a phone; "what are my reminders" lists them) | Windows has no scriptable Reminders app |
| Calendar (adding and reading events), Shortcuts, controlling the Music app | not there (play/pause/next/previous work through the media keys) | they are Mac apps and features |
| Questions about the computer (battery, Wi-Fi name, IP, free memory and disk, system version, uptime) | there, read from Windows | |
| Opening apps and websites, volume, play/pause/next/previous | there (Start menu, media keys; precise volume needs the `pycaw` package) | |

## How it is made

```
windows/
  aria_win/        the shell: icon (pystray), overlay (pywebview + WebView2), shortcut (RegisterHotKey), backend launch, WebSocket, language (l10n.py)
  install.ps1      installation      uninstall.ps1   uninstallation      (two languages)
  config.windows.yaml   starting configuration
  assets/aria.ico  the icon
```

The backend is `software/aria` (identical to the Mac, with small variants behind `sys.platform`: `winos.py` for apps/volume/music, `power.py` for the battery, `ollama.py` and `main.py` for processes). The overlay is `app/Resources/overlay.html` + `neural.js`, the same as the Mac's. The shell starts the backend, listens to its state on the local WebSocket (`127.0.0.1:8765`) and shows or hides the overlay. The language is the same choice the brain reads (`settings.json` next to `config.yaml`, written by `python -m aria.models language set`), so the menu, the overlay and the brain always agree.

## Common problems

- **The overlay does not appear but the icon is there**: WebView2 Runtime or `pywebview` is missing; see `app.log`.
- **Aria cannot hear you**: Windows Settings ▸ Privacy & security ▸ Microphone ▸ "Let desktop apps access your microphone".
- **The menu or the overlay are in the wrong language**: icon menu ▸ *Language*; "Automatic" follows Windows' display language.
- **"Ctrl+Alt+Space" does nothing**: another program uses it; set `ARIA_HOTKEY` (a user environment variable) and reopen Aria.
- **It answers slowly**: use a smaller chatbot (`-Model gemma3:1b`) or, with an NVIDIA card, `-Gpu`.
- **Windows Defender asks to confirm `pythonw.exe`**: it is Aria's Python environment; the program is not signed.
