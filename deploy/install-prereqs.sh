#!/usr/bin/env bash
# Best-effort installer for the host prerequisites doctor.sh checks. Handles the apt
# (Debian/Ubuntu/WSL) path; on other distros it prints what to install by hand. It's
# idempotent — skips anything already satisfied — and uses sudo for system packages.
#
# The top-level installer offers to run this when preflight fails; you can also run it
# directly:  ./deploy/install-prereqs.sh
# NOTE: no `set -u` — sourcing nvm.sh references unbound vars and would abort under it.
set -o pipefail

have() { command -v "$1" >/dev/null 2>&1; }
say()  { printf '\n>>> %s\n' "$1"; }

py_ge_311() { "$1" -c 'import sys;exit(0 if sys.version_info[:2]>=(3,11) else 1)' 2>/dev/null; }
have_py311() { for c in python3.13 python3.12 python3.11 python3; do have "$c" && py_ge_311 "$c" && return 0; done; return 1; }
have_node20() {
  if have node && [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)" -ge 20 ] 2>/dev/null; then return 0; fi
  ls -d "$HOME"/.nvm/versions/node/v2*/bin/node >/dev/null 2>&1
}

if ! have apt-get; then
  echo "This auto-installer only handles apt (Debian/Ubuntu/WSL). Install by hand:"
  echo "  ffmpeg, python>=3.11 (+venv), node>=20, and the nvidia-container-toolkit."
  exit 1
fi

# --- ffmpeg -----------------------------------------------------------------
if ! have ffmpeg; then
  say "installing ffmpeg"
  sudo apt-get update -qq && sudo apt-get install -y ffmpeg
fi

# --- python >= 3.11 (deadsnakes on Ubuntu) ----------------------------------
if ! have_py311; then
  say "installing python 3.12 (system python is <3.11)"
  sudo apt-get install -y software-properties-common
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt-get update -qq
  sudo apt-get install -y python3.12 python3.12-venv || \
    echo "  couldn't install python3.12 (deadsnakes is Ubuntu-only) — install python>=3.11 by hand."
fi

# --- node >= 20 (nvm, user-local, no sudo) ----------------------------------
if ! have_node20; then
  say "installing Node 20 (via nvm, user-local)"
  if [ ! -s "$HOME/.nvm/nvm.sh" ]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  fi
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh"
  nvm install 20 && nvm alias default 20
  if ls -d "$HOME"/.nvm/versions/node/v2*/bin/node >/dev/null 2>&1; then
    echo "  node 20 installed under ~/.nvm (the build picks the newest node automatically)."
  else
    echo "  >> nvm install 20 didn't land — check network, then run: nvm install 20"
  fi
fi

# --- nvidia-container-toolkit (GPU services) — best effort ------------------
if have docker && have nvidia-smi && ! (docker info 2>/dev/null | grep -qiE 'Runtimes:.*nvidia'); then
  say "installing nvidia-container-toolkit (GPU services need it)"
  if curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
       | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg; then
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
      | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
      | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
    sudo apt-get update -qq && sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker || true
    if ! sudo systemctl restart docker 2>/dev/null; then
      echo "  >> couldn't restart docker automatically — if you run Docker Desktop (common on WSL),"
      echo "     restart it yourself so the nvidia runtime loads, then re-run ./deploy/install.sh"
    fi
  else
    echo "  couldn't add the NVIDIA toolkit apt repo — install nvidia-container-toolkit by hand."
  fi
fi

say "prerequisite pass complete — the installer re-checks with doctor.sh next."
