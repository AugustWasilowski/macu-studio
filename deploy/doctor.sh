#!/usr/bin/env bash
# MACU installer preflight. CHECKS the host for everything the Studio app + the
# GPU services need; it does NOT install Docker/CUDA/etc. (too OS-specific to do
# safely, esp. on WSL) — it tells you what's missing and where to get it.
#
# Exit 0 if all REQUIRED checks pass, 1 otherwise. Optional checks only warn.
set -u

ok=0; miss=0
green=$'\033[32m'; red=$'\033[31m'; yellow=$'\033[33m'; dim=$'\033[2m'; rst=$'\033[0m'
PASS(){ printf "  ${green}✓${rst} %-22s %s\n" "$1" "${2:-}"; ok=$((ok+1)); }
FAIL(){ printf "  ${red}✗${rst} %-22s %s\n" "$1" "${yellow}${2:-}${rst}"; miss=$((miss+1)); }
WARN(){ printf "  ${yellow}!${rst} %-22s %s\n" "$1" "${dim}${2:-}${rst}"; }
have(){ command -v "$1" >/dev/null 2>&1; }
is_wsl(){ grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; }
docker_usable=0   # set to 1 once `docker info` succeeds (gates the services section)

echo "MACU preflight — checking host prerequisites"
echo

echo "Core:"
have git     && PASS git     "$(git --version 2>/dev/null)"                  || FAIL git     "install git"
have ffmpeg  && PASS ffmpeg  "$(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)" || FAIL ffmpeg  "install ffmpeg"
# python may be the system python3, or a versioned python3.11+ (e.g. deadsnakes).
py_bin=""
for c in python3 python3.13 python3.12 python3.11; do
  if have "$c" && "$c" -c 'import sys;exit(0 if sys.version_info[:2]>=(3,11) else 1)' 2>/dev/null; then py_bin="$c"; break; fi
done
if [ -n "$py_bin" ]; then
  PASS python3 "$("$py_bin" -V 2>&1 | cut -d' ' -f2)$([ "$py_bin" != python3 ] && echo " ($py_bin)")"
else
  pv=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
  FAIL python3 "need >=3.11 (have ${pv:-?}) — the installer can add it (deadsnakes)"
fi
# Pick the BEST node across PATH + every nvm install: highest FULL version with a
# WORKING npm. A too-old system node (apt node 16) must not hide an nvm node 20, and
# a half-removed npm (dangling symlink, no npm-cli.js — happens with two same-major
# nvm installs) must not pass as healthy: the frontend build needs npm, so this is
# the same selection studio/scripts/install.sh uses.
node_bin=""; node_major=0; best_key=0; node_seen=0
for cand in "$(command -v node 2>/dev/null)" $(ls -d "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null); do
  [ -x "$cand" ] || continue
  ver=$("$cand" -p 'process.versions.node' 2>/dev/null) || continue
  node_seen=1
  maj=${ver%%.*}; rest=${ver#*.}; min=${rest%%.*}; pat=${rest#*.}; pat=${pat%%[-+]*}
  [ "${maj:-0}" -ge 20 ] 2>/dev/null || continue
  dir="$(dirname "$cand")"
  [ -f "$dir/../lib/node_modules/npm/bin/npm-cli.js" ] || continue   # npm must be runnable
  key=$(( maj * 1000000 + ${min:-0} * 1000 + ${pat:-0} ))
  if [ "$key" -gt "$best_key" ]; then best_key=$key; node_bin="$cand"; node_major=$maj; fi
done
if [ -n "$node_bin" ]; then
  PASS node "v$("$node_bin" -v 2>/dev/null|tr -d v)$([ "$node_bin" != "$(command -v node 2>/dev/null)" ] && echo ' (nvm)')"
elif [ "$node_seen" -eq 1 ]; then
  FAIL node "found node but none is >=20 with a working npm — repair with 'nvm install --lts'"
else
  FAIL node "need >=20 (Studio frontend build) — the installer can add it (nvm)"
fi

echo
echo "Docker + GPU:"
if have docker; then
  if docker info >/dev/null 2>&1; then
    docker_usable=1
    PASS docker "$(docker --version 2>/dev/null | cut -d, -f1)"
    # Compose v2 (the `docker compose` subcommand) — the installer uses it everywhere.
    # The old standalone v1 `docker-compose` is NOT a substitute and will break mid-build.
    if docker compose version >/dev/null 2>&1; then
      PASS docker-compose "v$(docker compose version --short 2>/dev/null)"
    else
      FAIL docker-compose "need Compose v2 — install the docker-compose-plugin (the old standalone 'docker-compose' won't work)"
    fi
    # nvidia runtime available?
    if docker info 2>/dev/null | grep -qiE 'Runtimes:.*nvidia' \
       || docker info 2>/dev/null | grep -qi 'nvidia'; then
      PASS nvidia-runtime "container toolkit present"
    else
      FAIL nvidia-runtime "install nvidia-container-toolkit (GPU services need it)"
    fi
  else
    # Separate "you lack permission" from "the daemon is down" — the fix is different.
    if docker info 2>&1 | grep -qiE 'permission denied|dial unix.*docker.sock'; then
      FAIL docker "no permission for the Docker socket — run:  sudo usermod -aG docker $(id -un)  then log out and back in"
    elif is_wsl; then
      FAIL docker "daemon unreachable in this WSL distro — Docker Desktop → Settings → Resources → WSL Integration → enable this distro → Apply & Restart, then 'wsl --shutdown' and reopen. A distro move can also wipe the image store (see the services section)."
    else
      FAIL docker "daemon unreachable — start Docker (Docker Desktop, or 'sudo systemctl start docker')"
    fi
  fi
else FAIL docker "install Docker Engine"; fi

if have nvidia-smi; then
  gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)
  PASS nvidia-driver "$gpu"
  # The text-to-video stage is the VRAM hog; the tested floor is ~11 GB (RTX 2080 Ti).
  vram_mib=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
  if [ -n "$vram_mib" ] && [ "$vram_mib" -lt 11000 ] 2>/dev/null; then
    WARN gpu-vram "$((vram_mib/1024)) GB — 11-12 GB recommended; the video (T2V) stage may OOM below ~11 GB (see README → System requirements)"
  fi
else FAIL nvidia-driver "no nvidia-smi — install the NVIDIA driver (an NVIDIA GPU is required)"; fi

echo
echo "GPU services (on-demand — OmniVoice voices, Ollama shot-gen):"
# The on-demand `docker start omnivoice` (stage 1 VO) needs BOTH the image pulled
# AND a created container. A WSL distro move can wipe Docker Desktop's image store
# and orphan the container, so a fresh-looking install silently can't render voice
# (the Leo class of bug). Re-runnable: this only inspects state, fixes nothing.
svc_check(){ # label  image-repo(no tag/digest)  container-name
  local label="$1" image="$2" cont="$3"
  local img=0 con=0
  docker image ls --format '{{.Repository}}' 2>/dev/null | grep -qx "$image" && img=1
  docker container inspect "$cont" >/dev/null 2>&1 && con=1
  if [ "$img" = 1 ] && [ "$con" = 1 ]; then
    PASS "$label" "image + container ($(docker container inspect -f '{{.State.Status}}' "$cont" 2>/dev/null))"
  elif [ "$img" = 1 ]; then
    WARN "$label" "image present, no '$cont' container — create it: docker compose -f deploy/services/$label/docker-compose.yml create"
  else
    WARN "$label" "image not pulled — re-run installer step [3/6], or: docker compose -f deploy/services/$label/docker-compose.yml pull && ... create"
  fi
}
if [ "$docker_usable" = 1 ]; then
  svc_check omnivoice ghcr.io/debpalash/omnivoice-studio omnivoice
  svc_check ollama    ollama/ollama                       ollama
  # credsStore that Linux can't exec → public pulls fail (the installer now bypasses
  # it, but flag it so a manual `docker compose pull` failure isn't a mystery).
  if is_wsl && grep -qiE '"credsStore"\s*:\s*"desktop' "$HOME/.docker/config.json" 2>/dev/null; then
    WARN docker-creds "~/.docker/config.json uses the Windows 'desktop' cred helper — anonymous public pulls need 'DOCKER_CONFIG=<empty> docker compose pull' (the installer does this automatically)"
  fi
else
  WARN services "skipped — Docker isn't usable; fix the docker ✗ above, then re-run ./deploy/doctor.sh"
fi

echo
echo "Render pipeline (local frame interpolation — stage 3):"
# stage_3_rife shells out to these on PATH. The docker image bundles them; a
# bare-metal install must provide them or stage 3 dies after a long masters render
# (SSA-126). install-prereqs.sh can install both on apt hosts.
have anim_dump && PASS anim_dump "webp frame dump (libwebp)" \
  || FAIL anim_dump "stage 3 needs it — apt: 'sudo apt-get install webp' (or ./deploy/install-prereqs.sh)"
have rife-ncnn-vulkan && PASS rife-ncnn-vulkan "Vulkan frame interpolation" \
  || FAIL rife-ncnn-vulkan "stage 3 needs it — prebuilt from github.com/nihui/rife-ncnn-vulkan (or ./deploy/install-prereqs.sh)"

echo
echo "Coupling (optional — for the Studio↔Claude chat tile / writers' room + TERMINAL drawer):"
# Per-distro install hint for the optional terminal deps.
if   have apt-get; then pkg_hint="sudo apt-get install ttyd tmux"
elif have dnf;     then pkg_hint="sudo dnf install ttyd tmux"
elif have pacman;  then pkg_hint="sudo pacman -S ttyd tmux"
elif have brew;    then pkg_hint="brew install ttyd tmux"
else                    pkg_hint="install ttyd + tmux with your package manager"; fi
have claude && PASS claude-code "$(claude --version 2>/dev/null | head -1)" \
  || WARN claude-code "not found — the chat tile / writers' room need Claude Code + the channel skill"
have ttyd && PASS ttyd "$(ttyd --version 2>&1 | head -1)" \
  || WARN ttyd "not found — the Studio TERMINAL drawer needs it ($pkg_hint)"
have tmux && PASS tmux "$(tmux -V 2>/dev/null)" \
  || WARN tmux "not found — the TERMINAL drawer's persistent session needs it ($pkg_hint)"

echo
if [ "$miss" -eq 0 ]; then
  printf "${green}All required checks passed${rst} (%d ok). Next: bring up the services in deploy/services/, fetch models, then studio/scripts/install.sh\n" "$ok"
  exit 0
else
  printf "${red}%d required item(s) missing${rst}, %d ok. Install the ✗ items above, then re-run.\n" "$miss" "$ok"
  exit 1
fi
