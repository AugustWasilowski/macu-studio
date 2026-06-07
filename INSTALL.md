# Installing MACU (Studio + render pipeline)

MACU is a local, GPU-backed video pipeline + web studio. It assumes **nothing
pre-installed except the host prerequisites** below — it brings up its own service
stack (OmniVoice, Ollama, ComfyUI, Piper) and fetches its models.

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

`deploy/doctor.sh` checks the host for these. On a **Debian/Ubuntu/WSL** box the
installer can install most of the missing ones for you: when preflight fails it
offers to run `deploy/install-prereqs.sh` (ffmpeg, Python ≥3.11 via deadsnakes,
Node 20 via nvm, and a best-effort nvidia-container-toolkit). On other distros, or
to do it by hand, install:

- **NVIDIA driver** + **nvidia-container-toolkit**
- **Docker** (engine + your user in the `docker` group)
- **Node 20+** (nvm recommended), **Python 3.11+**, **git**, **ffmpeg**
- *(optional, for the chat tile / writers' room)* **Claude Code**
- *(optional, for the in-app TERMINAL drawer)* **ttyd** + **tmux** — the installer
  auto-installs these via apt/dnf/pacman when missing; `setup-macu-channel` wires them up

Run `./deploy/doctor.sh` any time to see what's missing, or
`./deploy/install-prereqs.sh` to try installing them.

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
5. **Long-lived services** — builds + starts ComfyUI and **Piper** (the default
   synthetic voice on `:5050`; a permissive voice is baked into its image — the
   HAL-9000 voice is opt-in via `PIPER_VOICE=hal`).
6. **Studio app + render venv** — Python venv + frontend build
   (`studio/scripts/install.sh`), plus a `.whisper-venv` for the stage-6 captions.

Then start Studio with **`./deploy/start-studio.sh`** (it also starts the render
service on `:8773`) and open `http://localhost:8774/`. To run on boot, see
`sudo ./deploy/install-systemd.sh`.

## Running on boot / in the background

- **systemd (Linux, or WSL with systemd enabled):**
  `sudo ./deploy/install-systemd.sh` templates the `macu-render` + `macu-studio`
  units to this machine, then `sudo systemctl enable --now macu-render macu-studio`.
  Stop with `sudo systemctl stop macu-render macu-studio`; disable boot-start with
  `sudo systemctl disable macu-render macu-studio`.
  (WSL only runs systemd if `[boot]\nsystemd=true` is set in `/etc/wsl.conf` and WSL
  has been restarted with `wsl --shutdown`.)

- **WSL without systemd (or anywhere you just want it backgrounded):** run it under
  `tmux` (survives the terminal closing, and you can re-attach):

  ```bash
  tmux new -s macu -d './deploy/start-studio.sh'   # start detached
  tmux attach -t macu                              # watch it / Ctrl-b d to detach
  tmux kill-session -t macu                        # stop
  ```

  or `nohup`:

  ```bash
  nohup ./deploy/start-studio.sh > ~/macu-studio.log 2>&1 &
  ```

  (WSL doesn't auto-start Linux services on Windows boot; launch it from your WSL
  shell, or add the tmux line to your shell profile.)

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
