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

# 1. Backend venv
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .

# 2. Frontend build
pushd frontend >/dev/null
# bypass the global ~/.npmrc that has a `prefix=` that confuses nvm
PATH="$HOME/.nvm/versions/node/$(ls $HOME/.nvm/versions/node | tail -1)/bin:$PATH" \
  NPM_CONFIG_PREFIX= \
  npm install --no-audit --no-fund --userconfig /dev/null
PATH="$HOME/.nvm/versions/node/$(ls $HOME/.nvm/versions/node | tail -1)/bin:$PATH" \
  NPM_CONFIG_PREFIX= \
  npm run build --userconfig /dev/null
popd >/dev/null

echo
echo "Build complete. Run MACU Studio one of two ways:"
echo
echo "  1) Just for now — foreground, Ctrl-C to stop:"
echo "       ./deploy/start-studio.sh"
echo
echo "  2) As a background service that starts on boot and auto-restarts (root):"
echo "       sudo cp $HERE/systemd/macu-studio.service /etc/systemd/system/macu-studio.service"
echo "       sudo systemctl daemon-reload"
echo "       sudo systemctl enable --now macu-studio"
echo "       sudo touch /var/log/macu-studio.log && sudo chown $(id -un):$(id -gn) /var/log/macu-studio.log"
echo "     Manage it later:"
echo "       sudo systemctl stop macu-studio            # stop now (still starts on boot)"
echo "       sudo systemctl disable --now macu-studio   # stop AND don't start on boot"
echo
echo "Then open: http://localhost:8774/  (or http://<this-host>:8774/)"
