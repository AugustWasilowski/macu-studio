#!/usr/bin/env bash
# MACU Studio uninstaller — reverses what ./deploy/install.sh (and the optional
# sudo ./deploy/install-systemd.sh) set up on this machine.
#
#   ./deploy/uninstall.sh [options]
#
#   -y, --yes        skip the confirm prompt
#   --purge-data     ALSO delete the data root (downloaded models AND YOUR SHOWS,
#                    voices, renders). Off by default — uninstalling the app never
#                    touches your work unless you ask.
#   --keep-images    keep the Docker images (multi-GB) so a reinstall is fast
#   --dry-run        print what would be done without doing any of it
#
# What it does, in order:
#   1. stop Studio + render (systemd units if installed, else the venv processes)
#   2. remove the macu-render/macu-studio systemd units + their logs (needs sudo)
#   3. docker compose down the four services (ollama, omnivoice, comfyui, piper),
#      removing their containers — and images too unless --keep-images
#   4. remove the repo-local build artifacts: studio/.venv, .whisper-venv,
#      studio/frontend/{node_modules,dist}
#   5. (only with --purge-data) delete $MACU_DATA_ROOT
#
# What it deliberately leaves alone:
#   • your data root (shows/voices/models) unless --purge-data
#   • .env / deploy/services/.env (they describe where your data lives)
#   • system prerequisites installed by install-prereqs.sh (docker, node/nvm,
#     python, ttyd, tmux) — they're general-purpose, remove via your package manager
#   • this repo checkout itself — `rm -rf` it yourself as the final step
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO"

AUTO=0; PURGE=0; KEEP_IMAGES=0; DRY=0
for a in "$@"; do case "$a" in
  -y|--yes)      AUTO=1 ;;
  --purge-data)  PURGE=1 ;;
  --keep-images) KEEP_IMAGES=1 ;;
  --dry-run)     DRY=1 ;;
  -h|--help)     sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $a (try --help)"; exit 1 ;;
esac; done

set -a; [ -f .env ] && . ./.env; [ -f deploy/services/.env ] && . ./deploy/services/.env; set +a
DATA_ROOT="${MACU_DATA_ROOT:-$REPO/data}"

# Every mutating step funnels through this so --dry-run is a faithful preview.
run(){
  if [ "$DRY" = 1 ]; then echo "  [dry-run] $*"; else "$@"; fi
}

echo
echo "   MACU Studio uninstaller — repo: $REPO"
echo
echo "   Will remove: services (docker + systemd), venvs, frontend build"
if [ "$KEEP_IMAGES" = 1 ]; then echo "   Keeping:     docker images (--keep-images)"; fi
if [ "$PURGE" = 1 ]; then
  echo "   PURGE:       $DATA_ROOT  — models AND your shows/voices/renders. Gone."
else
  echo "   Keeping:     your data at $DATA_ROOT (use --purge-data to delete it)"
fi
if [ "$DRY" = 1 ]; then echo "   DRY RUN:     nothing will actually be changed"; fi
echo

if [ "$AUTO" = 0 ] && [ "$DRY" = 0 ]; then
  if [ -t 0 ]; then
    read -r -p "   Continue? [y/N] " ans
    case "$ans" in [yY]|[yY][eE][sS]) ;; *) echo "   Aborted."; exit 1 ;; esac
  else
    echo "   Non-interactive shell — re-run with -y to proceed."; exit 1
  fi
fi

# Purging anything OTHER than the default repo-local ./data needs the path typed
# back, even with -y: on shared-storage installs MACU_DATA_ROOT can point at a
# drive holding far more than MACU (e.g. /mnt/storage), and one flag must never
# be able to take that out.
if [ "$PURGE" = 1 ] && [ "$DRY" = 0 ] && [ "$DATA_ROOT" != "$REPO/data" ]; then
  echo
  echo "   The data root is NOT the repo-local default — it may hold non-MACU data."
  if [ -t 0 ]; then
    read -r -p "   Type the full path to confirm deleting it: " typed
    if [ "$typed" != "$DATA_ROOT" ]; then echo "   Mismatch — skipping the purge."; PURGE=0; fi
  else
    echo "   Non-interactive — refusing to purge a custom data root. Delete it by hand."; PURGE=0
  fi
fi

echo; echo ">>> [1/5] stop Studio + render"
# systemd path (server installs) …
for unit in macu-studio macu-render; do
  if [ -f "/etc/systemd/system/$unit.service" ]; then
    run sudo systemctl disable --now "$unit" || true
  fi
done
# … and the foreground path (start-studio.sh): anything running out of the venv.
# Match the physical path too — running processes see through repo symlinks.
REPO_REAL="$(cd "$REPO" && pwd -P)"
for p in "$REPO/studio/.venv" "$REPO_REAL/studio/.venv"; do
  if pgrep -f "$p" >/dev/null 2>&1; then
    run pkill -f "$p" || true
  fi
done

echo; echo ">>> [2/5] remove systemd units + logs"
units_found=0
for unit in macu-studio macu-render; do
  if [ -f "/etc/systemd/system/$unit.service" ]; then units_found=1; fi
done
if [ "$units_found" = 1 ]; then
  run sudo rm -f /etc/systemd/system/macu-studio.service /etc/systemd/system/macu-render.service
  run sudo systemctl daemon-reload
  run sudo rm -f /var/log/macu-studio.log /var/log/macu-render.log
else
  echo "  no systemd units installed — skipping"
fi

echo; echo ">>> [3/5] remove service containers (ollama, omnivoice, comfyui, piper)"
if command -v docker >/dev/null 2>&1; then
  down_args=(down --remove-orphans)
  if [ "$KEEP_IMAGES" = 0 ]; then down_args+=(--rmi all); fi
  for svc in ollama omnivoice comfyui piper; do
    f="deploy/services/$svc/docker-compose.yml"
    [ -f "$f" ] || continue
    # MACU_DATA_ROOT keeps compose's bind-mount interpolation happy; all mounts
    # are binds (no named volumes), so `down` never deletes data.
    run env MACU_DATA_ROOT="$DATA_ROOT" docker compose -f "$f" "${down_args[@]}" || true
  done
else
  echo "  docker not found — skipping"
fi

echo; echo ">>> [4/5] remove venvs + build artifacts"
for d in studio/.venv .whisper-venv studio/frontend/node_modules studio/frontend/dist; do
  if [ -e "$REPO/$d" ]; then run rm -rf "${REPO:?}/$d"; else echo "  $d already absent"; fi
done

echo; echo ">>> [5/5] data"
if [ "$PURGE" = 1 ]; then
  if [ -d "$DATA_ROOT" ]; then run rm -rf "${DATA_ROOT:?}"; else echo "  $DATA_ROOT already absent"; fi
else
  echo "  kept: $DATA_ROOT  (shows, voices, models — delete with --purge-data or by hand)"
fi

cat <<EOF

######## uninstall complete ########
Still on this machine (on purpose):

  • this repo checkout — finish with:  rm -rf $REPO
  • system tools from install-prereqs.sh (docker, node/nvm, python, ttyd, tmux)
    — shared with other software; remove via your package manager if unwanted
$( [ "$PURGE" = 0 ] && echo "  • your data at $DATA_ROOT" )
  • if you ran /setup-macu-channel in Claude Code, remove the channel from your
    Claude Code settings by hand

Mayor Awesome is sorry to see you go. The air guitar is non-refundable.
EOF
