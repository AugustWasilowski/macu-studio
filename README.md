# MACU Pipeline

The production system for **The MACU Report** — August's black-and-white, post-apocalyptic, retro-futurist
faux-newscast in the Mayor Awesome Cinematic Universe. This one repo is the hub for **four** things:

| Dir | What it is |
|---|---|
| `pipeline/` | the 8-stage render pipeline (`run.py`, `serve.py`, `stage_1..8`, `lib.py`, `stackchan.py`, `freesound_fetch.py`) that turns an `episodes/<slug>/manifest.json` into a finished `final/<slug>.mp4` |
| `skills/` | the Claude Code agent skills — `macu-report` (authoring), `macu-render` (render driver), `comedy-writers-room` (critic panel) |
| `docs/` | the canon — character bible, world lore, pipeline design, story arcs, weekly routine, OmniVoice voice roster/tips |
| `studio/` | **MACU Studio** — the FastAPI + React web front end on `:8774` that drives the same pipeline from a browser |

**Everything runs on Max** (the Linux home server, RTX 2080 Ti). The repo lives on the **storage drive**, next
to the other app dirs (`/mnt/storage/{comfyui,hyperframes,...}`), so code + git history ride the same portable
drive as the episode data. One source of truth — no more code-on-OS-disk + drifting-copy-on-storage split:

```
/mnt/storage/macu-pipeline/        ← git repo (source of truth, on the storage drive)
├── pipeline/        the 8-stage renderer (run.py, serve.py, stage_1..8, lib.py, …)
├── skills/          macu-report, macu-render, comedy-writers-room  ←─symlinked─ ~/.claude/skills/
├── docs/            the canon (bible, lore, voice roster/tips, …)
├── studio/          MACU Studio (FastAPI :8774 + React)
└── deploy/          systemd units

/mnt/storage/shares/MACU/          ← episode DATA (Windows-visible as S:\MACU; gitignored)
├── episodes/<slug>/   manifests + per-episode artifacts
├── assets/{fonts,music,sfx,titles}/
└── pipeline ──symlink──▶ /mnt/storage/macu-pipeline/pipeline   (back-compat for old absolute paths)

~/work/macu-pipeline ──symlink──▶ /mnt/storage/macu-pipeline    (back-compat)
```

The render service (`macu-render.service`) and MACU Studio (`macu-studio.service`) both run the code from
`/mnt/storage/macu-pipeline/`; the units carry `RequiresMountsFor=/mnt/storage` so they wait for the drive.

> **History:** this started as a Leo→Max split — August authored on Leo (Windows) and shipped renders to Max
> over a Syncthing `macu` folder + Vikunja + n8n bridges. Authoring moved onto Max (all local now: no Syncthing
> wait, no cross-machine handoff, services on loopback), and the code was consolidated onto the storage drive
> 2026-06-03 so the whole project is one portable unit.

## Pipeline stages

| # | Script | What it does | Wall (~4-min ep) |
|---|---|---|---|
| 1 | `stage_1_vo.py` | per-cue VO: OmniVoice clones (`:3900`) for human-cast speakers, Piper HAL (`:5050`) for AI/appliance characters. Per-speaker routing from `manifest.voice.speaker_map`; cached by per-cue text+voice hash in `vo/.cache.json`. Stage 1 owns the ephemeral OmniVoice container's lifecycle (start → render → stop). | ~80s |
| 2 | `stage_2_masters.py` | one ComfyUI master gen per unique `characters[*]`/`broll[*]` key. zeroscope_v2_576w @ 384×384×24f, cfg 15. Fire-and-poll (first gen cold-loads + times out the request but keeps running). | ~7-8 min |
| 3 | `stage_3_rife.py` | RIFE 3× (24f → 72f) per master via `rife-ncnn-vulkan` (Vulkan / 2080 Ti). | ~35s |
| 4 | `stage_4_assemble.py` | per-shot analog-jank filtergraph (B&W, grain, vignette, chromashift, interlace) → concat shots → mux VO → concat cues → `.work/<slug>_nosubs.mp4`. Handles the animated intro card + closing bumper + `no_subs`/`hold` cues. | ~2 min |
| 5 | `stage_5_music.py` | music beds (random clip+offset per bed) + `manifest.sfx[]` one-shots, mixed via adelay→amix. | ~2-5s |
| 6 | `stage_6_whisper.py` | faster-whisper large-v3 (CPU int8) ASR on the rendered audio → word timestamps. | ~10 min |
| 7 | `stage_7_srt.py` | difflib aligns manifest VO text to whisper timings → SRT (≤7 words / 3s per line). | <1s |
| 8 | `stage_8_burn.py` | burn SRT in the Better VCR font + h264_nvenc (cq 22) → `final/<slug>.mp4` + `_thumbs.jpg`; extract 1920×1080 `final/<slug>_thumb.png`. | ~12s |

`run.py <slug>` runs all 8 in order, idempotent/cache-aware. `--from N` restarts from a stage; `--only N` runs
one. `serve.py` exposes the same over HTTP on `:8773` (systemd `macu-render.service`) with SSE stage events —
that's what MACU Studio drives.

## Locked render settings (do not regress)

- Checkpoint: `zeroscope_v2_576w` — NOT DAMO ModelScope (that's the shutterstock-watermarked one, preserved as
  `.damo.pth`). The watermark is solved by the checkpoint, not by negatives.
- Render: 384×384, 24 frames, 30 steps, cfg 15, euler/normal. Output after RIFE 3×: 1024×1024 @ 24fps. Encode:
  h264_nvenc, preset p5, tune hq, cq 22.
- **VRAM:** 576×320×24f OOMs / crashes the temporal modules on the 11 GB 2080 Ti. Don't bump res without testing.

## Local services

- ComfyUI: `http://127.0.0.1:8188/` — zeroscope T2V masters.
- OmniVoice: `http://127.0.0.1:3900/` — cloned character voices (ephemeral container; stage 1 manages it).
- Piper HAL: `http://127.0.0.1:5050/` — the calm machine register.
- StackChan: `http://10.0.0.134/leds/buffer` — per-stage LED progress bar.

(Older `episodes/<slug>/manifest.json` files carry `10.0.0.245:…` endpoints; those still work from Max since
Piper/ComfyUI bind `0.0.0.0`, and stage 1 hardcodes loopback for OmniVoice regardless. New manifests use `127.0.0.1`.)

## Layout

```
shares/MACU/
├── pipeline -> /mnt/storage/macu-pipeline/pipeline   # symlink (back-compat)
├── episodes/<slug>/
│   ├── manifest.json         # source of truth for the episode
│   ├── script.md
│   ├── clips/ frames/ .rife_frames/ vo/ titles/ .work/
│   └── final/<slug>.mp4 + .srt + _thumbs.jpg + _thumb.png
├── assets/{fonts,music,sfx,titles}/   # shared, reused across episodes
└── agent-io/{leo,max}/       # per-agent scratch (source transcripts, etc.)
```

## Running a render

- **Agent / CLI:** `/macu-render <slug>` (the skill) or `python3 pipeline/run.py <slug> [--from N|--only N]`.
- **HTTP:** POST `{slug, from_stage?, only?}` to `serve.py` on `:8773`; subscribe to its SSE for stage events.
- **GUI:** open [MACU Studio](studio/README.md) at `http://10.0.0.245:8774/` and drive it from the browser.

## Known gotchas

- **ComfyUI first gen cold-loads** the checkpoint and times out the request, but the job keeps running — fire and poll.
- **anim_dump, not ffmpeg's libwebp demuxer** — ffmpeg chokes on ComfyUI animated webps (`invalid TIFF header in Exif`).
- **Per-shot duration = cue.vo_dur / N_shots** — computed at run time from rendered VO; not in the manifest.
- **Title slots use their full per-shot share** (clone last frame via `tpad`); never hard-cap them or you truncate VO.
- **Better VCR font family is `Better VCR-JP`** — never put `FontName=`/`Fontsize=` inside subtitle `force_style` (libass last-key-wins silently drops to default).
