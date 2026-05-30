# macu-pipeline

Server-side render pipeline for **The MACU Report** — a fictional post-apocalyptic
retro-futurist newscast. Turns a per-episode manifest into a finished mp4 by chaining
Piper TTS → ComfyUI (zeroscope T2V) → RIFE frame interpolation → ffmpeg analog-jank
filter → music beds → faster-whisper ASR → SRT alignment → NVENC encode.

Lives on **Max** (Linux box with an RTX 2080 Ti). The author's drafting/orchestration
agent ("Leo") sits on a separate machine and drives this pipeline via either Vikunja
task hand-off, the included `serve.py` HTTP service, or n8n webhook bridges.

This repo doesn't include the source manifests, the rendered episodes, or the model
weights — those live on the shared media drive (`/mnt/storage/shares/MACU/...`).

## Pipeline stages

Each stage is a standalone module under `stage_<N>_<name>.py` and takes one positional
argument: the episode `<slug>`. All paths are resolved via `lib.episode_paths(slug)`
which reads `/mnt/storage/shares/MACU/episodes/<slug>/`.

Run them in order or use the all-stages driver `run.py`:

| # | script             | reads                              | writes                                                   | typical wall (3-min ep) |
|---|--------------------|------------------------------------|----------------------------------------------------------|-------------------------|
| 1 | `stage_1_vo.py`    | `manifest.cues[].vo`               | `vo/<cue>.wav` (Piper HAL TTS, parallel 4-wide)          | ~8s                     |
| 2 | `stage_2_masters.py` | `manifest.characters/.broll`     | `clips/<key>_master.zs.webp` (ComfyUI fire-and-poll)     | ~7–8 min for 12+ keys   |
| 3 | `stage_3_rife.py`  | `clips/*.zs.webp`                  | `.rife_frames/<key>_out/` (RIFE 3x, 24f → 72f)           | ~35s                    |
| 4 | `stage_4_assemble.py` | `manifest.cues` + RIFE PNG dirs | `.work/<slug>_nosubs.mp4` (per-cue ffmpeg + jank filter) | ~2 min                  |
| 5 | `stage_5_music.py` | `manifest.music` (optional)         | `.work/<slug>_music_nosubs.mp4` (random clip+offset beds) | ~3s                    |
| 6 | `stage_6_whisper.py` | music_nosubs audio                | `/tmp/macu_whisper_<slug>.json` (faster-whisper large-v3 CPU int8) | ~10 min       |
| 7 | `stage_7_srt.py`   | whisper + manifest VO text         | `final/<slug>.srt` (difflib alignment, ~7 words / cue)   | <1s                     |
| 8 | `stage_8_burn.py`  | `manifest.subtitles` + music_nosubs | `final/<slug>.mp4` (h264_nvenc, fontsdir burn)          | ~12s                    |

Every stage is **idempotent** — it detects existing output and skips the work. Re-runs
after partial failures are cheap.

## Driver

```
python3 run.py <slug>                              # full pipeline (stages 1-8)
python3 run.py <slug> --from 5                     # restart from stage N
python3 run.py <slug> --only 8                     # run a single stage
python3 run.py <slug> --events-out events.jsonl    # emit structured events for serve.py
```

Writes `/tmp/macu_render_<slug>_report.json` with per-stage timings.

## HTTP service

`serve.py` is a thin stdlib `http.server` wrapper for clients that can't or won't
invoke `run.py` directly. Single-worker queue (the GPU is the bottleneck anyway).

```
POST /render        body: {"slug":"epN","from_stage":1,"only":null}
                    → 202 {"job_id":"...", "events_url":"...", "status_url":"..."}
GET  /events/{id}   text/event-stream of `data: {...}\n\n` lines, terminates on
                    `event: end` after job.done or job.error
GET  /status/{id}   {job: {...}, event_count: N, last_events: [...]}
GET  /jobs          {jobs: [...]} newest-first
GET  /health        {ok: true, uptime_s: N}
```

Event vocabulary on the SSE stream:

```
{ts, kind: "job.started", slug, from_stage, only}
{ts, kind: "stage.started", n, name}
{ts, kind: "stage.done",   n, name, wall_s, result: {...}}
{ts, kind: "stage.error",  n, name, error, wall_s}
{ts, kind: "job.done",     final, thumbs, final_size_mb, final_duration_s, total_wall_s, report_path}
{ts, kind: "job.error",    error}
```

Run as a systemd unit — see `deploy/macu-render.service` for the canonical install.
Binds `0.0.0.0:8773` with no auth. LAN-only by design.

## Manifest schema (informal)

```json
{
  "episode": "ep5",
  "title": "...",
  "version": 2,
  "voice":      { "engine":"piper", "model":"hal", "endpoint":"http://10.0.0.245:5050/", ... },
  "comfyui":    { "workflow":"will-smith-modelscope-t2v",
                  "checkpoint":"zeroscope_v2_576w",
                  "frames":24, "width":384, "height":384, "steps":30, "cfg":15 },
  "style":      { "suffix":"...", "negative":"..." },
  "render_rule":"...",
  "title_assets": { "macu_report_title":"...", "macu_report_bumper":"..." },
  "characters": { "<key>": { "seed":<int>, "core":"..." }, ... },
  "broll":      { "<key>": "...prompt..." },
  "cues":       [ { "id":"c01", "speaker":"...", "vo":"...",
                    "shots":[ { "id":"c01_s1", "kind":"character|broll|title",
                                "who":"<key>", "asset":"<title key>", "seed":<int?> } ] } ],
  "music":      { "enabled":true, "source_dir":"...", "clips":["...mp3"],
                  "clip_seconds":19.8, "gain":0.16, "fade_in":1.5, "fade_out":2.5,
                  "beds": [{ "name":"intro","anchor":"start","cues":["c01"],"max_seconds":14 }] },
  "subtitles":  { "font":"Better VCR", "fontsize":18,
                  "fontsdir":"/mnt/storage/shares/MACU/assets/fonts",
                  "force_style":"BorderStyle=1,Outline=2,Shadow=1,..." }
}
```

`stage_4_assemble.py` computes per-shot duration as `cue.vo_duration / N_shots_in_cue` —
the manifest does NOT specify per-shot durations.

## Locked render settings (post-SSA-87)

- Checkpoint: **`cerspense/zeroscope_v2_576w`** (NOT the DAMO ModelScope T2V — that
  one has a baked-in shutterstock watermark in its weights that no negative prompt
  can suppress).
- Render: 384×384, 24 frames, 30 steps, cfg 15, sampler euler, scheduler normal.
- Interpolation: RIFE 3x via `rife-ncnn-vulkan` (Vulkan path picks up the 2080 Ti
  automatically; no CUDA wheel dance needed).
- Output (post jank filter): 1024×1024 @ 24fps via h264_nvenc cq 22.

## Hard-won gotchas (encoded in the stage scripts)

- **`anim_dump`, NOT ffmpeg's libwebp demuxer**, for webp → PNG. ffmpeg chokes on
  ComfyUI's animated webps with `invalid TIFF header in Exif`.
- **Do not bump source res past 384×384×24f.** 576×320×24f triggers ComfyUI's
  lowvram offload and the custom `ModelScopeT2VLoader` crashes with
  `Input type (torch.cuda.HalfTensor) and weight type (torch.HalfTensor) should be
  the same` (the temporal modules don't track lowvram patches).
- **Title slots fill their full per-shot share** via `tpad=stop_mode=clone`.
  An earlier cap-to-1.5s bug truncated VO at end of title-containing cues.
- **Same-character shots reuse one master.** All N SAFE shots came from one
  `safe_master.zs.webp`. Don't re-render per shot.
- **`Better VCR` font is actually `Better VCR-JP`** as of the dafont 25.09 release.
  Stage 8 falls back to `fc-scan`'ing the fontsdir if the requested family isn't
  registered.
- **The cached `.work/<slug>_nosubs.mp4` is the lever** for iterating subs or music
  styles without re-rendering shots. `--from 5` re-runs music + sub burn in seconds.
- **Whisper venv:** `/tmp/whisper-venv/bin/python` with `faster-whisper` (CPU int8).
  GPU fp16 fails on `libcublas.so.12` inside the venv — not worth fixing for ~10 min
  CPU runs.

## Dependencies

Host:
- Python 3.12+
- ffmpeg (with `h264_nvenc`, libass, libwebp, lavfi filters)
- ffprobe
- `anim_dump` (from the `webp` apt package)
- `rife-ncnn-vulkan` (release tarball from
  [nihui/rife-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan))
- `sqlite3` (only if you're poking n8n)

Python:
- `Pillow` (thumbnail strips)
- `faster-whisper` (under `/tmp/whisper-venv/`)

Services expected to be reachable on Max:
- ComfyUI on `:8188` with the `cerspense/zeroscope_v2_576w` `text2video_pytorch_model.pth`
  staged into `models/text2video/`, plus the OpenCLIP and SD-VAE that ComfyUI needs
  for ModelScope T2V.
- Piper HAL TTS on `:5050`.

## License

UNLICENSED — private repo, internal home-server pipeline. Ask before redistributing.
