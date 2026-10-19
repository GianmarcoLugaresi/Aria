#!/usr/bin/env bash
# Prepara Aria sul Raspberry Pi 5 (Raspberry Pi OS Bookworm/Trixie a 64 bit). Da lanciare DENTRO la cartella software/.
set -euo pipefail
cd "$(dirname "$0")/.."

sudo apt update
sudo apt install -y python3-venv python3-dev libportaudio2 portaudio19-dev libsndfile1 espeak-ng ffmpeg \
                    chromium-browser unclutter git cmake build-essential

python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e ".[raspberry]"

mkdir -p models
base=https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT/paola/medium
[ -f models/it_IT-paola-medium.onnx ]      || curl -L -o models/it_IT-paola-medium.onnx      "$base/it_IT-paola-medium.onnx"
[ -f models/it_IT-paola-medium.onnx.json ] || curl -L -o models/it_IT-paola-medium.onnx.json "$base/it_IT-paola-medium.onnx.json"
python -c "import openwakeword; openwakeword.utils.download_models()"

# SPI per la strip LED (WS2812 sul pin MOSI/GPIO10)
sudo raspi-config nonint do_spi 0 || true

cat <<MSG

Installato. Resta da fare (una volta):
  - llama.cpp per il cervello "di scorta" sul Pi:  vedi scripts/README_brain.md (sezione Raspberry)
  - copia config.example.yaml in config.yaml e sistemalo
  - servizi automatici:  sudo cp systemd/*.service /etc/systemd/system/ && sudo systemctl enable --now aria aria-display
MSG
