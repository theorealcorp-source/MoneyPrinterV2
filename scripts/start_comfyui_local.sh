#!/usr/bin/env bash

set -euo pipefail

COMFYUI_ROOT="${COMFYUI_ROOT:-/Users/theo/iCloud Drive (Archive)/Documents/ComfyUI/app}"
COMFYUI_HOST="${COMFYUI_HOST:-127.0.0.1}"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"

if [ ! -d "$COMFYUI_ROOT" ]; then
  echo "ComfyUI root not found: $COMFYUI_ROOT" >&2
  exit 1
fi

if [ ! -x "$COMFYUI_ROOT/.venv/bin/python" ]; then
  echo "ComfyUI virtualenv not found: $COMFYUI_ROOT/.venv" >&2
  exit 1
fi

export PYTORCH_ENABLE_MPS_FALLBACK=1

exec "$COMFYUI_ROOT/.venv/bin/python" "$COMFYUI_ROOT/main.py" \
  --listen "$COMFYUI_HOST" \
  --port "$COMFYUI_PORT"
