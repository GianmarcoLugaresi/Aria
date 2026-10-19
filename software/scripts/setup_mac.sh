#!/usr/bin/env bash
# Prepara Aria sul Mac per sviluppare e provare. Scarica SOLO cio' che e' scritto qui sotto (circa 0,4 GB).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e ".[mac,test]"

mkdir -p models
echo "== Voce Piper italiana 'paola' (~60 MB)"
base=https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium
[ -f models/it_IT-paola-medium.onnx ]      || curl -L -o models/it_IT-paola-medium.onnx      "$base/it_IT-paola-medium.onnx"
[ -f models/it_IT-paola-medium.onnx.json ] || curl -L -o models/it_IT-paola-medium.onnx.json "$base/it_IT-paola-medium.onnx.json"

echo "== Modelli di base openWakeWord (pochi MB)"
python -c "import openwakeword; openwakeword.utils.download_models()"

cat <<MSG

Fatto. Prossimi passi:
  1) prova il carattere senza audio:      python scripts/try_persona.py --config config.mac.yaml
  2) prova le voci (opzionale, Kokoro ~340 MB):
       curl -L -o models/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
       curl -L -o models/voices-v1.0.bin  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
       pip install kokoro-onnx
       python scripts/audition_voices.py --piper models/it_IT-paola-medium.onnx --kokoro-dir models
  3) parla con lei (Invio al posto del wake word): python -m aria.main --config config.mac.yaml --dev
MSG
