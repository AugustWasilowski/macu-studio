#!/usr/bin/env bash
# Install / refresh MACU Studio in-place. Idempotent — re-run after pulling.
#
# Assumes:
#   - You're on Max (the box this is meant to run on).
#   - nvm + Node 22 already installed (see ~/.nvm).
#   - python3.11+ available as python3.
#   - You will install the systemd unit manually (the script prints next steps).

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

# 1. Backend venv. This same venv runs serve.py → run.py (the render pipeline), so
# it also needs the pipeline's deps (Pillow, python-dotenv).
if [ ! -d .venv ]; then
  "${MACU_PYTHON:-python3}" -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .
.venv/bin/pip install --quiet -r "$HERE/../pipeline/requirements.txt"

# 2. Frontend build. Resolve Node: prefer one already on PATH, else the newest nvm
# install (sort -V, not lexical). nvm is recommended but NOT required.
NODE_DIR=""
if command -v npm >/dev/null 2>&1; then
  NODE_DIR="$(dirname "$(command -v npm)")"
elif [ -d "$HOME/.nvm/versions/node" ]; then
  NODE_DIR="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"
fi
if [ -z "$NODE_DIR" ] || [ ! -x "$NODE_DIR/npm" ]; then
  echo "ERROR: Node 20+ / npm not found on PATH or under ~/.nvm. Install Node and re-run." >&2
  exit 1
fi
pushd frontend >/dev/null
# bypass the global ~/.npmrc that has a `prefix=` that confuses nvm
PATH="$NODE_DIR:$PATH" NPM_CONFIG_PREFIX= npm install --no-audit --no-fund --userconfig /dev/null
PATH="$NODE_DIR:$PATH" NPM_CONFIG_PREFIX= npm run build --userconfig /dev/null
popd >/dev/null

# When run as part of the top-level installer (MACU_INSTALLER=1), stay quiet — the
# parent prints the canonical "next steps" at the very end, after the remaining steps.
# Only print run instructions when invoked standalone (just rebuilding the app).
if [ -z "${MACU_INSTALLER:-}" ]; then
  echo
  echo "Build complete. Run MACU Studio one of two ways:"
  echo
  echo "  1) Just for now — foreground, Ctrl-C to stop:"
  echo "       ./deploy/start-studio.sh"
  echo
  echo "  2) As background services that start on boot and auto-restart (root):"
  echo "       sudo ./deploy/install-systemd.sh           # templates the units to this machine"
  echo "       sudo systemctl enable --now macu-render macu-studio"
  echo "     Manage them later:"
  echo "       sudo systemctl stop macu-render macu-studio       # stop now (still start on boot)"
  echo "       sudo systemctl disable macu-render macu-studio    # don't start on boot"
  echo
  echo "Then open: http://localhost:8774/  (or http://<this-host>:8774/)"
fi
