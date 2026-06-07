#!/usr/bin/env bash
# Start MACU Studio (foreground; Ctrl-C to stop). Reads host/port from .env.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
set -a; [ -f "$REPO/.env" ] && . "$REPO/.env"; set +a
HOST="${MACU_STUDIO_HOST:-0.0.0.0}"
PORT="${MACU_STUDIO_PORT:-8774}"

cd "$REPO/studio"
if [ ! -x .venv/bin/uvicorn ]; then
  echo "MACU Studio isn't built yet. Run ./deploy/install.sh first"
  echo "(or just the app step: ./studio/scripts/install.sh)."
  exit 1
fi

echo "MACU Studio  ->  http://localhost:$PORT/   (Ctrl-C to stop)"
exec env PYTHONPATH=backend .venv/bin/uvicorn macu_studio.main:app --host "$HOST" --port "$PORT"
