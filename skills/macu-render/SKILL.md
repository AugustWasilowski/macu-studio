---
name: macu-render
description: "Render a MACU Report episode end-to-end from its manifest. Trigger when the user says 'render MACU <slug>', '/macu-render <slug>', or when a Vikunja task assigned to Max contains [MACU] + 'render' (project 3, agent-coordination). Drives the proven 8-stage pipeline on Max: per-speaker VO routing (OmniVoice clones + Piper HAL for robot characters) → ComfyUI zeroscope masters → RIFE 3x → ffmpeg jank assembly → music beds → faster-whisper ASR → manifest-text-aligned SRT → Better VCR sub burn + h264_nvenc. Idempotent (each stage skips if its output is cached). Reports back via Vikunja comment with the format Max has been using: per-stage timings table + output path + thumb strip."
trigger: /macu-render
---

# /macu-render

End-to-end render driver for MACU Report episodes. Reads `episodes/<slug>/manifest.json` and runs all 8 pipeline stages in order with caching at each stage, so re-runs after partial failure are cheap.

## Trigger

- **Slash command:** `/macu-render <slug>` — e.g. `/macu-render ep-011`. The slug is the directory name under `/mnt/storage/shares/MACU/episodes/` (or, for a non-default show, under that show's `episodes_dir` — see Multi-show).
- **Vikunja:** when a task is assigned to Max in project 3 with `[MACU]` + `render` in the title, the ss-channels session should read the task description for the episode slug and invoke this skill.
- **Phrase:** "render MACU episode <slug>" / "render macu <slug>" — same behavior.

## Usage

```
/macu-render ep-011                 # run all 8 stages, idempotent (cache-aware)
/macu-render ep-011 --from 5        # restart from stage 5 (music) — useful for sub/music tweaks
/macu-render ep-011 --only 8        # rebuild only the sub-burn (when manifest.subtitles changed)
/macu-render ep-011 --no-stackchan  # disable the StackChan LED progress bar (also via MACU_NO_STACKCHAN env var)
```

## What it does

Invokes `/mnt/storage/shares/MACU/pipeline/run.py <slug>` which runs in order:

| # | stage | reads | writes | typical wall |
|---|---|---|---|---|
| 1 | `vo`       | manifest.cues[].vo + manifest.voice.speaker_map | vo/<cue>.wav (per-speaker dispatch: OmniVoice clones at :3900 or Piper HAL at :5050, serial). Auto-starts the `omnivoice` container if any non-cached cue needs it and stops it again on the way out (~4.6 GB VRAM released for stage 2). Cues with `hold_seconds: N` emit a silent wav of N seconds via ffmpeg anullsrc (no TTS dispatch). | ~80s for a ~4-min ep (+ ~15-30s OmniVoice cold start on first cue) |
| 2 | `masters`  | manifest.characters / .broll      | clips/<key>_master.zs.webp (ComfyUI fire-and-poll) | ~7-8 min for ~12 keys, serialized on the 2080 Ti |
| 3 | `rife`     | clips/*.zs.webp                   | .rife_frames/<key>_out/ (RIFE 3x to 72f) | ~35s for ~12 masters via rife-ncnn-vulkan |
| 4 | `assemble` | manifest.cues + RIFE PNG dirs + manifest.overlays[] | .work/<slug>_nosubs.mp4 (per-cue ffmpeg w/ jank filter, VO mux, concat). Then bakes any spanning title-card graphics via `stage_4b_graphics.apply()` (no-op when `manifest.overlays[]` is empty) and snapshots `.work/<slug>_nosubs_clean.mp4` so an overlay-only edit can re-composite without a full re-assemble. | ~2 min |
| 5 | `music`    | manifest.music (optional) + manifest.sfx[] (optional) | .work/<slug>_music_nosubs.mp4 (random clip+offset per bed, amix). SFX one-shots from `assets/sfx/<file>` pin to a cue at start/end with optional `delay`/`gain`/`fade_*`; they ride the same amix chain as the beds and work even with music.enabled=false. | ~2-5s |
| 6 | `whisper`  | music_nosubs audio                | /tmp/macu_whisper_<slug>.json (faster-whisper large-v3 CPU int8) | ~10 min |
| 7 | `srt`      | whisper + manifest.cues[].vo      | final/<slug>.srt (difflib alignment, max 7 words / 3s per cue) | <1s |
| 8 | `burn`     | manifest.subtitles + music_nosubs | final/<slug>.mp4 (h264_nvenc cq 22, Better VCR font) | ~12s |

After all stages, `run.py` builds a 7-up `final/<slug>_thumbs.jpg` strip, derives a 1920×1080 YouTube still `final/<slug>_thumb.png` from the episode's wide/square thumb card (`titles/thumb_wide.mp4` → fallback `titles/thumb.mp4`; skipped if neither exists), and writes `/tmp/macu_render_<slug>_report.json` with per-stage timings + output paths.

## Cache strategy (each stage detects and skips)

- VO: skip cues whose `vo/<cue>.wav` exists AND whose sidecar hash in `vo/.cache.json` matches the cue's current hash (text + speaker + voice engine/profile/voice_name, or hold_seconds for silent cues). A manifest edit that doesn't change *that cue's* inputs does NOT invalidate it. First-run migration seeds the sidecar from existing wavs — no forced full regen when this version of the pipeline first runs on an episode dir. Hand-tuned/swapped wavs (e.g. copying c25.wav over c23.wav to fix audio masking) survive any manifest edit that doesn't change c23's own text/voice — no more `--from 4` dance after edits.
- Masters: skip keys whose `clips/<key>_master.zs.webp` exists
- RIFE: skip masters whose `.rife_frames/<key>_out/` has the expected frame count
- Assemble: skip if `.work/<slug>_nosubs.mp4` is newer than the manifest. The stage-4b graphics bake (spanning title-card overlays) runs inside this stage off `manifest.overlays[]`; it's a no-op when there are no overlays.
- Music: pass-through if `manifest.music.enabled` is false (no music block)
- Whisper: skip if `/tmp/macu_whisper_<slug>.json` is newer than the audio source
- SRT: always runs (cheap; <1s)
- Burn: always runs (this is where you iterate sub style)

`--from N` lets you force re-run from stage N onward. `--only N` runs just one stage. Use these for sub/music/style iteration without re-rendering shots.

## Multi-show (MACU_EPISODES)

MACU Studio gained a multi-show layer (2026-06-06): episodes for shows *other than* **The MACU Report** live outside the default `episodes/` dir. `run.py` (via `lib.episode_paths`) resolves the episodes dir from the **`MACU_EPISODES`** env var (`lib.EPISODES_ROOT`), defaulting to `/mnt/storage/shares/MACU/episodes` — so **the-macu-report renders exactly as before with no env set; this skill's default behavior is unchanged.**

To render an episode of a *different* show from this skill, point `MACU_EPISODES` at that show's episodes dir before invoking `run.py`:

```
MACU_EPISODES=/mnt/storage/shares/MACU/shows/<show-id>/episodes \
    python3 /mnt/storage/shares/MACU/pipeline/run.py <slug>
```

The per-show episodes dir is recorded in the registry at `studio/shows.json` (each entry's `episodes_dir`). Slugs are globally unique across shows, so the slug alone is unambiguous — `MACU_EPISODES` only tells `run.py` *where* the dir lives. **Studio-driven renders set this automatically** (the macu-render HTTP service injects the per-job `episodes_dir` into the stage subprocess env); the manual `export` above is only needed for the **CLI/skill** path on a non-default show.

## Hard-won gotchas (encoded in the stage scripts)

- **Per-speaker voice routing** lives in `manifest.voice.speaker_map`. Keys are exact cue speaker strings (e.g. `RON`, `MOTHER MARIGOLD`, `TALLY MAN`, `SAFE`). Engine is `omnivoice` (with `profile_id`) or `piper` (HAL). Unmapped speakers fall back to `manifest.voice.default` (Piper HAL). All VO is normalized to 24 kHz mono PCM s16 in stage 1 so stage 4's concat-copy doesn't trip on sample-rate mismatches.
- **VO is serial, not parallel.** OmniVoice's torch.compile path asserts under concurrent /generate calls (cudagraph TLS issue). `max_workers=1` in stage 1. Piper would tolerate parallelism but we share the worker pool for simplicity.
- **OmniVoice is hosted at 127.0.0.1:3900** — bound to loopback only inside the omnivoice container's compose. Stage 1 calls `OMNIVOICE_URL = http://127.0.0.1:3900` (defined in `lib.py`). If you ever move the pipeline off Max, expose the port or proxy it.
- **OmniVoice torch.compile mode is patched to `default`** (was `reduce-overhead` upstream, which uses cudagraphs and breaks across-thread inference). Patch is bind-mounted at `/home/mayorawesome/docker/omnivoice/patches/model_manager.py` — survives Watchtower bumps as long as the upstream file path is stable. See `omnivoice_gpu_pool_bug` memory.
- **OmniVoice is ephemeral — stage 1 owns its lifecycle.** The container is **stopped by default** so its ~4.6 GB doesn't compete with ComfyUI. Stage 1's `main()` calls `omnivoice_start()` (in `lib.py`) before the render loop and `omnivoice_stop()` in a `finally` so VRAM is released even on failure. The start probe polls TCP `:3900` then HTTP `/docs` until the FastAPI is responding (180 s timeout). If you want to keep OmniVoice up after stage 1 — e.g. iterating just on VO with `--only 1` — export `MACU_KEEP_OMNIVOICE=1`.
- **OmniVoice VRAM gotcha (incident ep6, 2026-05-30):** before stage 1 started managing the container, leaving OmniVoice up post-VO drove ComfyUI into lowvram offload during stage 2 — the ModelScopeT2VLoader's temporal modules crashed with `Input type (torch.cuda.HalfTensor) and weight type (torch.HalfTensor) should be the same` because some weights got swung to CPU. Symptom: every master prompt instantly enters `error` status with that exception; stage 2 then poll-sleeps for its 60-min timeout waiting for prompts that already died. If you ever see that traceback, check `nvidia-smi --query-compute-apps`; if OmniVoice is still resident, the lifecycle wiring is broken.
- **Other consumers of OmniVoice** (e.g. the voice-clone wrapper at `/mnt/storage/shares/MACU/voices/clone_one.sh`) must `docker start omnivoice` themselves now — the container won't be running between renders. Stop it again afterward to keep the GPU clean.
- **anim_dump, not ffmpeg's libwebp demuxer** for webp → PNG. ffmpeg chokes on ComfyUI animated webps with `invalid TIFF header in Exif`.
- **Don't bump res past 384×384×24f.** 576×320×24f triggers ComfyUI's lowvram offload and the custom ModelScopeT2VLoader's temporal modules crash with fp16 CPU/CUDA dtype mismatch on the 11 GB 2080 Ti.
- **Title slots fill their full per-shot share** (`tpad=stop_mode=clone` to pad short title MP4s). The old "cap to 1.5s" bug truncated VO at end of title-containing cues — don't reintroduce.
- **Per-shot duration = cue VO duration / N shots in that cue.** The manifest doesn't specify per-shot durations; the assembler computes at run time from rendered VO. Stage 1 must complete before stage 4.
- **Silent `hold` cues** (since ep10 prep, 2026-05-30): a cue with `"hold_seconds": N` and `"vo": ""` is a no-dialogue beat for comedic reaction cuts. Stage 1 generates a real silent wav of N seconds via `ffmpeg -f lavfi -i anullsrc -t N` instead of calling TTS, so stage 4's per-shot math (`vo_dur / N shots`) works unchanged. Hold cues do NOT count toward the OmniVoice lifecycle decision — pure-hold episodes won't spin up the container. Stage 7 SRT defensively uses `cue.get("vo") or ""` so a hold cue contributes zero subtitle words. **Stage 4 routes hold-cue character/broll shots through `freeze_shot()` instead of `rife_shot()`** — it locks onto the master's first PNG and runs the jank filter on top of that still frame, so characters don't animate (mouth moving, gestures) while there's no dialogue. The broadcast aesthetic (noise, scanline shimmer, tinterlace) is still alive per-frame because it's all in the jank filter, not the input PNGs. Title shots inside a hold cue are unaffected (they keep their own playback).
- **SFX one-shots** (since ep10 prep, 2026-05-30): top-level `manifest.sfx[]` array (sibling of `manifest.music`, NOT nested inside it) of `{file, cue, at, gain?, delay?, fade_in?, fade_out?}`. Files live in shared `/mnt/storage/shares/MACU/assets/sfx/` (10 synthesized starters there: EBS tone + bent variant, cricket, static, hum, buzz, ding, plus three placeholder percussives). `at: "start"` parks at `cum[cue]`, `at: "end"` parks at `cum[cue] + cue_dur[cue] - sfx_dur`. Optional `delay` (signed seconds) nudges before/after. SFX defaults to **hard cuts** (no fades) because cuts are funnier — set `fade_out` explicitly if you want one. Missing files log a WARN and skip gracefully; stage 5 keeps running. SFX work even with `music.enabled=false`. Source files are peak-normalized to −3 dBFS so `gain` 0.0-1.0 behaves linearly.
- **Acquiring new SFX**: three paths, all landing a 24 kHz mono PCM s16 / −3 dBFS file in `assets/sfx/`:
  1. **freesound.org CC0** via `python3 /mnt/storage/shares/MACU/pipeline/freesound_fetch.py "<query>" <basename> [--duration-max N]`. Searches the freesound API, filters by CC0, downloads the top preview MP3, normalizes to the kit standard. Creds at `~/.config/freesound/credentials.env` (mode 600). Append a catalog row to `assets/sfx/README.md` with the freesound URL + sound id + CC0 license.
  2. **`agen` text-to-foley** (local, de-novo) via `python3 /mnt/storage/shares/MACU/pipeline/agen_sfx.py "<prompt>" <basename> [--duration N] [--seed N]`. Wraps the AudioGen model behind `/mnt/storage/audio-gen/agen sfx`, then runs the **same `normalize()`** as freesound (re-samples agen's 16 kHz up to the 24 kHz kit). Auto-logs a catalog row tagged `agen sfx` (MACU-local, AudioGen) / Public Domain (de novo) with the **prompt + seed** (reproducible — seed defaults to a hash of the prompt). Use when no good CC0 match exists, or for a bespoke sound the script calls for (a specific bonk, a particular car engine, etc.). **GPU lifecycle:** agen is another ~6 GB GPU consumer — `agen_lib.ensure_gpu_free()` refuses to run if <6.5 GB is free, so it can't collide with ComfyUI stage 2 or OmniVoice stage 1 (the ep6 lowvram failure class). Run it as a **curated pre-pass when the GPU is idle**, like freesound; do NOT call it inline during stages 1–4.
  3. **ffmpeg lavfi synth** in the kit's own PD-synth style — see `assets/sfx/README.md`. Unambiguously public-domain and reproducible; use it for predictable in-mix character (the EBS tones, cricket chirp, etc.).
- **Generating music beds** (`agen`): `python3 /mnt/storage/shares/MACU/pipeline/agen_music.py "<prompt>" <basename> [--engine music|riff] [--duration N] [--seed N]` writes a bed into `assets/music/` (catalog row logged), then reference it from `manifest.music.clips[]` like the existing big-band clips. `music` = MusicGen (drifts/loops past ~15–20s — on-brand jank); `riff` = Riffusion (grittiest, tape-degraded lo-fi). Same GPU gate as SFX. The Studio Audio panel also exposes both: a "Generate (agen)" toggle in the Add-SFX dialog (`POST /api/episodes/<slug>/sfx/gen`) and `POST /api/episodes/<slug>/music/gen`.
- **Same-character shots reuse one master.** All 5 SAFE shots came from one `safe_master.zs.webp`. Don't re-render per shot.
- **Empty-room broll quirk:** stage 4 maps `empty_room` to `c09_s1.zs.webp` (the legacy SAFE-ad slice's broll render). New brolls under `broll[key]` get their own `broll_<key>` master.
- **Checkpoint:** zeroscope_v2_576w is active (`text2video_pytorch_model.pth`). DAMO is preserved as `.damo.pth` for rollback — that's the watermarked ModelScope T2V we replaced.
- **Better VCR font family is `Better VCR-JP`** as of the 25.09 dafont release. Stage 8 falls back to `fc-scan`'ing the fontsdir if `manifest.subtitles.font` isn't registered.
- **Cached `.work/<slug>_nosubs.mp4` is the lever** for iterating subs or music without re-rendering shots. `--from 5` re-runs music + sub burn in seconds.
- **Whisper venv:** `/tmp/whisper-venv/bin/python` with `faster-whisper` (CPU int8). GPU fp16 fails on `libcublas.so.12` inside the venv — not worth fixing for ~10 min CPU runs.

## StackChan LED progress bar

A 30-LED WS2812 strip on the StackChan's Port C acts as a per-stage progress bar during renders. The 8 stages map to 8 colored zones across the strip (`LEDS_PER_STAGE = [4, 4, 3, 4, 4, 4, 3, 4]`, total 30):

| # | stage | color | LEDs |
|---|---|---|---|
| 1 | vo       | blue     | 0..3   |
| 2 | masters  | magenta  | 4..7   |
| 3 | rife     | cyan     | 8..10  |
| 4 | assemble | yellow   | 11..14 |
| 5 | music    | green    | 15..18 |
| 6 | whisper  | orange   | 19..22 |
| 7 | srt      | red      | 23..25 |
| 8 | burn     | white    | 26..29 |

**Behavior:**
- Each zone fills left-to-right as its stage runs; once a stage completes, its zone stays lit while later zones start filling.
- **Sub-progress** during the two long stages:
  - Stage 2 (masters, ~7-8 min): one tick per ComfyUI job completed.
  - Stage 6 (whisper, ~10 min): background thread ticks every 2s based on `elapsed / (audio_dur × 2.0)`, capped at 0.95 until the venv subprocess returns.
- **Job done**: all 30 LEDs hold their per-stage colors for 3s, then clear.
- **Job failed**: failing stage's zone turns solid red for 2s, then clear. Earlier zones stay lit so you can see how far it got.
- **Partial run** (`--from N` / `--only N`): strip is left in its last-painted state — no auto-clear so you can see which stages ran.

**Auto-disable** if the StackChan is unreachable (`stackchan.reachable()` probes `GET /status` with a 1s timeout). Manual opt-out via `--no-stackchan` or `MACU_NO_STACKCHAN=1`. All LED HTTP calls have a 1s timeout and swallow errors silently — they cannot block or fail a render.

**Brightness** is software-scaled in `stackchan.py` via `LED_BRIGHTNESS` (default **0.20**) — every RGB value is multiplied by that factor before posting to the firmware. Override at runtime with the env var `STACKCHAN_BRIGHTNESS=<0.0-1.0>` (e.g. `STACKCHAN_BRIGHTNESS=0.10 python3 run.py ep10` for night-mode, `0.50` for fully-lit-room visibility). The constant lives at the top of `pipeline/stackchan.py` if you want to change the default; STAGE_COLORS are stored at full scale (255) and only dimmed at paint time, so all eight hues stay distinguishable as the scaler drops.

**Implementation:** `pipeline/stackchan.py` (zone math + paint helpers, posts to `http://<stackchan-host>/leds/buffer`). `lib.progress_tick(n, name, frac)` is the shared sub-stage hook; stages call it freely and `run.py` registers the StackChan paint callback at startup. Firmware endpoint is in `~/work/StackChanBridge/StackChanBridge.ino` (handler `handleLedsBuffer`).

## Vikunja report-back format

After a successful render, the skill should post a comment on the originating Vikunja task with:

1. One-line headline: `**Render complete.** episodes/<slug>/final/<slug>.mp4 — <duration> at <size> MB.`
2. Per-stage timing table (from `/tmp/macu_render_<slug>_report.json`)
3. Output paths: `.mp4`, `.srt`, `_thumbs.jpg`
4. Music bed RNG (if music enabled): which clip + offset per bed
5. Whisper match rate from stage 7 (e.g. "583/626 words matched, 93%")
6. Any notable warnings (font fallback, master cold-load timeouts, etc.)

Send the thumb strip with `SendUserFile` immediately, so August has it without opening the share.

## Files this skill writes / reads

| path | role |
|---|---|
| `/mnt/storage/shares/MACU/pipeline/` | driver + 8 stage scripts (slug-parameterized) |
| `/mnt/storage/shares/MACU/episodes/<slug>/manifest.json` | source of truth |
| `/mnt/storage/shares/MACU/episodes/<slug>/{clips,vo,frames,.rife_frames,titles,.work,final}/` | per-episode artifacts |
| `/mnt/storage/shares/MACU/assets/fonts/` | shared font dir (Better VCR + others) |
| `/mnt/storage/shares/MACU/assets/music/` | shared music-bed source dir (referenced by `manifest.music.source_dir`) |
| `/mnt/storage/shares/MACU/assets/sfx/` | shared SFX one-shot source dir (referenced by `manifest.sfx[].file`) |
| `/mnt/storage/shares/MACU/pipeline/freesound_fetch.py` | CC0 SFX acquisition helper (search → preview-mp3 download → kit-format normalize) |
| `/mnt/storage/shares/MACU/pipeline/agen_sfx.py` · `agen_music.py` · `agen_lib.py` | local generation helpers — wrap `/mnt/storage/audio-gen/agen` (AudioGen/MusicGen/Riffusion), reuse `freesound_fetch.normalize()`, GPU-gated (≥6.5 GB free) |
| `~/.config/freesound/credentials.env` | freesound.org API creds (mode 600) — `FREESOUND_API_KEY` is what the helper needs |
| `/tmp/whisper-venv/` | shared Whisper venv |
| `/tmp/macu_whisper_<slug>.json` | cached ASR output |
| `/tmp/macu_render_<slug>_report.json` | per-stage timings + paths |
| `/mnt/storage/shares/MACU/pipeline/stackchan.py` | StackChan LED progress driver (zones + paint) |
| `http://<stackchan-host>/leds/buffer` | firmware endpoint the pipeline POSTs to (single-call paint) |

## Related: the macu-render HTTP service

The **HTTP service is built and running** — `pipeline/serve.py` as systemd `macu-render.service` on `:8773`. `POST /render {slug, from_stage?, only?, episodes_dir?}` queues a job (single-worker GPU queue) and re-runs `run.py` as a subprocess with `--events-out`; `GET /events/<job_id>` streams the same `stage.started`/`stage.done`/`job.error` events as SSE. **MACU Studio** drives renders through this service (and supplies `episodes_dir` for non-default shows — see Multi-show above). This skill, by contrast, invokes `run.py` directly; the two share the exact same stage code and caches, so a Studio render and a `/macu-render` CLI run are interchangeable on the same episode dir.

## Future hooks

- **Movietone 1.19:1** crop (SSA-87 deferred) — add `crop=1024:861:0:81` to stage 8 between the subtitles filter and the encode when `manifest.assembly.output_crop` is set.

See also: `/mnt/storage/shares/MACU/pipeline/README.md` for the deeper rationale, and Max's memory files [zeroscope_drop_in_for_modelscope], [rife_ncnn_vulkan_recipe], [macu_movietone_aspect_ratio].
