#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
  echo "Aviso: em Wayland, a interface funciona mas atalhos globais exigem X11/Xorg."
fi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py