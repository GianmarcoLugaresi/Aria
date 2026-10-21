"""I testi in INGLESE delle Impostazioni di Aria (versioni, modelli, funzioni, messaggi di stato e di errore).

L'italiano vive dov'e' sempre stato (profiles.py e models.py); qui c'e' il corrispondente inglese, scelto quando la lingua di Aria e' l'inglese (vedi i18n.py).
Chi manca qui ricade sull'italiano: meglio una scritta nella lingua sbagliata che un buco.
"""
from __future__ import annotations

# ---- riconoscimento vocale (chiave: repo)
STT_NOTES = {
    "apple:speech": "The Mac's own: downloads nothing and doesn't use Aria's RAM, 0.1 s per sentence. On real recordings it comes close to Whisper large-v3 (it gets different sentences wrong).",
    "mlx-community/whisper-tiny-mlx": "The smallest: for testing only, it usually gets a lot wrong.",
    "mlx-community/whisper-base-mlx": "Very fast, but with noise it gets about half the words wrong.",
    "mlx-community/whisper-small-mlx-q4": "The one in the Light version.",
    "mlx-community/whisper-large-v3-turbo-q4": "The one in the Medium version: the best balance of accuracy and size among those measured.",
    "mlx-community/whisper-small-mlx": "Like small at 4 bit, uncompressed: a little more accurate, heavier.",
    "mlx-community/whisper-medium-mlx": "In between, but heavier and slower than the turbo without being better: not worth it.",
    "mlx-community/whisper-large-v3-turbo": "The turbo without 4-bit compression: in theory slightly more accurate, 3 times heavier.",
    "mlx-community/whisper-large-v3-mlx": "The one in the Heavy version. Measured: NOT more accurate than the 4-bit turbo (1 / 2 / 8 % in the same test) and it is slower and 6 times heavier.",
}
STT_LABELS = {"apple:speech": "Apple (built into the Mac)"}

# ---- chatbot (chiave: ref)
LLM_NOTES = {
    "mlx:mlx-community/gemma-3-1b-it-4bit": "Tiny and very fast, but a model this small writes poorly and loses the thread: for testing only.",
    "mlx:mlx-community/gemma-3-text-4b-it-4bit": "Aria's default (Light and Medium versions): the smallest one that holds a good conversation.",
    "mlx:mlx-community/gemma-4-e4b-it-4bit": "Tested at length: faster (50 words per second against 30), lighter than Gemma 2 9B and better at understanding commands; it converses a little better. Downloads 5.2 GB.",
    "mlx:mlx-community/gemma-2-9b-it-4bit": "The one in the Heavy version: writes better, but it is slower and takes twice the space.",
    "mlx:mlx-community/gemma-3-text-12b-it-4bit": "Very heavy: with 16 GB of RAM you have to close everything else.",
}

# ---- versioni (chiave: id)
PROFILES = {
    "leggera": ("Light", "Lighter speech recognition, 3 times faster, but less accurate: it gets more words wrong, especially with noise or low volume."),
    "media": ("Medium", "Aria's current setup: a good balance of accuracy, speed and memory."),
    "pesante": ("Heavy", "A bigger chatbot that writes better, and Whisper large-v3 (same accuracy as the Medium's turbo, but slower). Uses about 10 GB of memory: close other apps."),
}

# ---- funzioni (chiave: id) -> (nome, cosa fa)
POWERS = {
    "shortcuts": ("macOS Shortcuts", "Runs your Shortcuts by voice, always asking for confirmation first."),
    "reminders": ("Reminders", "Creates reminders in the Reminders app and reads them back to you."),
    "calendar": ("Calendar", "Adds events to Calendar and tells you what is on your agenda."),
    "music": ("Music and volume", "Controls Music (or Spotify) and the Mac's volume."),
    "apps": ("Apps and websites", "Opens installed apps, websites and searches (YouTube, Google, Maps…)."),
    "documents": ("Documents", "Reads and answers questions about the PDFs and Word documents in Aria's folder."),
    "briefing": ("Morning briefing", "Weather, appointments, reminders and news in one go."),
    "screen_mac": ("Looking at the screen: the Mac's OCR",
                   "Reads the text you have on screen and tells you where it is (\"where is the Export button?\", \"summarise this page\"). It uses macOS text recognition: "
                   "0.3 seconds, no extra memory, works with any chatbot. It doesn't understand images or icons without a label. Switched off if you turn the other one on."),
    "screen_model": ("Looking at the screen: a model that can see",
                     "A model with built-in vision looks at the screen: it also understands icons, images and how the page is laid out, and can give you an opinion. It takes a few seconds and uses "
                     "about 4 GB more memory while it answers. Switched off if you turn the other one on."),
    "screen_point": ("Pointing at things on the screen",
                     "When it tells you where a button or a label is (with the Mac's OCR), it highlights it with a glowing frame that pulses for a few seconds. It doesn't block clicks: you keep working."),
    "screen_ax": ("Finding buttons and icons precisely (Accessibility)",
                  "For \"where is the X button?\" it uses macOS Accessibility: it reads the buttons, the icons without a label and the menus of the app in front of you and tells you exactly where it is, even without looking at the screen. "
                  "It needs the \"Accessibility\" permission for Aria (macOS asks for it)."),
    "voice_natural": ("More natural voice (Qwen3-TTS)",
                      "A more human voice. For now it speaks Italian only: in English, Aria always uses the standard voice."),
    "battery_rest": ("Rest on battery",
                     "When the Mac runs on battery and the screen has been off for a minute, Aria stops listening and the Mac can go to sleep: with the microphone open it never would on its own. "
                     "It resumes as soon as you turn the screen back on, plug in the charger or press ⌥ Space. Off = always listening (uses a lot more battery)."),
}

# ---- messaggi
VISION_TAG = " · sees images"
CHOSEN_BY_YOU = "Model chosen by you."
INSTALLED_WITH_OLLAMA = "Installed with Ollama."
BLOCK = {"integrato nel Mac": "built into the Mac", "in uso": "in use", "ultimo installato": "last one installed"}      # (il Swift confronta i valori italiani: qui solo per chi li mostra)

SCREEN_NO_HELPER = " ⚠︎ The program that reads the screen is missing: run the installation again."
SCREEN_HINT = " Models that see images: Gemma 4 (E4B, 12B). They don't: Gemma 2 9B and Gemma 3 (1B, 4B, 12B). It will use {model}: "
SCREEN_READY = "already on this Mac."
SCREEN_TO_DOWNLOAD = "to be downloaded (pick it among the chatbots and press \"Download\")."
SCREEN_NO_VLM = " ⚠︎ The vision component is missing: run the installation again."

MSG = {
    "wake_bad": "Type two or three words, for example \"Hey Aria\" or \"Hi Aria\": with a single word it would wake up every time it hears it in a sentence.",
    "unknown_feature": "unknown feature: {name}",
    "unknown_version": "unknown version: {profile}",
    "need_version": "the version is needed: light, medium, heavy or custom",
    "remove_what": "what do you want to remove? 'stt' or 'llm', not '{kind}'",
    "not_installed": "This model isn't installed.",
    "in_use": "It is the model Aria is using: pick another one first and apply.",
    "last_one": "It is the only one installed: Aria needs at least one model to work.",
    "bad_path": "Invalid path: I'm not removing anything.",
    "ollama_not_removed": "Ollama didn't remove it ({err}).",
    "bad_stt_name": "The speech recognition model name isn't valid: '{name}' (it needs the organisation/name format, for example mlx-community/whisper-small-mlx).",
    "bad_llm_name": "The chatbot name isn't valid: '{name}' (an Ollama name like llama3.1:8b, or an MLX model like mlx-community/gemma-3-text-4b-it-4bit).",
    "no_apple_helper": "The helper program for Apple speech recognition is missing: run app/install.sh again (it compiles it).",
    "hf_not_found_stt": "I can't find the model '{repo}' on Hugging Face ({err}). Check the name and your connection.",
    "hf_not_found_llm": "I can't find the chatbot '{llm}' on Hugging Face ({err}). Check the name and your connection.",
    "no_space": "Not enough space: about {need:.1f} GB are needed (plus {margin:.1f} GB to spare) and you have {free:.1f} GB free.",
    "ollama_off": "Ollama isn't running: open it and try again (or pick an MLX chatbot, which doesn't need it).",
    "ollama_no_answer": "Ollama isn't answering: open it and try again (or pick an MLX chatbot, which doesn't need it).",
    "stt_not_ready": "Speech recognition '{repo}' {why}.",
    "stt_not_downloaded": "isn't downloaded yet",
    "llm_not_installed": "The chatbot '{llm}' isn't installed.",
    "llm_not_ready": "The chatbot '{repo}' {why}.",
    "llm_not_downloaded": "isn't downloaded yet",
    "dl_interrupted": "the download stopped before the end",
    "bad_model_stt": "'{repo}' {problem}.",
    "language_unknown": "unknown language: {code} (use it, en or auto)",
}

PROBLEMS = {
    "non e' scaricato": "isn't downloaded",
    "manca config.json: non e' un modello MLX Whisper": "config.json is missing: it isn't an MLX Whisper model",
    "non e' nel formato MLX Whisper (cerca un modello 'mlx-community/whisper-…')": "isn't in the MLX Whisper format (look for a 'mlx-community/whisper-…' model)",
    "mancano i pesi del modello": "the model weights are missing",
    "manca config.json: non e' un modello di linguaggio MLX": "config.json is missing: it isn't an MLX language model",
    "non e' un modello di linguaggio MLX": "isn't an MLX language model",
    "il download e' incompleto": "the download is incomplete",
}


def problem(it: str) -> str:
    """Il motivo per cui un modello non va, in inglese (i motivi con un nome dentro, come il tipo di modello, si compongono qui)."""
    if it in PROBLEMS:
        return PROBLEMS[it]
    if it.startswith("il tipo di modello '") and it.endswith("non e' supportato da Aria"):
        return "the model type " + it[len("il tipo di modello "):-len(" non e' supportato da Aria")] + " isn't supported by Aria"
    return it
