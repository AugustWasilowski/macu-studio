#!/usr/bin/env bash
# Top-level MACU installer. Runs the mechanical stages in order on a fresh machine;
# each stage skips work already done. The un-scriptable parts (systemd units, the
# Claude Code channel) are printed at the end for you to finish by hand.
# Usage: ./deploy/install.sh [-y|--yes] [--with-models|--no-models] [--with-talking-head]
#   -y                  skip the confirm prompts (implies --with-models unless --no-models)
#   --no-models         "light" install: skip every AI model download (~18 GB).
#                       Generation runs remotely instead — route stills/video/
#                       lipsync to Higgsfield or a remote render box and script
#                       tools to Claude Code in Settings → Engines. Pull the
#                       models any time later: ./deploy/fetch-models.sh
#   --with-models       pull the model packs without asking
#   --with-talking-head also pull the ~28 GB Wan 2.1 + InfiniteTalk stack
#                       (local talking-head/lipsync models; implies --with-models)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO"

AUTO=0
WITH_TALKING_HEAD="${MACU_INSTALL_TALKING_HEAD:-0}"
WITH_MODELS="${MACU_INSTALL_MODELS:-}"        # empty = ask; 1/0 = decided by flag/env
for a in "$@"; do case "$a" in
  -y|--yes) AUTO=1 ;;
  --with-talking-head) WITH_TALKING_HEAD=1; WITH_MODELS=1 ;;
  --no-models) WITH_MODELS=0 ;;
  --with-models) WITH_MODELS=1 ;;
esac; done

# Retry a flaky network command up to 3 times with a growing backoff, so one WiFi
# hiccup during a multi-GB pull doesn't abort the whole install.
retry(){
  local n=0
  until "$@"; do
    n=$((n+1))
    [ "$n" -ge 3 ] && { echo "  still failing after 3 tries: $*" >&2; return 1; }
    echo "  network hiccup — retry $n/3 in $((n*5))s ..." >&2
    sleep $((n*5))
  done
}

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

# Second confirmation: the AI model packs are optional. A "light"/headless
# install skips ~18 GB of downloads and routes generation to remote services
# (Higgsfield / a remote render box / Claude Code) in Settings → Engines.
if [ -z "$WITH_MODELS" ]; then
  if [ "$AUTO" = 1 ]; then
    WITH_MODELS=1
  elif [ -t 0 ]; then
    echo "   Local AI model packs (~18 GB: zeroscope video, Z-Image stills, Ollama text)."
    echo "   Skip them for a light install — generation can run remotely instead, and"
    echo "   you can pull them any time later with ./deploy/fetch-models.sh"
    read -r -p "   Download the model packs now? [Y/n] " mans
    case "$mans" in [nN]|[nN][oO]) WITH_MODELS=0 ;; *) WITH_MODELS=1 ;; esac
  else
    WITH_MODELS=1
  fi
fi
[ "$WITH_MODELS" = 0 ] && echo "   → light install: skipping model downloads."
echo

# Optional: the WAN 2.1 + InfiniteTalk talking-head stack (~28 GB on top of the
# base packs). Powers the LOCAL WAN image-to-video masters backend and the local
# lipsync engine. Off by default — most installs route those to a remote render
# box or Higgsfield. Only offered when the base model packs are being installed;
# --with-talking-head (or MACU_INSTALL_TALKING_HEAD=1) skips the prompt.
if [ "$WITH_TALKING_HEAD" != 1 ] && [ "$WITH_MODELS" = 1 ]; then
  if [ "$AUTO" = 0 ] && [ -t 0 ]; then
    echo "   Talking-head / WAN stack — a BIG optional download (~28 GB: Wan 2.1 I2V 14B +"
    echo "   InfiniteTalk + custom nodes). Needed only for LOCAL WAN image-to-video + lipsync;"
    echo "   skip it and those run remotely. Add it later with:"
    echo "     ./deploy/fetch-models.sh --with-talking-head"
    read -r -p "   Also download the ~28 GB talking-head stack now? [y/N] " thans
    case "$thans" in [yY]|[yY][eE][sS]) WITH_TALKING_HEAD=1 ;; *) WITH_TALKING_HEAD=0 ;; esac
  fi
fi
[ "$WITH_TALKING_HEAD" = 1 ] && echo "   → including the ~28 GB talking-head / WAN stack."
echo

echo; echo ">>> [1/6] preflight"
if ! ./deploy/doctor.sh; then
  echo
  do_prereqs=0
  if [ "$AUTO" = 1 ]; then
    do_prereqs=1
  elif [ -t 0 ]; then
    read -r -p "   Try to auto-install the missing prerequisites? [Y/n] " a
    case "$a" in [nN]|[nN][oO]) ;; *) do_prereqs=1 ;; esac
  fi
  if [ "$do_prereqs" = 1 ]; then
    ./deploy/install-prereqs.sh || true
    echo; echo ">>> [1/6] preflight (re-check)"
    ./deploy/doctor.sh || {
      echo "Some prerequisites are still missing (see ✗ above). Install them — or for the GPU"
      echo "runtime, restart Docker after the toolkit install — then re-run ./deploy/install.sh"
      exit 1
    }
  else
    echo "Install the missing prerequisites above, then re-run."
    echo "(Tip: ./deploy/install-prereqs.sh tries to install them for you on apt systems.)"
    exit 1
  fi
fi

# Use a >=3.11 python for the venvs (auto-install may have just added python3.12).
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys;exit(0 if sys.version_info[:2]>=(3,11) else 1)' 2>/dev/null; then
    export MACU_PYTHON="$c"; break
  fi
done
echo "using python: ${MACU_PYTHON:-python3}"

echo; echo ">>> [2/6] config (.env)"
# Default the storage to a repo-local ./data dir so a fresh install JUST WORKS — no
# manual path editing. We do this by pointing the examples' /mnt/storage paths (the
# original host's) at $REPO/data. Override later by editing .env / deploy/services/.env.
[ -f .env ]                  || sed "s|/mnt/storage|$REPO/data|g" .env.example > .env
[ -f deploy/services/.env ]  || sed "s|/mnt/storage|$REPO/data|g" deploy/services/.env.example > deploy/services/.env
set -a; . ./.env 2>/dev/null || true; . ./deploy/services/.env 2>/dev/null || true; set +a
export MACU_DATA_ROOT="${MACU_DATA_ROOT:-$REPO/data}"
export MACU_SHARES="${MACU_SHARES:-$REPO/data/shares/MACU}"
# Fail clearly now rather than with cryptic mkdir errors mid-download.
for d in "$MACU_DATA_ROOT" "$MACU_SHARES"; do
  if ! mkdir -p "$d" 2>/dev/null; then
    echo "ERROR: can't create '$d'. Edit MACU_SHARES (.env) / MACU_DATA_ROOT"
    echo "       (deploy/services/.env) to a writable path, then re-run."
    exit 1
  fi
done
echo "config OK  —  data under: $MACU_DATA_ROOT"
case "$REPO" in
  /mnt/[a-z]/*)
    echo "  NOTE: this repo is on a Windows mount — the ~8 GB model download + renders will be"
    echo "        slow here. For speed, set MACU_DATA_ROOT/MACU_SHARES to a \$HOME path + re-run." ;;
esac
echo "  (override the data location in .env / deploy/services/.env if you want it elsewhere)"

echo; echo ">>> [3/6] pull + create on-demand service containers (ollama + omnivoice)"
retry docker compose -f deploy/services/ollama/docker-compose.yml pull
retry docker compose -f deploy/services/omnivoice/docker-compose.yml pull
# Create the containers (stopped) so the on-demand `docker start omnivoice` works
# later — pulling the image alone leaves no container to start.
docker compose -f deploy/services/ollama/docker-compose.yml create 2>/dev/null || true
docker compose -f deploy/services/omnivoice/docker-compose.yml create 2>/dev/null || true

echo; echo ">>> [4/6] fetch public models + assets (~8 GB — slow)"
MACU_INSTALL_MODELS="$WITH_MODELS" MACU_INSTALL_TALKING_HEAD="$WITH_TALKING_HEAD" ./deploy/fetch-models.sh

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
  "${MACU_PYTHON:-python3}" -m venv "$REPO/.whisper-venv"
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

# The AWESOME poster as terminal art (color if the terminal supports it, else the
# plain block fallback) + Mayor Awesome's sign-off — then the next-steps LAST, so the
# actionable instructions are the final thing on screen.
echo
if [ -t 1 ] && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ] && [ -f "$REPO/deploy/assets/awesome.ans" ]; then
  cat "$REPO/deploy/assets/awesome.ans"
elif [ -f "$REPO/deploy/assets/awesome.txt" ]; then
  cat "$REPO/deploy/assets/awesome.txt"
fi
echo
echo "Mayor Awesome thanks you for installing MACU Studio. You are entitled to one free"
echo "air guitar redeemable at your local library."

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
