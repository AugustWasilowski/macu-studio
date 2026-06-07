#!/usr/bin/env bash
# Top-level MACU installer. Runs the mechanical stages in order on a fresh machine;
# each stage skips work already done. The un-scriptable parts (systemd units, the
# Claude Code channel) are printed at the end for you to finish by hand.
# Usage: ./deploy/install.sh [-y|--yes]   (-y skips the confirm prompt)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO"

AUTO=0
for a in "$@"; do case "$a" in -y|--yes) AUTO=1 ;; esac; done

cat <<'BANNER'

   ██    ██   ██████    ██████   ██    ██
   ███  ███  ██    ██  ██        ██    ██
   ██ ██ ██  ████████  ██        ██    ██
   ██    ██  ██    ██  ██        ██    ██
   ██    ██  ██    ██   ██████    ██████

   Mayor Awesome Cinematic Universe — Studio installer

   This downloads several GB of models and stands up local services
   (ComfyUI, OmniVoice, Ollama, Piper HAL) via Docker. Beta software — you're on your own.

BANNER

if [ "$AUTO" = 0 ]; then
  if [ -t 0 ]; then
    read -r -p "   Cool to continue? [Y/n] " ans
    case "$ans" in [nN]|[nN][oO]) echo "   Aborted."; exit 1 ;; *) ;; esac
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

echo; echo ">>> [5/6] build + start long-lived services (ComfyUI + Piper HAL)"
docker compose -f deploy/services/comfyui/docker-compose.yml build
docker compose -f deploy/services/comfyui/docker-compose.yml up -d
# Piper — the default synthetic voice (engine "piper") on :5050. CPU-only; a
# permissive voice is baked into the image (HAL is opt-in via PIPER_VOICE=hal).
docker compose -f deploy/services/piper/docker-compose.yml up -d --build

echo; echo ">>> [6/6] MACU Studio app (venv + frontend build) + whisper ASR venv"
MACU_INSTALLER=1 ./studio/scripts/install.sh   # suppress its standalone "next steps" footer
# Stage 6 ASR runs in its own venv so CTranslate2/faster-whisper stay out of the
# main interpreter. Provision it once (override the location with MACU_WHISPER_VENV).
if [ ! -x "$REPO/.whisper-venv/bin/python" ]; then
  echo "provisioning whisper ASR venv (.whisper-venv) ..."
  python3 -m venv "$REPO/.whisper-venv"
  "$REPO/.whisper-venv/bin/pip" install --quiet --upgrade pip
  "$REPO/.whisper-venv/bin/pip" install --quiet -r "$REPO/pipeline/requirements-whisper.txt"
fi

echo; echo ">>> optional: terminal coupling deps (ttyd + tmux for Studio's TERMINAL drawer)"
need=""
command -v ttyd >/dev/null 2>&1 || need="$need ttyd"
command -v tmux >/dev/null 2>&1 || need="$need tmux"
if [ -z "$need" ]; then
  echo "ttyd + tmux already present"
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq && sudo apt-get install -y $need \
    || echo "couldn't install$need — install by hand for the TERMINAL drawer (it's optional)"
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y $need || echo "couldn't install$need — install by hand (optional)"
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --noconfirm $need || echo "couldn't install$need — install by hand (optional)"
else
  echo "missing$need and no apt-get/dnf/pacman detected — install them by hand to use the"
  echo "Studio TERMINAL drawer (optional; the rest of Studio works without it)."
fi

cat <<'EOF'

######## install complete ########
Start MACU Studio:

      ./deploy/start-studio.sh        # then open http://localhost:8774/

Optional next steps:

  • Run on boot (systemd):  sudo ./deploy/install-systemd.sh
      Templates the macu-render + macu-studio units to THIS machine and installs them.
  • Claude Code coupling — the chat tile, writers' room, AND the in-app TERMINAL
    drawer (needs Claude Code): run  /setup-macu-channel  in Claude Code.
      The TERMINAL drawer (right-hand panel) will refuse to connect until this runs.
EOF
