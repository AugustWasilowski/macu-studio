# MACU pipeline & local render

## Where it all runs

You are **Max** (Linux home server, agent `max-claude`) and you own the whole thing — authoring AND the
GPU + Piper + ffmpeg render. Everything lives under `/mnt/storage/shares/MACU/`; the render scripts are at
`/mnt/storage/shares/MACU/pipeline/` and the local services are on this box:

- **ComfyUI** `http://127.0.0.1:8188/` (zeroscope T2V masters — RTX 2080 Ti)
- **OmniVoice** `http://127.0.0.1:3900/` (cloned character voices; ephemeral container, stage 1 owns its lifecycle)
- **Piper HAL** `http://127.0.0.1:5050/` (the calm machine register for AI/appliance characters)

That same tree is `S:\MACU\` on August's Windows box (`/mnt/storage/shares/` ⇄ `S:\`), so anything you write
under `episodes/<slug>/final/` is visible to him with no sync wait.

> **History:** this skill was authored on Leo (August's Windows box), which wrote scripts/manifests and shipped
> the render to Max over a Syncthing `macu` folder + the Vikunja board + n8n bridge workflows. Max now does
> both halves locally, so all of that cross-machine plumbing is gone — render with the `macu-render` skill
> directly (below).

## What the pipeline does (so you can describe it / set expectations)

`pipeline/README.md` on the share has the authoritative stage table. In order:

1. `render_vo.py` — POST each cue `vo` to Piper HAL → `vo/<cue_id>.wav` (parallel; skips existing). ~8s.
2. `render_masters.py` — one ComfyUI gen per unique character/broll key, zeroscope @ 384²×24f. ~30–40s each,
   serialized on the GPU. First gen cold-loads and times out the request but keeps running (fire-and-poll).
3. `interpolate_masters.py` — RIFE 3× (24→72 frames) for smooth motion. ~35s for a dozen masters.
4. `assemble.py` — per shot: anim_dump → jank filtergraph (B&W, grain, vignette, etc.) → concat shots → mux
   VO → per cue; then concat cues → `final/<slug>_nosubs` cache. The open cue plays the
   animated `intro` card under Walter's announcement and clone-holds the title for the `pad_seconds` tail; the
   closing bumper plays the NEXT episode's `next` card; `no_subs` cues are spoken but not subtitled.
   **At its tail it runs stage 4b (`stage_4b_graphics.py`)**: bakes any spanning title-card graphics
   (`manifest.overlays[]`) onto the assembled video — `insert` mode cuts the card full-frame across its span,
   `overlay` mode composites it over the footage (alpha `.webm` or keyed-black opaque). Audio is untouched, so
   stage 5+ are unaffected; a clean `_nosubs_clean` snapshot lets overlay-only edits re-composite without a full
   re-assemble. No-op when `overlays` is empty.
5. `run_whisper.py` — faster-whisper aligns the rendered audio for subtitle timing. (~10 min on CPU.)
6. `build_srt_aligned.py` — manifest text at whisper timings → SRT (short lines, ~7 words/3s max).
7. final burn — burns the SRT in the Better VCR font + NVENC encode → `final/<slug>.mp4` + `_thumbs.jpg`.
   Then a 1920×1080 YouTube thumbnail is extracted from the wide open card → `final/<slug>_thumb.png`.

Cheap re-renders: VO, masters, RIFE frames, and the `_nosubs` cut are cached, so subtitle/music/style tweaks
re-encode in seconds without regenerating shots.

## Triggering a render (local — just run it)

The render runs right here. Invoke the **`macu-render`** skill (or call its driver directly); it's idempotent
and cache-aware, so partial-failure re-runs and tweak passes are cheap:

```
/macu-render <slug>            # full 8-stage cold render (~13 min; whisper is the slow stage)
/macu-render <slug> --from 5   # music + whisper(cached) + srt + burn (~15s if whisper cached)
/macu-render <slug> --from 8   # sub-only re-burn on the cached nosubs (~15s) — iterate subtitle style
/macu-render <slug> --only 8   # run just one stage
```

Equivalently `python3 /mnt/storage/shares/MACU/pipeline/run.py <slug> [--from N|--only N]`. Watch the stages
stream by in your own output — there's no job_id to poll, no webhook, no `serve.py` round-trip; you're the one
running it. (`pipeline/serve.py` on `:8773` and the old n8n `macuRenderTrigger001`/`macuRenderStatus001`
bridge workflows existed so off-box callers could drive a render remotely — irrelevant when you're on the box.)

When it finishes, the final lands at `episodes/<slug>/final/<slug>.mp4` (plus `_thumbs.jpg` strip and the
1920×1080 `final/<slug>_thumb.png` YouTube still). `run.py` also writes per-stage timings to
`/tmp/macu_render_<slug>_report.json`. Present the mp4 path + thumbnail to August.

**Titles auto-resolve**: the assembler checks `episodes/<slug>/titles/<asset>.mp4` then falls back to the
shared `/mnt/storage/shares/MACU/assets/titles/<asset>.mp4` (the canonical title + bumper are staged there).
So you do NOT need to pre-stage title MP4s for a new episode.

**Bookend assets**: the per-episode `intro.mp4`, `thumb_wide.mp4`, and `next.mp4` are rendered from
Hyperframes; move them into `episodes/<slug>/titles/` before the render. The render then auto-extracts
`final/<slug>_thumb.png` (1920×1080) from `thumb_wide.mp4` for YouTube.

## Gotchas to respect

- **anim_dump, not ffmpeg's libwebp demuxer** for ComfyUI webps (ffmpeg errors `invalid TIFF header in Exif`).
- **Don't bump render resolution** past 384×384×24f without testing — 576×320×24f OOMs the 2080 Ti.
- **Title slots fill their allocated airtime** (clone last frame); never hard-cap them or you truncate VO.
- **Watermark** is solved by the zeroscope checkpoint, not by negatives. If a stray text artifact ever shows,
  re-roll that shot's seed +1.

## Vikunja — report back when a render was requested as a task

You don't hand renders off to anyone anymore — you run them. The only Vikunja interaction left is the
**report-back** when a render arrived as a task. The coordination board is project **3** (`agent-coordination`);
you are **Max = id 5** (`max-claude`).

If a `[MACU]` + render task assigned to you kicked off this work, post a comment on that task when the render
finishes — the `macu-render` report-back format:

1. One-line headline: `**Render complete.** episodes/<slug>/final/<slug>.mp4 — <duration> at <size> MB.`
2. The per-stage timing table from `/tmp/macu_render_<slug>_report.json`.
3. Output paths (`.mp4`, `.srt`, `_thumbs.jpg`) and the whisper match rate from stage 7.
4. Any notable warnings (font fallback, master cold-load timeouts, etc.).

Use the vikunja MCP `vikunja_tasks` subcommand `comment`, `id: <task>`. (Your comments sometimes show author
`mayorawesome` due to a token quirk — that's still you; ignore it.) Otherwise — a render you started yourself,
in conversation with August — just relay the result in chat; no task needed.

## Real-life announcements (optional flavor)

When something genuinely warrants it (a finished episode), announce in HAL register through the StackChan
robot: `mcp__stackchan__speak`. The room-TTS `announce-home` webhook is also reachable from Max now at
`http://127.0.0.1:5060/` (it forwards to StackChan `/play`).


## Voice render reality — `speed` & two-register characters (2026-06-02)

The OmniVoice `/generate` API accepts `speed` (see `OmniVoice_Voice_Tips.md`), but the **stage-1 VO wrapper in the MACU pipeline does not pass it yet** (found on SSA-115). Practical consequences when authoring/handoff:

- **Shape performance from the LINE TEXT.** Warm = chipper punctuation, exclamations, contractions; cold/clinical = short clipped sentences, no contractions, em-dashes for hard stops. `instruct` will NOT do emotion (it 400s on free-text; it's gender/age/pitch/accent/whisper only).
- **Two-register characters (e.g. STRIDE warm↔cold):** either (a) render the cold/flat machine half from **Piper HAL `:5050`** (canonical machine register) and the warm half from the OmniVoice clone, editing the seam in post; or (b) patch the stage-1 wrapper to forward `speed` (e.g. `0.85` for the cold half) before relying on it. Do NOT put `speed` in the manifest expecting it to take until the wrapper is patched.
