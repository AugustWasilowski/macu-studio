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
if have python3; then
  pv=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
  python3 -c 'import sys;exit(0 if sys.version_info[:2]>=(3,11) else 1)' 2>/dev/null \
    && PASS python3 "$pv" || FAIL python3 "need >=3.11 (have ${pv:-?})"
else FAIL python3 "install python >=3.11"; fi
# node may be nvm-managed (not on the bare PATH) — check PATH then ~/.nvm.
node_bin=""
if have node; then node_bin="$(command -v node)"
elif [ -d "$HOME/.nvm/versions/node" ]; then
  node_bin="$(ls -d "$HOME"/.nvm/versions/node/*/bin/node 2>/dev/null | sort -V | tail -1)"
fi
if [ -n "$node_bin" ]; then
  nv=$("$node_bin" -p 'process.versions.node.split(".")[0]' 2>/dev/null)
  [ "${nv:-0}" -ge 20 ] 2>/dev/null && PASS node "v$("$node_bin" -v 2>/dev/null|tr -d v)$([ "$node_bin" != "$(command -v node 2>/dev/null)" ] && echo ' (nvm)')" \
    || FAIL node "need >=20 (Studio frontend build; have ${nv:-?})"
else FAIL node "install Node 20+ (nvm recommended)"; fi

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
else FAIL nvidia-driver "no nvidia-smi — install the NVIDIA driver (an NVIDIA GPU is required)"; fi

echo
echo "Coupling (optional — for the Studio↔Claude chat tile / writers' room):"
have claude && PASS claude-code "$(claude --version 2>/dev/null | head -1)" \
  || WARN claude-code "not found — the chat tile / writers' room need Claude Code + the channel skill"

echo
if [ "$miss" -eq 0 ]; then
  printf "${green}All required checks passed${rst} (%d ok). Next: bring up the services in deploy/services/, fetch models, then studio/scripts/install.sh\n" "$ok"
  exit 0
else
  printf "${red}%d required item(s) missing${rst}, %d ok. Install the ✗ items above, then re-run.\n" "$miss" "$ok"
  exit 1
fi
