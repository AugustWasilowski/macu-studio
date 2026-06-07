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

# 2. Frontend build. Pick the NEWEST node across PATH + every nvm install (a too-old
# system node, e.g. apt node 16, must not hide an nvm node 20). nvm not required.
NODE_DIR=""; node_major=0
for cand in "$(command -v node 2>/dev/null)" $(ls -d "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null); do
  [ -x "$cand" ] || continue
  maj=$("$cand" -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
  if [ "${maj:-0}" -gt "$node_major" ] 2>/dev/null; then node_major=$maj; NODE_DIR="$(dirname "$cand")"; fi
done
if [ -z "$NODE_DIR" ] || [ "$node_major" -lt 20 ] || [ ! -x "$NODE_DIR/npm" ]; then
  echo "ERROR: Node 20+ not found on PATH or under ~/.nvm (newest found: v${node_major}). Install Node 20" >&2
  echo "       (or run ./deploy/install-prereqs.sh) and re-run." >&2
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
