#!/usr/bin/env bash
# Top-level MACU installer. Runs the mechanical stages in order on a fresh machine;
# each stage skips work already done. The un-scriptable parts (systemd units, the
# Claude Code channel) are printed at the end for you to finish by hand.
# Usage: ./deploy/install.sh [-y|--yes]   (-y skips the confirm prompt)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO"

AUTO=0
case "${1:-}" in -y|--yes) AUTO=1 ;; esac

cat <<'BANNER'

   ██    ██   ██████    ██████   ██    ██
   ███  ███  ██    ██  ██        ██    ██
   ██ ██ ██  ████████  ██        ██    ██
   ██    ██  ██    ██  ██        ██    ██
   ██    ██  ██    ██   ██████    ██████

   Mayor Awesome Cinematic Universe — Studio installer

   This downloads several GB of models and stands up local GPU services
   (ComfyUI, OmniVoice, Ollama) via Docker. Beta software — you're on your own.

BANNER

if [ "$AUTO" = 0 ]; then
  if [ -t 0 ]; then
    read -r -p "   Cool to continue? [y/N] " ans
    case "$ans" in [yY]|[yY][eE][sS]) ;; *) echo "   Aborted."; exit 1 ;; esac
  else
    echo "   Non-interactive shell — re-run with -y to proceed."; exit 1
  fi
fi
echo

echo; echo ">>> [1/6] preflight"
./deploy/doctor.sh || { echo "Install the missing prerequisites above, then re-run."; exit 1; }

echo; echo ">>> [2/6] config (.env)"
created=0
[ -f .env ] || { cp .env.example .env; created=1; }
[ -f deploy/services/.env ] || { cp deploy/services/.env.example deploy/services/.env; created=1; }
if [ "$created" = 1 ]; then
  cat <<EOF
Created .env (and deploy/services/.env) from the examples.

  >> Set your storage paths before continuing. The defaults are /mnt/storage,
     which only exists on the original host. Pick a WRITABLE location on THIS
     machine — on WSL prefer the Linux filesystem (e.g. \$HOME) over /mnt/c|/mnt/f
     (Windows mounts are slow for the models + render IO):

       .env                  ->  MACU_SHARES=\$HOME/macu-data/shares/MACU
       deploy/services/.env  ->  MACU_DATA_ROOT=\$HOME/macu-data

  Then re-run:  ./deploy/install.sh
EOF
  exit 0
fi
set -a; . ./.env 2>/dev/null || true; . ./deploy/services/.env 2>/dev/null || true; set +a
export MACU_DATA_ROOT="${MACU_DATA_ROOT:-/mnt/storage}"
export MACU_SHARES="${MACU_SHARES:-/mnt/storage/shares/MACU}"
# Fail clearly now rather than with cryptic mkdir errors mid-download.
for d in "$MACU_DATA_ROOT" "$MACU_SHARES"; do
  if ! mkdir -p "$d" 2>/dev/null; then
    echo "ERROR: can't create '$d' (from your .env). Edit .env (MACU_SHARES) and"
    echo "       deploy/services/.env (MACU_DATA_ROOT) to a writable path, then re-run."
    exit 1
  fi
done
echo "config OK  —  data: $MACU_DATA_ROOT   shares: $MACU_SHARES"

echo; echo ">>> [3/6] pull on-demand service images (ollama + omnivoice)"
docker compose -f deploy/services/ollama/docker-compose.yml pull
docker compose -f deploy/services/omnivoice/docker-compose.yml pull

echo; echo ">>> [4/6] fetch public models + assets (~8 GB — slow)"
./deploy/fetch-models.sh

echo; echo ">>> [5/6] build + start ComfyUI (long-lived service)"
docker compose -f deploy/services/comfyui/docker-compose.yml build
docker compose -f deploy/services/comfyui/docker-compose.yml up -d

echo; echo ">>> [6/6] MACU Studio app (venv + frontend build)"
./studio/scripts/install.sh

cat <<'EOF'

######## install complete ########
Start MACU Studio:

      ./deploy/start-studio.sh        # then open http://localhost:8774/

Optional next steps:

  • Chat tile / writers' room (needs Claude Code): run  /setup-macu-channel  in Claude Code.
  • (Your own 2nd machine) copy your voices + asset kits from an existing box:
        deploy/sync-personal-data.sh <user@your-existing-box>
EOF
