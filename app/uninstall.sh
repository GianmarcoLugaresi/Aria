#!/usr/bin/env bash
# Toglie Aria dal Mac. NON cancella i modelli di Ollama.
set -euo pipefail
pkill -f "Aria.app/Contents/MacOS/Aria" 2>/dev/null || true
rm -rf "$HOME/Applications/Aria.app"
read -r -p "Cancello anche ambiente, configurazione e memoria in ~/Library/Application Support/Aria? [s/N] " a || a=""
if [[ "$a" =~ ^[sSyY] ]]; then rm -rf "$HOME/Library/Application Support/Aria" "$HOME/.aria"; fi
echo "Fatto. Se avevi attivato «Apri all'accesso», si toglie da solo con l'app."
echo "Per liberare spazio: ollama rm gemma3:4b   e   rm -rf ~/.cache/huggingface/hub/models--kyutai--pocket-tts ~/.cache/huggingface/hub/models--Systran--faster-whisper-small"
