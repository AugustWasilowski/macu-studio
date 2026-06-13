# MACU local services (OmniVoice · Ollama · ComfyUI · Piper)

The local services MACU Studio + the render pipeline depend on, as compose stacks
**in the repo**. Bringing one up on a new machine is `docker compose up -d` from
the service's dir — no hand-reconstruction.

| Service | Image | Lifecycle | Port (loopback) | Data |
|---|---|---|---|---|
| **omnivoice** | `ghcr.io/debpalash/omnivoice-studio` (+ 2 in-repo patches) | on-demand (backend/pipeline start/stop) | 3900 | `${MACU_DATA_ROOT}/omnivoice/{state,data,hf-cache}` |
| **ollama** | `ollama/ollama` | on-demand | 11434 | `${MACU_DATA_ROOT}/ollama` |
| **comfyui** | local build (`Dockerfile` here) | long-lived | 8188 | `${MACU_DATA_ROOT}/comfyui/{ComfyUI,models,output,input,user,custom_nodes}` |
| **piper** | local build (`Dockerfile` here) | long-lived | 5050 | none — voice baked into the image (CPU-only); permissive default, HAL opt-in via `PIPER_VOICE=hal` |

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
  starts it.) Voice profiles live in the `state` volume (`omnivoice.db`) — see the
  model/asset fetch step for importing the existing MACU voices.

  > **The image is PINNED by digest, not `:latest`** (and `watchtower.enable=false`).
  > OmniVoice has **no working migration for an existing DB**: `_BASE_SCHEMA` is
  > `CREATE TABLE IF NOT EXISTS` (helps only fresh installs), the inline `_migrate`
  > stops at `user_version 4`, and the alembic chain never runs (no `alembic.ini` in the
  > image). So a floating `:latest` silently outruns an existing `omnivoice.db` and
  > breaks NEW clones with `voice_profiles has no column named kind` / `vd_states`
  > (SSA-122).
  >
  > **To intentionally upgrade — SCHEMA-SYNC, don't fresh-rebuild** (a rebuild reassigns
  > every `profile_id`, which the shows' `speaker_map`s reference by id). Recipe (the one
  > used to move max onto the 2026-06-13 image):
  > 1. `cp omnivoice.db omnivoice.db.bak` (back up; stop the container first).
  > 2. Get the canonical target schema — run the **new** image's own initializer against
  >    an empty dir (no GPU/server):
  >    `docker run --rm -e OMNIVOICE_DATA_DIR=/work -v /tmp/ref:/work --workdir /app/backend
  >    --entrypoint python <new-image> -c "from core.db import init_db; init_db()"`
  >    → `/tmp/ref/omnivoice.db` now holds the fresh schema.
  > 3. On a copy of the real DB, create any tables present in ref but missing locally and
  >    `ALTER TABLE … ADD COLUMN` any columns ref has that yours lacks (use ref's
  >    `PRAGMA table_info` for exact type/default; set `PRAGMA user_version` to match ref).
  >    The 2026-06-13 bump added tables `settings`, `mcp_client_bindings` and 8
  >    `voice_profiles` cols (`description, is_demo, verified_own_voice, consent_text,
  >    consent_audio_path, consent_recorded_at, kind, vd_states`).
  > 4. Verify the copy's schema matches ref table-for-table + data counts/ids are intact,
  >    swap it in, start the new image, confirm `GET :3900/profiles` lists your voices,
  >    then re-`validate_cast`.
- **comfyui:** needs its source + models first (see below), then
  `docker compose -f comfyui/docker-compose.yml build && … up -d`.
- **piper:** `docker compose -f piper/docker-compose.yml up -d --build`. A
  permissive `rhasspy/piper-voices` model is baked into the image at build time, so
  there's nothing to fetch — it's the default voice engine and stays up. To bake in
  the HAL-9000 voice instead (opt-in; see NOTICE), build with
  `PIPER_VOICE=hal docker compose -f piper/docker-compose.yml up -d --build`.

### ComfyUI first-run (the model/asset fetch step does this)

Under `${MACU_DATA_ROOT}/comfyui/`:
```
git clone https://github.com/Comfy-Org/ComfyUI.git ComfyUI
git clone <ModelScopeT2V node> custom_nodes/ComfyUI_ModelScopeT2V
mkdir -p models output input user
# download into models/text2video/ (zeroscope unet + DAMO VAE/config) and models/clip/:
#   text2video/text2video_pytorch_model.pth   (zeroscope_v2_576w — the un-watermarked default)
#   text2video/VQGAN_autoencoder.pth, text2video/configuration.json  (DAMO VAE + config)
#   clip/open_clip_pytorch_model.bin          (text encoder)
```

> Licensing note: the zeroscope unet is OpenRAIL-M (commercial use OK); the DAMO
> VAE/CLIP/config are CC-BY-NC-4.0 (non-commercial). See NOTICE.

> These ~8 GB of weights are NOT in git — the installer's **model-fetch** step pulls
> them (zeroscope from HF, DAMO from ModelScope). The compose here only defines the
> runtime; data is fetched separately.

## Prereqs (the installer's `doctor` step checks these)

NVIDIA driver + **nvidia-container-toolkit**, Docker, and enough VRAM (the defaults
target an ~11 GB GPU, e.g. an RTX 2080 Ti). Install these first on a new machine.
