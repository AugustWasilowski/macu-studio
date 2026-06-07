#!/usr/bin/env bash
# Top-level MACU installer. Runs the mechanical stages in order on a fresh machine;
# each stage skips work already done. The un-scriptable parts (systemd units, the
# Claude Code channel) are printed at the end for you to finish by hand.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO"
echo "######## MACU install ########"

echo; echo ">>> [1/6] preflight"
./deploy/doctor.sh || { echo "Install the missing prerequisites above, then re-run."; exit 1; }

echo; echo ">>> [2/6] config (.env)"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "If your storage isn't /mnt/storage, edit MACU_SHARES (and deploy/services/.env"
  echo "MACU_DATA_ROOT) now, then re-run this script."
fi
[ -f deploy/services/.env ] || cp deploy/services/.env.example deploy/services/.env
set -a; . ./.env 2>/dev/null || true; . ./deploy/services/.env 2>/dev/null || true; set +a
export MACU_DATA_ROOT="${MACU_DATA_ROOT:-/mnt/storage}"

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

######## install staged ########
Mechanical install done. To finish:

  • Start MACU Studio:
      cd studio && PYTHONPATH=backend .venv/bin/uvicorn macu_studio.main:app --host 0.0.0.0 --port 8774
    (or install the systemd unit per studio/scripts/install.sh's printed steps)
    Then open http://localhost:8774/

  • (Your own 2nd machine only) copy your voices + asset kits from an existing box:
      deploy/sync-personal-data.sh <user@your-existing-box>

  • Studio↔Claude chat tile / writers' room (the coupled half — needs Claude Code):
      a `setup-macu-channel` skill is the planned next phase.
EOF
