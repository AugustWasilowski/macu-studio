#!/usr/bin/env bash
# Install ComfyUI's requirements.txt on every start so host-side `git pull`
# updates to ComfyUI's pinned versions take effect on the next restart.
# Torch + the heavy CUDA layers are already baked into the image — pip is
# fast for the small pure-Python deltas.
set -euo pipefail
rm -f /workspace/.deps-failed
if [ -f /workspace/requirements.txt ]; then
  echo "[entrypoint] installing ComfyUI requirements"
  if ! /opt/venv/bin/pip install --quiet -r /workspace/requirements.txt; then
    # Don't block startup on a transient pip blip (the heavy deps are baked into
    # the image), but leave a greppable marker + ERROR so it isn't silent.
    echo "[entrypoint] ERROR: requirements.txt install failed — see /workspace/.deps-failed" >&2
    date > /workspace/.deps-failed
  fi
fi
exec "$@"
