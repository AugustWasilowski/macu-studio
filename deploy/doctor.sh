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
    PASS docker "$(docker --version 2>/dev/null | cut -d, -f1)"
    # nvidia runtime available?
    if docker info 2>/dev/null | grep -qiE 'Runtimes:.*nvidia' \
       || docker info 2>/dev/null | grep -qi 'nvidia'; then
      PASS nvidia-runtime "container toolkit present"
    else
      FAIL nvidia-runtime "install nvidia-container-toolkit (GPU services need it)"
    fi
  else
    FAIL docker "installed but daemon unreachable (start Docker / add user to docker group)"
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
