#!/usr/bin/env bash
# Build the macu-web Studio demo: stage Studio's PRODUCTION frontend build, inject
# the demo Service-Worker registration + ribbon, bake ep-005 fixtures, and publish
# to the host dir the demo's nginx container serves.
#
# Wired into studio/scripts/install.sh (best-effort) so the demo auto-tracks every
# Studio deploy. Run standalone any time to refresh:  ./studio/scripts/build_demo.sh
set -euo pipefail

STUDIO="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$STUDIO/.." && pwd)"
# Pull in local, gitignored config (MACU_DEMO_FLY_APP, FLY_API_TOKEN, MACU_WEB_DEMO_DIR, …).
[ -f "$REPO/.env" ] && { set -a; . "$REPO/.env"; set +a; }
FRONTEND="$STUDIO/frontend"
DEMO="$STUDIO/demo"
DEST="${MACU_WEB_DEMO_DIR:-/mnt/storage/macu-web/demo}"
SLUG="${DEMO_EPISODE:-ep-005}"

echo ">>> demo build  (episode=$SLUG  ->  $DEST)"

# 1. Need a production build to wrap. install.sh runs `npm run build` just before us;
#    when run standalone, build it if it's missing.
if [ ! -f "$FRONTEND/dist/index.html" ]; then
  echo "    frontend/dist missing — building it"
  ( cd "$FRONTEND" && npm run build )
fi

# 2. Stage the real bundle + the demo SW.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -a "$FRONTEND/dist/." "$STAGE/"
cp -a "$DEMO/sw.js" "$STAGE/sw.js"

# 3. Inject the SW-registration + ribbon into index.html (markers in demo/inject.html).
python3 - "$STAGE/index.html" "$DEMO/inject.html" <<'PY'
import sys, re
index_path, inject_path = sys.argv[1], sys.argv[2]
raw = open(inject_path).read()
head = raw.split("<!-- {{HEAD}} -->", 1)[1].split("<!-- {{BODY}} -->", 1)[0].strip()
body = raw.split("<!-- {{BODY}} -->", 1)[1].strip()
html = open(index_path).read()
if "macu-demo-ribbon" not in html:
    html = re.sub(r"</head>", head + "\n</head>", html, count=1)
    html = re.sub(r"</body>", body + "\n</body>", html, count=1)
open(index_path, "w").write(html)
print("    injected demo SW + ribbon into index.html")
PY

# 4. Bake fixtures + media into STAGE/data (prefer the studio venv for macu_studio + ffmpeg).
PY="$STUDIO/.venv/bin/python"; [ -x "$PY" ] || PY="python3"
PYTHONPATH="$STUDIO/backend" "$PY" "$STUDIO/scripts/gen_demo_fixtures.py" "$SLUG" --out "$STAGE"

# 5. Publish to the local dir the dev demo container serves (LAN dev).
mkdir -p "$DEST"
rsync -a --delete "$STAGE/" "$DEST/"
echo ">>> demo published to $DEST  ($(du -sh "$DEST" | cut -f1))"

# 6. Publish PROD to a Fly app (set MACU_DEMO_FLY_APP, e.g. "macu-demo"). flyctl must be
#    installed and authenticated (FLY_API_TOKEN in env/.env, or `fly auth login`). Skipped
#    cleanly on installs that don't set MACU_DEMO_FLY_APP.
FLY_APP="${MACU_DEMO_FLY_APP:-}"
if [ -n "$FLY_APP" ]; then
  export PATH="$HOME/.fly/bin:$PATH"
  if command -v flyctl >/dev/null 2>&1; then
    echo ">>> deploying demo to Fly app: $FLY_APP"
    FLYCTX="$(mktemp -d)"; mkdir -p "$FLYCTX/content"
    cp -a "$STAGE/." "$FLYCTX/content/"
    cp "$DEMO/fly/Dockerfile" "$DEMO/fly/default.conf" "$DEMO/fly/fly.toml" "$FLYCTX/"
    ( cd "$FLYCTX" && flyctl deploy -a "$FLY_APP" --config fly.toml --ha=false )
    rm -rf "$FLYCTX"
    echo ">>> demo deployed to Fly app $FLY_APP"
  else
    echo "    flyctl not found — skipping Fly deploy (set up flyctl to publish prod)"
  fi
fi
