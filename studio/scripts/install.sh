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

# 2. Frontend build. Pick the BEST node across PATH + every nvm install: highest FULL
# version (major.minor.patch) whose npm actually works. Two refinements over a naive
# "newest major" scan: (a) a too-old system node (e.g. apt node 16) must not hide an
# nvm node 20; (b) a half-removed npm in one nvm dir (a dangling npm symlink with no
# npm-cli.js — seen when two same-major installs coexist) must not shadow a healthy
# sibling. nvm not required.
NODE_DIR=""; node_major=0; best_key=0
for cand in "$(command -v node 2>/dev/null)" $(ls -d "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null); do
  [ -x "$cand" ] || continue
  ver=$("$cand" -p 'process.versions.node' 2>/dev/null) || continue
  maj=${ver%%.*}; rest=${ver#*.}; min=${rest%%.*}; pat=${rest#*.}; pat=${pat%%[-+]*}
  [ "${maj:-0}" -ge 20 ] 2>/dev/null || continue
  dir="$(dirname "$cand")"
  # npm must be RUNNABLE, not just present: its CLI module has to exist on disk
  # (a bare symlink whose target was pruned still passes `-x`, then crashes at build).
  [ -f "$dir/../lib/node_modules/npm/bin/npm-cli.js" ] || continue
  key=$(( maj * 1000000 + ${min:-0} * 1000 + ${pat:-0} ))
  if [ "$key" -gt "$best_key" ]; then best_key=$key; NODE_DIR="$dir"; node_major=$maj; fi
done
if [ -z "$NODE_DIR" ]; then
  echo "ERROR: no Node 20+ with a working npm found on PATH or under ~/.nvm. Install Node 20+" >&2
  echo "       (run ./deploy/install-prereqs.sh, or 'nvm install --lts' to repair a broken npm)." >&2
  exit 1
fi
node_crash_hint() {
  echo >&2
  echo "ERROR: the frontend 'npm' step crashed. If you saw 'Illegal instruction (core" >&2
  echo "dumped)' or a V8 'TurboFan/unreachable code' fatal, that's Node's JIT hitting an" >&2
  echo "instruction this environment rejects — almost always WSL 1 or a very old CPU:" >&2
  echo "  • Switch to WSL 2 (also REQUIRED for the GPU): in Windows PowerShell run" >&2
  echo "      wsl -l -v        # if your distro shows VERSION 1, that's the cause" >&2
  echo "      wsl --set-version <distro> 2" >&2
  echo "  • Or, to retry without the JIT (slower but works):" >&2
  echo "      NODE_OPTIONS=--jitless ./deploy/install.sh" >&2
}
pushd frontend >/dev/null
# bypass the global ~/.npmrc that has a `prefix=` that confuses nvm. NODE_OPTIONS is
# passed through so a --jitless retry works around a V8 JIT crash on constrained hosts.
PATH="$NODE_DIR:$PATH" NPM_CONFIG_PREFIX= npm install --no-audit --no-fund --userconfig /dev/null || { node_crash_hint; exit 1; }
PATH="$NODE_DIR:$PATH" NPM_CONFIG_PREFIX= npm run build --userconfig /dev/null || { node_crash_hint; exit 1; }
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
