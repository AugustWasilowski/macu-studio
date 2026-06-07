#!/usr/bin/env bash
# Start MACU Studio + its render service (foreground; Ctrl-C stops both).
# Reads host/port from .env.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
set -a; [ -f "$REPO/.env" ] && . "$REPO/.env"; set +a
HOST="${MACU_STUDIO_HOST:-0.0.0.0}"
PORT="${MACU_STUDIO_PORT:-8774}"
RENDER_URL="${MACU_RENDER_URL:-http://127.0.0.1:8773}"

cd "$REPO/studio"
if [ ! -x .venv/bin/uvicorn ]; then
  echo "MACU Studio isn't built yet. Run ./deploy/install.sh first"
  echo "(or just the app step: ./studio/scripts/install.sh)."
  exit 1
fi

# Studio drives the render service (pipeline/serve.py on :8773) for all rendering —
# voice, masters, assembly. Start it here unless something already answers there
# (e.g. a systemd macu-render unit on a server install). Run it under the same venv
# so serve.py launches run.py (sys.executable) with consistent deps.
RENDER_PID=""
if curl -sf -o /dev/null --max-time 2 "$RENDER_URL/health" 2>/dev/null; then
  echo "render service already up at $RENDER_URL"
else
  echo "starting render service  ->  $RENDER_URL"
  ( cd "$REPO/pipeline" && exec "$REPO/studio/.venv/bin/python" serve.py ) &
  RENDER_PID=$!
fi

cleanup() { [ -n "$RENDER_PID" ] && kill "$RENDER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "MACU Studio  ->  http://localhost:$PORT/   (Ctrl-C to stop)"
env PYTHONPATH=backend .venv/bin/uvicorn macu_studio.main:app --host "$HOST" --port "$PORT"
