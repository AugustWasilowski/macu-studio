# MACU GPU services (OmniVoice · Ollama · ComfyUI)

The three local GPU services MACU Studio + the render pipeline depend on, as
compose stacks **in the repo**. Bringing one up on a new machine is
`docker compose up -d` from the service's dir — no hand-reconstruction.

| Service | Image | Lifecycle | Port (loopback) | Data |
|---|---|---|---|---|
| **omnivoice** | `ghcr.io/debpalash/omnivoice-studio` (+ 2 in-repo patches) | on-demand (backend/pipeline start/stop) | 3900 | `${MACU_DATA_ROOT}/omnivoice/{state,data,hf-cache}` |
| **ollama** | `ollama/ollama` | on-demand | 11434 | `${MACU_DATA_ROOT}/ollama` |
| **comfyui** | local build (`Dockerfile` here) | long-lived | 8188 | `${MACU_DATA_ROOT}/comfyui/{ComfyUI,models,output,input,user,custom_nodes}` |

## Config

Volume roots come from `${MACU_DATA_ROOT}` (default `/mnt/storage`), so these work
with the default paths and are retargetable elsewhere. Copy `.env.example` →
`.env` and set `MACU_DATA_ROOT` on a new machine, then pass it to compose:

```bash
docker compose --env-file ../.env -f omnivoice/docker-compose.yml up -d
# or: export MACU_DATA_ROOT=/your/data && docker compose -f omnivoice/docker-compose.yml up -d
```

## Bring-up (per service)

- **ollama:** `docker compose -f ollama/docker-compose.yml up -d` then
  `docker exec ollama ollama pull qwen2.5:7b-instruct-q4_K_M`. (Stays stopped
  between jobs; the backend starts it on demand.)
- **omnivoice:** `docker compose -f omnivoice/docker-compose.yml up -d`. Base model
  downloads into the `hf-cache` volume on first inference. (On-demand; backend
  starts it.) Voice profiles live in the `data` volume — see the model/asset
  fetch step for importing the existing MACU voices.
- **comfyui:** needs its source + models first (see below), then
  `docker compose -f comfyui/docker-compose.yml build && … up -d`.

### ComfyUI first-run (the model/asset fetch step does this)

Under `${MACU_DATA_ROOT}/comfyui/`:
```
git clone https://github.com/Comfy-Org/ComfyUI.git ComfyUI
git clone <ModelScopeT2V node> custom_nodes/ComfyUI_ModelScopeT2V
mkdir -p models output input user
# download into models/text2video/:
#   text2video_pytorch_model.pth   (zeroscope_v2_576w — the un-watermarked default)
#   VQGAN_autoencoder.pth
#   text2video_pytorch_model.damo.pth + configuration.json  (DAMO rollback, watermarked)
```

> These ~8 GB of weights are NOT in git — the installer's **model-fetch** step pulls
> them (zeroscope from HF, DAMO from ModelScope). The compose here only defines the
> runtime; data is fetched separately.

## Prereqs (the installer's `doctor` step checks these)

NVIDIA driver + **nvidia-container-toolkit**, Docker, and enough VRAM (the defaults
target an ~11 GB GPU, e.g. an RTX 2080 Ti). Install these first on a new machine.
