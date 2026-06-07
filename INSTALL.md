# Installing MACU (Studio + render pipeline)

MACU is a local, GPU-backed video pipeline + web studio. It assumes **nothing
pre-installed except the host prerequisites** below — it brings up its own service
stack (OmniVoice, Ollama, ComfyUI, Piper HAL) and fetches its models.

> **Hardware:** an NVIDIA GPU is required (the defaults target an ~11 GB 2080 Ti).
> Linux or WSL2.

## Quick start

```bash
git clone <repo-url> macu-pipeline
cd macu-pipeline

./deploy/install.sh          # 1st run: creates .env and STOPS so you can set your paths

# Edit the two created files to a WRITABLE location on this machine. On WSL, use
# the Linux filesystem ($HOME), NOT /mnt/c or /mnt/f (Windows mounts are slow):
#   .env                  ->  MACU_SHARES=$HOME/macu-data/shares/MACU
#   deploy/services/.env  ->  MACU_DATA_ROOT=$HOME/macu-data

./deploy/install.sh          # re-run: does the full install
./deploy/start-studio.sh     # start Studio, then open http://localhost:8774/
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
2. **Config** — on the first run it creates `.env` + `deploy/services/.env` and
   **stops** so you can set `MACU_SHARES` / `MACU_DATA_ROOT` to a writable path on
   this machine; re-run to continue. It also verifies those paths are writable
   before downloading anything.
3. **Service images** — pulls the on-demand OmniVoice + Ollama images.
4. **Models + assets** — `fetch-models.sh`: clones ComfyUI + the ModelScopeT2V
   node, downloads the ~8 GB text2video weights (zeroscope + DAMO/VQGAN from
   public sources), pulls `qwen2.5:7b-instruct-q4_K_M`, installs the bundled
   subtitle font. **Public sources only — no personal data.**
5. **Long-lived services** — builds + starts ComfyUI and **Piper HAL** (the default
   synthetic voice on `:5050`; the HAL-9000 voice is baked into its image).
6. **Studio app + render venv** — Python venv + frontend build
   (`studio/scripts/install.sh`), plus a `.whisper-venv` for the stage-6 captions.

Then start Studio with **`./deploy/start-studio.sh`** (it also starts the render
service on `:8773`) and open `http://localhost:8774/`. To run on boot, see
`sudo ./deploy/install-systemd.sh`.

## The two halves a script can't do

- **Voices.** The installer ships **no** cloned voices — clone your own with the
  *Create Voice* button in the Audio page.
- **The Claude Code coupling.** The chat tile + writers' room route to a Claude
  Code session over a channel — wiring that touches Claude Code's config and needs
  permission approvals, so it's done **inside Claude Code**: run the
  **`setup-macu-channel`** skill, which generates the token, starts the chat
  bridge, and tests the loop.

## Services reference

See `deploy/services/README.md` for the individual compose stacks, ports, and
data layout.
