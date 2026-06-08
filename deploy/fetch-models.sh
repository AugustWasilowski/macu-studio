#!/usr/bin/env bash
# Fetch the PUBLIC models + assets MACU needs, from public sources only (no
# personal data). Idempotent — skips anything already present. Run after the GPU
# services exist (deploy/services/) and before the first render.
#
# Pulls:
#   - ComfyUI source            -> $MACU_DATA_ROOT/comfyui/ComfyUI            (Comfy-Org/ComfyUI)
#   - ModelScopeT2V custom node -> $MACU_DATA_ROOT/comfyui/custom_nodes/...   (ExponentialML)
#   - text2video weights (~5.4 GB) -> $MACU_DATA_ROOT/comfyui/models/
#       text2video/text2video_pytorch_model.pth = zeroscope_v2_576w (un-watermarked unet)
#       text2video/VQGAN_autoencoder.pth, text2video/configuration.json (DAMO VAE + config)
#       clip/open_clip_pytorch_model.bin (text encoder; config's ckpt_clip)
#   - Ollama shot-gen model     -> qwen2.5:7b-instruct-q4_K_M (into the ollama volume)
#   - Subtitle font             -> $MACU_ASSETS/fonts/BetterVCR.ttf (bundled in repo)
#
# Personal data (cloned VOICES + music/sfx kits) is NOT fetched here — clone your
# own voices in the app's Create Voice panel.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
set -a; [ -f "$REPO/.env" ] && . "$REPO/.env"
# MACU_DATA_ROOT lives in deploy/services/.env (not the repo-root .env) — source it
# too so a standalone run of this script lands models on the right disk.
[ -f "$REPO/deploy/services/.env" ] && . "$REPO/deploy/services/.env"; set +a
: "${MACU_DATA_ROOT:=/mnt/storage}"
: "${MACU_SHARES:=/mnt/storage/shares/MACU}"
: "${MACU_ASSETS:=$MACU_SHARES/assets}"

# Resolve a python that has huggingface_hub. PEP-668 (Ubuntu 24.04 / WSL) rejects
# `pip install --user` against the system interpreter, so use a dedicated venv.
PYHF="python3"
if ! python3 -c 'import huggingface_hub' 2>/dev/null; then
  echo "provisioning a fetch venv (huggingface_hub) at $REPO/.fetch-venv ..."
  "${MACU_PYTHON:-python3}" -m venv "$REPO/.fetch-venv"
  "$REPO/.fetch-venv/bin/pip" install --quiet --upgrade pip huggingface_hub
  PYHF="$REPO/.fetch-venv/bin/python"
fi

COMFY="$MACU_DATA_ROOT/comfyui"
T2V="$COMFY/models/text2video"
say(){ printf '\n=== %s ===\n' "$1"; }

# Retry a flaky network command up to 3 times with a growing backoff. Downloads are
# the #1 thing that breaks an install on hotel/home WiFi — don't fail the whole run
# on a single transient hiccup.
retry(){
  local n=0
  until "$@"; do
    n=$((n+1))
    [ "$n" -ge 3 ] && { echo "  still failing after 3 tries: $*" >&2; return 1; }
    echo "  network hiccup — retry $n/3 in $((n*5))s ..." >&2
    sleep $((n*5))
  done
}

# --- ComfyUI source + custom node --------------------------------------------
say "ComfyUI source + ModelScopeT2V node"
mkdir -p "$COMFY"/{models,output,input,user,custom_nodes}
if [ ! -d "$COMFY/ComfyUI/.git" ]; then
  rm -rf "$COMFY/ComfyUI"  # clear any partial clone from an interrupted run
  retry git clone --depth 1 https://github.com/Comfy-Org/ComfyUI.git "$COMFY/ComfyUI"
else echo "ComfyUI already cloned — skip (git pull to update)"; fi
NODE="$COMFY/custom_nodes/ComfyUI_ModelScopeT2V"
if [ ! -d "$NODE/.git" ]; then
  rm -rf "$NODE"  # clear any partial clone from an interrupted run
  retry git clone --depth 1 https://github.com/ExponentialML/ComfyUI_ModelScopeT2V.git "$NODE"
else echo "ModelScopeT2V node already present — skip"; fi

# --- text2video + clip weights (HuggingFace) ---------------------------------
say "text2video + clip weights (~5.4 GB; skips files already present)"
MODELS="$COMFY/models"
mkdir -p "$MODELS/text2video" "$MODELS/clip"
"$PYHF" - "$MODELS" <<'PY'
import os, sys, shutil
from huggingface_hub import hf_hub_download, hf_hub_url, get_hf_file_metadata
models = sys.argv[1]
T2V = os.path.join(models, "text2video")
CLIP = os.path.join(models, "clip")

# zeroscope's unet lives in a zs2_576w/ subfolder; the DAMO VAE + config + the CLIP
# text encoder come from the ali-vilab ModelScope mirror. (repo, file, dest, name)
ZS = "cerspense/zeroscope_v2_576w"
DAMO = "ali-vilab/modelscope-damo-text-to-video-synthesis"
WANT = [
    (ZS,   "zs2_576w/text2video_pytorch_model.pth", T2V,  "text2video_pytorch_model.pth"),
    (DAMO, "VQGAN_autoencoder.pth",                 T2V,  "VQGAN_autoencoder.pth"),
    (DAMO, "configuration.json",                    T2V,  "configuration.json"),
    (DAMO, "open_clip_pytorch_model.bin",           CLIP, "open_clip_pytorch_model.bin"),
]

def human(n):
    return f"{n/1e9:.2f} GB" if n and n >= 1e9 else (f"{n/1e6:.0f} MB" if n else "?")

def expected_size(repo, fname):
    """Authoritative size from HF metadata, so a truncated download can't pass a
    weak >1KB check forever. Returns None if the lookup fails (offline mirror, etc.)."""
    try:
        return get_hf_file_metadata(hf_hub_url(repo_id=repo, filename=fname)).size
    except Exception:
        return None

for repo, fname, dst, final in WANT:
    out = os.path.join(dst, final)
    want = expected_size(repo, fname)
    if os.path.exists(out):
        have = os.path.getsize(out)
        # Match the known size when we have it; else fall back to a sanity floor.
        if (want and have == want) or (not want and have > 1000):
            print(f"  have {final} ({human(have)}) — skip"); continue
        print(f"  {final} is {human(have)} but expected {human(want)} — re-fetching")
        os.remove(out)
    print(f"  downloading {final} ({human(want)})  <-  {repo}/{fname}")
    try:
        p = hf_hub_download(repo_id=repo, filename=fname, local_dir=dst)
        if os.path.abspath(p) != os.path.abspath(out):
            # Stage next to the final name, then atomically swap in — so an interrupted
            # cross-filesystem move never leaves a half-written file at `out`.
            tmp = out + ".part"
            shutil.move(p, tmp)
            os.replace(tmp, out)
    except BaseException:
        for stray in (out, out + ".part"):
            try: os.remove(stray)
            except OSError: pass
        raise
print("text2video + clip weights ready")
PY

# --- Ollama shot-gen model ----------------------------------------------------
say "Ollama model (qwen2.5:7b-instruct-q4_K_M)"
OLLAMA_COMPOSE="$REPO/deploy/services/ollama/docker-compose.yml"
MACU_DATA_ROOT="$MACU_DATA_ROOT" retry docker compose -f "$OLLAMA_COMPOSE" up -d
ready=0
for i in $(seq 1 30); do docker exec ollama ollama list >/dev/null 2>&1 && { ready=1; break; }; sleep 2; done
if [ "$ready" -ne 1 ]; then
  echo "ERROR: ollama container didn't become ready in 60s. Check 'docker logs ollama'." >&2
  exit 1
fi
retry docker exec ollama ollama pull qwen2.5:7b-instruct-q4_K_M
echo "(ollama left running — the Studio backend manages start/stop on demand; 'docker stop ollama' to free VRAM)"

# --- Subtitle font ------------------------------------------------------------
say "Subtitle font (BetterVCR.ttf)"
mkdir -p "$MACU_ASSETS/fonts"
if [ ! -f "$MACU_ASSETS/fonts/BetterVCR.ttf" ]; then
  cp "$REPO/deploy/assets/fonts/BetterVCR.ttf" "$MACU_ASSETS/fonts/"
  echo "installed BetterVCR.ttf -> $MACU_ASSETS/fonts/"
else echo "BetterVCR.ttf already present — skip"; fi

say "Done. Next: docker compose -f deploy/services/comfyui/docker-compose.yml build && up -d"
