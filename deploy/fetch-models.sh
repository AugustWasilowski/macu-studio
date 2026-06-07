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
set -a; [ -f "$REPO/.env" ] && . "$REPO/.env"; set +a
: "${MACU_DATA_ROOT:=/mnt/storage}"
: "${MACU_SHARES:=/mnt/storage/shares/MACU}"
: "${MACU_ASSETS:=$MACU_SHARES/assets}"

COMFY="$MACU_DATA_ROOT/comfyui"
T2V="$COMFY/models/text2video"
say(){ printf '\n=== %s ===\n' "$1"; }

# --- ComfyUI source + custom node --------------------------------------------
say "ComfyUI source + ModelScopeT2V node"
mkdir -p "$COMFY"/{models,output,input,user,custom_nodes}
if [ ! -d "$COMFY/ComfyUI/.git" ]; then
  git clone --depth 1 https://github.com/Comfy-Org/ComfyUI.git "$COMFY/ComfyUI"
else echo "ComfyUI already cloned — skip (git pull to update)"; fi
NODE="$COMFY/custom_nodes/ComfyUI_ModelScopeT2V"
if [ ! -d "$NODE/.git" ]; then
  git clone --depth 1 https://github.com/ExponentialML/ComfyUI_ModelScopeT2V.git "$NODE"
else echo "ModelScopeT2V node already present — skip"; fi

# --- text2video + clip weights (HuggingFace) ---------------------------------
say "text2video + clip weights (~5.4 GB; skips files already present)"
MODELS="$COMFY/models"
mkdir -p "$MODELS/text2video" "$MODELS/clip"
python3 - "$MODELS" <<'PY'
import os, sys, subprocess
models = sys.argv[1]
T2V = os.path.join(models, "text2video")
CLIP = os.path.join(models, "clip")
try:
    from huggingface_hub import hf_hub_download
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "--user", "huggingface_hub"])
    from huggingface_hub import hf_hub_download

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
for repo, fname, dst, final in WANT:
    out = os.path.join(dst, final)
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print(f"  have {final} — skip"); continue
    print(f"  downloading {final}  <-  {repo}/{fname}")
    p = hf_hub_download(repo_id=repo, filename=fname, local_dir=dst)
    if os.path.abspath(p) != os.path.abspath(out):
        os.replace(p, out)
print("text2video + clip weights ready")
PY

# --- Ollama shot-gen model ----------------------------------------------------
say "Ollama model (qwen2.5:7b-instruct-q4_K_M)"
OLLAMA_COMPOSE="$REPO/deploy/services/ollama/docker-compose.yml"
MACU_DATA_ROOT="$MACU_DATA_ROOT" docker compose -f "$OLLAMA_COMPOSE" up -d
for i in $(seq 1 30); do docker exec ollama ollama list >/dev/null 2>&1 && break; sleep 2; done
docker exec ollama ollama pull qwen2.5:7b-instruct-q4_K_M
echo "(ollama left running — the Studio backend manages start/stop on demand; 'docker stop ollama' to free VRAM)"

# --- Subtitle font ------------------------------------------------------------
say "Subtitle font (BetterVCR.ttf)"
mkdir -p "$MACU_ASSETS/fonts"
if [ ! -f "$MACU_ASSETS/fonts/BetterVCR.ttf" ]; then
  cp "$REPO/deploy/assets/fonts/BetterVCR.ttf" "$MACU_ASSETS/fonts/"
  echo "installed BetterVCR.ttf -> $MACU_ASSETS/fonts/"
else echo "BetterVCR.ttf already present — skip"; fi

say "Done. Next: docker compose -f deploy/services/comfyui/docker-compose.yml build && up -d"
