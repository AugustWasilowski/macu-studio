# MACU Pipeline

MACU Pipeline is a self-hosted, GPU-backed system for producing stylized short-form video from a script. Its
built-in look is a black-and-white, retro-futurist analog-TV aesthetic. It pairs an 8-stage render pipeline
with **MACU Studio**, a web app that drives the whole process from a browser.

| Dir | What it is |
|---|---|
| `pipeline/` | the 8-stage render pipeline (`run.py`, `serve.py`, `stage_1..8`, `lib.py`) that turns an `episodes/<slug>/manifest.json` into a finished `final/<slug>.mp4` |
| `studio/` | **MACU Studio** — a FastAPI + React web app on `:8774` that drives the pipeline: write scripts, generate shot lists, clone + assign voices, place SFX, render, and review |
| `skills/` | Claude Code agent skills — authoring (`macu-report`, `police-squad-pass`, `comedy-writers-room`), render driver (`macu-render`), and channel setup (`setup-macu-channel`) |
| `docs/` | the canon, namespaced per show: `docs/_common/` (shared pipeline/tooling docs) + `docs/shows/<show-id>/` (per-show character bible, story arcs, etc.), editable in Studio's Canon Docs panel |
| `deploy/` | the installer (`doctor`, `install`, `fetch-models`), the GPU-service compose stacks, the chat bridge, and systemd units |

## What it does

From a per-episode `manifest.json`, the pipeline:

- **Voice** — per-cue voiceover from cloned character voices (OmniVoice) plus a synthetic register (Piper).
- **Video** — one text-to-video master per character/scene (ComfyUI, zeroscope T2V), interpolated to a higher
  frame rate (RIFE).
- **Assembly** — a per-shot analog-jank filtergraph (B&W, grain, vignette, chroma-shift, interlace), VO mux,
  music beds, and SFX.
- **Captions** — ASR (faster-whisper) aligned to the script text → burned-in subtitles.

MACU Studio puts a browser UI on all of it: a script editor, LLM shot-list generation, voice cloning and
per-character assignment, an SFX timeline, render with live progress, and review.

## Install

MACU is portable: every path and endpoint is env-driven (copy `.env.example` → `.env`; usually you only set
`MACU_SHARES`), and the GPU services + models come down from `deploy/`. **Requirements: an NVIDIA CUDA GPU**
(the defaults are tuned for an ~11 GB RTX 2080 Ti), Docker + the nvidia-container-toolkit, Node 20+, Python
3.11+, git, ffmpeg, and — for the chat tile — Claude Code. **Platform: Linux, or Windows via WSL2** — *not*
macOS (no CUDA). `deploy/doctor.sh` checks all of it.

```bash
git clone <repo-url> macu-pipeline
cd macu-pipeline

./deploy/install.sh        # 1st run creates .env and STOPS — set MACU_SHARES (.env) and
                           # MACU_DATA_ROOT (deploy/services/.env) to a writable path, then:
./deploy/install.sh        # doctor → pull images → fetch models (~8 GB) → build ComfyUI → app
./deploy/start-studio.sh   # start Studio
```

Open `http://localhost:8774/`. For the in-app chat tile
and writers' room, run **`/setup-macu-channel`** in Claude Code.

Full prerequisites, the staged flow, and the per-service compose stacks: **[INSTALL.md](INSTALL.md)** and
[`deploy/services/README.md`](deploy/services/README.md).

### Running & stopping Studio

- **Foreground (temporary):** `./deploy/start-studio.sh` — Ctrl-C to stop.
- **Service (persistent):** install the systemd unit (the app installer prints the exact commands) to start
  Studio on boot and auto-restart it. Stop/disable later with `sudo systemctl stop macu-studio` /
  `sudo systemctl disable --now macu-studio`.

From inside the app, the project menu (top-left **MACU STUDIO** → **More → Shut down Studio…**) stops the
server and **frees the GPU first** — it stops the ComfyUI / OmniVoice / Ollama containers, then exits. Start
it again from a terminal to come back.

## Pipeline stages

| # | Script | What it does | Wall (~4-min ep) |
|---|---|---|---|
| 1 | `stage_1_vo.py` | per-cue VO: OmniVoice clones (`:3900`) for human-cast speakers, Piper (`:5050`) for AI/appliance characters. Per-speaker routing from `manifest.voice.speaker_map`; cached by per-cue text+voice hash. Stage 1 owns the ephemeral OmniVoice container's lifecycle (start → render → stop). | ~80s |
| 2 | `stage_2_masters.py` | one ComfyUI master gen per unique `characters[*]`/`broll[*]` key. zeroscope_v2_576w @ 384×384×24f, cfg 15. Fire-and-poll (first gen cold-loads and times out the request but keeps running). | ~7-8 min |
| 3 | `stage_3_rife.py` | RIFE 3× (24f → 72f) per master via `rife-ncnn-vulkan`. | ~35s |
| 4 | `stage_4_assemble.py` | per-shot analog-jank filtergraph (B&W, grain, vignette, chroma-shift, interlace) → concat shots → mux VO → concat cues. Handles the animated intro card, closing bumper, and `no_subs`/`hold` cues. | ~2 min |
| 5 | `stage_5_music.py` | music beds (random clip+offset per bed) + `manifest.sfx[]` one-shots, mixed via adelay→amix. | ~2-5s |
| 6 | `stage_6_whisper.py` | faster-whisper large-v3 (CPU int8) ASR on the rendered audio → word timestamps. | ~10 min |
| 7 | `stage_7_srt.py` | difflib aligns manifest VO text to whisper timings → SRT (≤7 words / 3s per line). | <1s |
| 8 | `stage_8_burn.py` | burn SRT in the Better VCR font + h264_nvenc (cq 22) → `final/<slug>.mp4` + thumbnails. | ~12s |

`run.py <slug>` runs all 8 in order, idempotent/cache-aware. `--from N` restarts from a stage; `--only N` runs
one. `serve.py` exposes the same over HTTP on `:8773` with SSE stage events — that's what MACU Studio drives.

## Locked render settings (do not regress)

- Checkpoint: `zeroscope_v2_576w` — NOT DAMO ModelScope (that's the watermarked one, preserved as `.damo.pth`).
  The watermark is solved by the checkpoint, not by negatives.
- Render: 384×384, 24 frames, 30 steps, cfg 15, euler/normal. Output after RIFE 3×: 1024×1024 @ 24fps. Encode:
  h264_nvenc, preset p5, tune hq, cq 22.
- **VRAM:** 576×320×24f OOMs / crashes the temporal modules on an 11 GB GPU. Don't bump resolution without testing.

## Local services

All bind loopback; the pipeline and Studio reach them on `127.0.0.1`. Endpoints are env-overridable
(`MACU_COMFY_URL`, `MACU_PIPER_URL`, `MACU_OMNIVOICE_URL`).

- ComfyUI — `:8188` — zeroscope T2V masters.
- OmniVoice — `:3900` — cloned character voices (ephemeral container; stage 1 manages its lifecycle).
- Piper — `:5050` — the synthetic/machine register.
- Ollama — `:11434` — local LLM for Studio's shot-list generation (on-demand).

## Episode layout

Episode data lives outside the repo under `$MACU_SHARES` (default `/mnt/storage/shares/MACU`):

```
$MACU_SHARES/
├── episodes/<slug>/
│   ├── manifest.json        # source of truth for the episode
│   ├── script.md
│   ├── clips/ frames/ .rife_frames/ vo/ titles/ .work/
│   └── final/<slug>.mp4 + .srt + thumbnails
└── assets/{fonts,music,sfx,titles}/   # shared, reused across episodes
```

## Running a render

- **CLI:** `python3 pipeline/run.py <slug> [--from N | --only N]` (or the `macu-render` skill).
- **HTTP:** POST `{slug, from_stage?, only?}` to `serve.py` on `:8773`; subscribe to its SSE for stage events.
- **GUI:** open MACU Studio at `http://localhost:8774/` and drive it from the browser.

## Known gotchas

- **ComfyUI first gen cold-loads** the checkpoint and times out the request, but the job keeps running — fire and poll.
- **anim_dump, not ffmpeg's libwebp demuxer** — ffmpeg chokes on ComfyUI animated webps (`invalid TIFF header in Exif`).
- **Per-shot duration = cue.vo_dur / N_shots** — computed at run time from rendered VO; not in the manifest.
- **Title slots use their full per-shot share** (clone last frame via `tpad`); never hard-cap them or you truncate VO.
- **Better VCR font family is `Better VCR-JP`** — never put `FontName=`/`Fontsize=` inside subtitle `force_style`
  (libass last-key-wins silently drops to the default font).
