#!/usr/bin/env bash
# Install ComfyUI's requirements.txt on every start so host-side `git pull`
# updates to ComfyUI's pinned versions take effect on the next restart.
# Torch + the heavy CUDA layers are already baked into the image — pip is
# fast for the small pure-Python deltas.
set -euo pipefail
if [ -f /workspace/requirements.txt ]; then
  echo "[entrypoint] installing ComfyUI requirements"
  /opt/venv/bin/pip install --quiet -r /workspace/requirements.txt || \
    echo "[entrypoint] WARN: requirements.txt install had errors — continuing"
fi
exec "$@"
