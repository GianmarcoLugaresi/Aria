#!/usr/bin/env bash
# Installa Aria per Mac: ambiente Python arm64, app in ~/Applications, configurazione, modelli.
# Uso:  ./app/install.sh        (puoi rilanciarlo: aggiorna senza toccare la tua configurazione)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUPPORT="$HOME/Library/Application Support/Aria"
MODEL="${ARIA_MODEL:-gemma3:4b}"          # solo per chi sceglie Ollama come chatbot

say() { printf "\n\033[1m== %s\033[0m\n" "$1"; }

say "Controlli"
[ "$(uname -m)" = "arm64" ] || { echo "Serve un Mac con chip Apple (arm64)."; exit 1; }
command -v swift >/dev/null 2>&1 || { echo "Mancano gli strumenti per compilare l'app. Esegui:  xcode-select --install"; exit 1; }

say "1/6 Python nativo (uv)"
if ! command -v uv >/dev/null 2>&1; then
  echo "Installo 'uv' (gestore Python di Astral, dal sito ufficiale)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
mkdir -p "$SUPPORT"
if [ ! -x "$SUPPORT/venv/bin/python" ]; then
  uv venv "$SUPPORT/venv" --python cpython-3.12-macos-aarch64
fi

say "2/6 Librerie (Whisper e chatbot su GPU, voce Pocket TTS, rilevamento voce…)"
uv pip install --python "$SUPPORT/venv/bin/python" -q \
  numpy httpx pyyaml websockets sounddevice faster-whisper mlx-whisper mlx-lm pysilero-vad pocket-tts ddgs pypdf
# il modello che «vede» (guardare lo schermo): senza dipendenze, per non toccare le versioni di mlx e transformers che gia' funzionano
uv pip install --python "$SUPPORT/venv/bin/python" -q --no-deps mlx-vlm pillow
# la «voce naturale» (Qwen3-TTS, si accende dalle Impostazioni): stessa cosa, il modello (~0,9 GB) si scarica da solo al primo uso
uv pip install --python "$SUPPORT/venv/bin/python" -q --no-deps "mlx-audio==0.5.8" miniaudio

say "3/6 Il programma di Aria"
mkdir -p "$SUPPORT/software"
rsync -a --delete --exclude "__pycache__" "$ROOT/software/aria/" "$SUPPORT/software/aria/"
# riconoscimento vocale integrato nel Mac (Apple SpeechTranscriber): programma di supporto compilato qui, senza modelli da scaricare e senza RAM in piu'
mkdir -p "$SUPPORT/bin"
if [ -f "$ROOT/software/helpers/aria_apple_stt.swift" ]; then
  swiftc -parse-as-library -O "$ROOT/software/helpers/aria_apple_stt.swift" -o "$SUPPORT/bin/aria-apple-stt" 2>/dev/null \
    || echo "(il riconoscimento vocale integrato di Apple non e' disponibile con questa versione di macOS: resta Whisper)"
fi
# microfono con il filtro eco di macOS (Voice Processing, come le chiamate FaceTime): toglie la voce di Aria dal microfono e permette di interromperla a voce mentre parla
if [ -f "$ROOT/software/helpers/aria_vpmic.swift" ]; then
  swiftc -O "$ROOT/software/helpers/aria_vpmic.swift" -o "$SUPPORT/bin/aria-vpmic" 2>/dev/null \
    || echo "(il filtro eco del Mac non e' disponibile: si interrompe Aria a voce solo nelle pause o con le cuffie)"
fi
# lettura dello schermo con il riconoscimento testo di macOS (Vision): programma di supporto, nessun modello da scaricare
if [ -f "$ROOT/software/helpers/aria_apple_ocr.swift" ]; then
  swiftc -O "$ROOT/software/helpers/aria_apple_ocr.swift" -o "$SUPPORT/bin/aria-apple-ocr" 2>/dev/null \
    || echo "(l'OCR del Mac non e' disponibile con questa versione di macOS: resta l'opzione «un modello che vede»)"
fi
# posizione esatta di pulsanti, icone e menu con l'Accessibilita' di macOS (serve il permesso «Accessibilita» per Aria)
if [ -f "$ROOT/software/helpers/aria_ax.swift" ]; then
  swiftc -O "$ROOT/software/helpers/aria_ax.swift" -o "$SUPPORT/bin/aria-ax" 2>/dev/null \
    || echo "(la lettura dei pulsanti con l'Accessibilita' non e' disponibile: restano OCR e modello che vede)"
fi
# il riquadro luminoso con cui Aria indica un pulsante o una scritta sullo schermo (finestra trasparente che lascia passare i clic)
if [ -f "$ROOT/software/helpers/aria_pointer.swift" ]; then
  swiftc -O "$ROOT/software/helpers/aria_pointer.swift" -o "$SUPPORT/bin/aria-pointer" 2>/dev/null \
    || echo "(il riquadro che indica sullo schermo non e' disponibile: Aria dice la posizione a parole)"
fi
[ -f "$SUPPORT/config.yaml" ] || cp "$ROOT/app/config.app.yaml" "$SUPPORT/config.yaml"
[ -f "$SUPPORT/persona.md" ] || cp "$ROOT/anima/persona_compatta.md" "$SUPPORT/persona.md"
cat > "$SUPPORT/paths.json" <<JSON
{"python": "$SUPPORT/venv/bin/python", "software": "$SUPPORT/software", "config": "$SUPPORT/config.yaml"}
JSON

say "4/6 L'app"
mkdir -p "$HOME/Applications"
"$ROOT/app/build_app.sh" "$HOME/Applications"

say "5/6 Chatbot"
if grep -q "kind: mlx-lm" "$SUPPORT/config.yaml" 2>/dev/null; then
  echo "Il chatbot gira dentro Aria: non serve Ollama. Lo scarica il passo successivo."
elif ! command -v ollama >/dev/null 2>&1; then
  echo "La tua configurazione usa Ollama, che non è installato. Installalo da https://ollama.com, oppure scegli un chatbot «dentro Aria» da Impostazioni."
elif grep -q "^$MODEL" <<<"$(ollama list 2>/dev/null || true)"; then
  echo "già presente (Ollama)"
else
  if [ "${ARIA_YES:-}" = 1 ]; then ans=s; else read -r -p "Scarico $MODEL con Ollama? (circa 3,3 GB) [s/N] " ans || ans=""; fi
  if [[ "$ans" =~ ^[sSyY] ]]; then ollama pull "$MODEL"; else echo "Salto: ricordati di eseguire  ollama pull $MODEL"; fi
fi

say "6/6 Modelli (Whisper ~0,5 GB, chatbot ~2,6 GB, voce ~0,25 GB: solo al primo giro)"
PYTHONPATH="$SUPPORT/software" "$SUPPORT/venv/bin/python" -m aria.main --prefetch --config "$SUPPORT/config.yaml" || true

cat <<MSG

Fatto.  Apri l'app:   open ~/Applications/Aria.app
  • la prima volta macOS chiede il permesso per il microfono: concedilo
  • poi dì «Hey Aria» oppure premi  ⌥ + Spazio
  • nel menu in alto (il logo di Aria) trovi voce, silenzio, «Apri all'accesso» e «Impostazioni…» (versione Leggera/Media/Pesante/Personalizzata, scelta dei modelli e cestino per rimuoverli)
Configurazione: $SUPPORT/config.yaml   ·   Carattere: $SUPPORT/persona.md   ·   Log: ~/Library/Logs/Aria
MSG
