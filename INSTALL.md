# Installing MACU (Studio + render pipeline)

MACU is a local, GPU-backed video pipeline + web studio. It assumes **nothing
pre-installed except the host prerequisites** below — it brings up its own service
stack (OmniVoice, Ollama, ComfyUI) and fetches its models.

> **Hardware:** an NVIDIA GPU is required (the defaults target an ~11 GB 2080 Ti).
> Linux or WSL2.

## TL;DR

```bash
git clone https://github.com/AugustWasilowski/macu-pipeline.git
cd macu-pipeline
./deploy/install.sh          # runs the stages below in order
```

## Prerequisites (checked by `deploy/doctor.sh`)

Install these first — the installer **checks but does not install** them (too
OS-specific, especially on WSL):

- **NVIDIA driver** + **nvidia-container-toolkit**
- **Docker** (engine + your user in the `docker` group)
- **Node 20+** (nvm recommended), **Python 3.11+**, **git**, **ffmpeg**
- *(optional, for the chat tile / writers' room)* **Claude Code**

Run `./deploy/doctor.sh` any time to see what's missing.

## What the installer does (`deploy/install.sh`)

1. **Preflight** — `doctor.sh`.
2. **Config** — creates `.env` (set `MACU_SHARES` if your storage isn't
   `/mnt/storage`) and `deploy/services/.env` (`MACU_DATA_ROOT`).
3. **Service images** — pulls the on-demand OmniVoice + Ollama images.
4. **Models + assets** — `fetch-models.sh`: clones ComfyUI + the ModelScopeT2V
   node, downloads the ~8 GB text2video weights (zeroscope + DAMO/VQGAN from
   public sources), pulls `qwen2.5:7b-instruct-q4_K_M`, installs the bundled
   subtitle font. **Public sources only — no personal data.**
5. **ComfyUI** — builds the local image and starts it.
6. **Studio app** — Python venv + frontend build (`studio/scripts/install.sh`).

Then start Studio (printed at the end) and open `http://localhost:8774/`.

## The two halves a script can't do

- **Voices.** The installer ships **no** cloned voices — clone your own with the
  *Create Voice* button in the Audio page. If you're setting up a **second machine
  you own**, copy your existing voice store + asset kits instead (exact voices/ids):
  `deploy/sync-personal-data.sh <user@your-existing-box>`.
- **The Claude Code coupling.** The chat tile + writers' room route to a Claude
  Code session over a channel — installing that touches Claude Code's config and
  needs permission approvals, so it's done **inside Claude Code** (a
  `setup-macu-channel` skill is the planned next phase), not by this script.

## Services reference

See `deploy/services/README.md` for the individual compose stacks, ports, and
data layout.
