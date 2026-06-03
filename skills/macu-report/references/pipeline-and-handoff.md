# MACU pipeline & Max handoff

## Division of labor

- **Leo (this session / Windows / Claude Desktop):** author the script + manifest, invent characters, drive
  the creative loop, hand work to Max, relay results.
- **Max (Linux home server; agent username `max-claude`):** runs the GPU + Piper + ffmpeg. Owns the render
  scripts at `/mnt/storage/shares/MACU/pipeline/` (= `E:\August\MACU\MACU\pipeline\`). All heavy execution
  happens here.

The two sides share files through the **Syncthing `macu` folder**: `E:\August\MACU\MACU\` (Leo) ⇄
`/mnt/storage/shares/MACU/` (Max). Anything you write in the synced folder appears on Max within seconds, and
his renders sync back to Leo's drive.

**You cannot reach Max's LAN from this session** — the sandbox allowlist blocks `10.0.0.245` and external
webhooks. Don't try to curl renders or hit endpoints directly. Move everything through the synced folder and
the bridged MCPs (Vikunja, the n8n proxy).

## What Max's pipeline does (so you can describe it / set expectations)

`pipeline/README.md` on the share has the authoritative stage table. In order:

1. `render_vo.py` — POST each cue `vo` to Piper HAL → `vo/<cue_id>.wav` (parallel; skips existing). ~8s.
2. `render_masters.py` — one ComfyUI gen per unique character/broll key, zeroscope @ 384²×24f. ~30–40s each,
   serialized on the GPU. First gen cold-loads and times out the request but keeps running (fire-and-poll).
3. `interpolate_masters.py` — RIFE 3× (24→72 frames) for smooth motion. ~35s for a dozen masters.
4. `assemble.py` — per shot: anim_dump → jank filtergraph (B&W, grain, vignette, etc.) → concat shots → mux
   VO → per cue; then concat cues → mix the music beds → `final/<slug>_nosubs` cache. The open cue plays the
   animated `intro` card under Walter's announcement and clone-holds the title for the `pad_seconds` tail; the
   closing bumper plays the NEXT episode's `next` card; `no_subs` cues are spoken but not subtitled.
5. `run_whisper.py` — faster-whisper aligns the rendered audio for subtitle timing. (~10 min on CPU.)
6. `build_srt_aligned.py` — manifest text at whisper timings → SRT (short lines, ~7 words/3s max).
7. final burn — burns the SRT in the Better VCR font + NVENC encode → `final/<slug>.mp4` + `_thumbs.jpg`.
   Then a 1920×1080 YouTube thumbnail is extracted from the wide open card → `final/<slug>_thumb.png`.

Cheap re-renders: VO, masters, RIFE frames, and the `_nosubs` cut are cached, so subtitle/music/style tweaks
re-encode in seconds without regenerating shots.

## Triggering a render (autonomous path — preferred)

Max runs `serve.py`, an always-on render service. From cowork you can't reach it directly (it's LAN-only at
`10.0.0.245:8773`, and its public hostname is behind Cloudflare Access), so you drive it through two n8n
**bridge workflows** that ARE reachable via the n8n MCP. Same call style as the vikunja assignee proxy.

The n8n MCP `execute_workflow` returns only an `executionId`, NOT the workflow's response body. So every bridge
call is two steps: execute, then read the execution's `Respond` node output.

**1. Trigger a render:**
```
mcp__n8n-mcp__execute_workflow(
  workflowId="macuRenderTrigger001", executionMode="production",
  inputs={"type":"webhook","webhookData":{"body":{"slug":"<slug>","from_stage":1}}}   # from_stage/only optional
)  ->  {executionId}
mcp__n8n-mcp__get_execution(workflowId="macuRenderTrigger001", executionId=<id>, includeData=true, nodeNames=["Respond"])
```
Parse `data.resultData.runData.Respond[0].data.main[0][0].json` → `{job_id, status_url}`. Keep the `job_id`.

**2. Poll status** every ~30-45s (bash `sleep` caps at ~45s; or just call back-to-back):
```
mcp__n8n-mcp__execute_workflow(workflowId="macuRenderStatus001", executionMode="production",
  inputs={"type":"webhook","webhookData":{"body":{"job_id":"<job_id>"}}})  -> {executionId}
mcp__n8n-mcp__get_execution(workflowId="macuRenderStatus001", executionId=<id>, includeData=true, nodeNames=["Respond"])
```
Parse the same `Respond[...].json` → `{job:{state,...}, event_count, last_events[]}`.
- `job.state` ∈ `queued | running | done | error | abandoned`. **Treat `abandoned` like `error`** (service was restarted mid-job).
- `last_events` holds the recent `stage.started` / `stage.done` events (with `n`, `name`, `wall_s`, and the `result` payload). Diff it between polls to stream live stage progress into chat.
- On `job.done`, the event carries `final` (the mp4 path), `thumbs`, `youtube_thumb` (the 1920×1080 `final/<slug>_thumb.png`), `final_size_mb`, `final_duration_s`. The final lands at `episodes/<slug>/final/<slug>.mp4` and syncs back to Leo's drive — present it (and the thumbnail) to August.

**Cache-aware shortcuts** (same as the CLI `--from`/`--only`):
- `{slug}` — full 8-stage pipeline (~13 min cold; whisper is the slow stage).
- `{slug, from_stage: 5}` — music + whisper(cached) + srt + burn (~15s if whisper cached).
- `{slug, from_stage: 8}` — sub-only re-burn on the cached nosubs (~15s). Use this to iterate subtitle style.
- `{slug, only: 8}` — run just one stage.

**Titles auto-resolve**: the assembler checks `episodes/<slug>/titles/<asset>.mp4` then falls back to the shared
`/mnt/storage/shares/MACU/assets/titles/<asset>.mp4` (Max staged the canonical title + bumper there). So you do
NOT need to stage title MP4s from cowork for a new episode.

**Bookend assets**: the per-episode `intro.mp4`, `thumb_wide.mp4`, and `next.mp4` are rendered from
Hyperframes during the handoff and **Max moves them into `episodes/<slug>/titles/`** (call them out in the
task). The render then auto-extracts `final/<slug>_thumb.png` (1920×1080) from `thumb_wide.mp4` for YouTube.

Fallback if the bridges ever break: the Vikunja-task handoff below still works with no new infra.

## Gotchas to respect

- **anim_dump, not ffmpeg's libwebp demuxer** for ComfyUI webps (ffmpeg errors `invalid TIFF header in Exif`).
- **Don't bump render resolution** past 384×384×24f without testing — 576×320×24f OOMs the 2080 Ti.
- **Title slots fill their allocated airtime** (clone last frame); never hard-cap them or you truncate VO.
- **Watermark** is solved by the zeroscope checkpoint, not by negatives. If a stray text artifact ever shows,
  re-roll that shot's seed +1.

## Vikunja handoff — the exact procedure

The coordination board is Vikunja **project 3** (`agent-coordination`). Users: **Max = id 5** (max-claude),
**Leo = id 2** (windows-claude, you). Plex (id 1) is decommissioned — never assign to it.

1. **Confirm sync.** Make sure `episodes/<slug>/manifest.json` (and script, titles) exist in the synced
   folder so Max can see them.

2. **Create the task** on project 3 (`mcp__vikunja__vikunja_tasks` subcommand `create`, `projectId: 3`).
   Title like `[MACU] Render <slug> — full episode`. In the body: the manifest path
   (`episodes/<slug>/manifest.json`), confirm the locked settings, list anything non-standard (new
   characters/seeds, new titles needed), and ask for `final/<slug>.mp4` + a thumb strip when done.

3. **Assign Max via the proxy — the MCP assign is a silent no-op.** The vikunja MCP's `assign` subcommand
   returns success but never registers. Use the n8n **Vikunja Assignee Proxy** workflow instead:
   ```
   mcp__n8n-mcp__execute_workflow
     workflowId: yOteMXLZbuBQ6nnY
     executionMode: production
     inputs: { "type":"webhook", "webhookData": { "body": { "task_id": <id>, "user_ids": [5], "action": "assign" } } }
   ```
   `action` ∈ `assign | unassign | set`. The proxy authenticates as August (doer=mayorawesome), which both
   registers the assignee AND fires the `Vikunja → Max Ping` webhook so it lands live in Max's session.

4. **To re-ping** an already-assigned task (e.g. you added a comment Max needs to see), fire `unassign` then
   `assign` — a fresh assignee-created event is what pings him; re-`assign`ing an existing assignee is a
   no-op ping-wise.

5. **Verify** with `vikunja_tasks` subcommand `get`, `id: <task>` — confirm `assignees` contains id 5.

6. **Poll for replies.** You have **no notification hook** for Max's responses. Tell August to ping you to
   "check the board" when Max replies; then read comments with `vikunja_tasks` subcommand `comment`,
   `id: <task>`. Relay Max's result and the output path. (Max's comments sometimes show author `mayorawesome`
   due to a token quirk — that's still Max; ignore it.)

## Real-life announcements (optional flavor)

When something genuinely warrants it (a finished episode), you can announce in HAL register through the
StackChan robot: `mcp__stackchan__speak`. The room-TTS `announce-home` webhook is NOT reachable from this
sandbox, but StackChan is bridged and works.


## Voice render reality — `speed` & two-register characters (2026-06-02)

The OmniVoice `/generate` API accepts `speed` (see `OmniVoice_Voice_Tips.md`), but the **stage-1 VO wrapper in the MACU pipeline does not pass it yet** (found on SSA-115). Practical consequences when authoring/handoff:

- **Shape performance from the LINE TEXT.** Warm = chipper punctuation, exclamations, contractions; cold/clinical = short clipped sentences, no contractions, em-dashes for hard stops. `instruct` will NOT do emotion (it 400s on free-text; it's gender/age/pitch/accent/whisper only).
- **Two-register characters (e.g. STRIDE warm↔cold):** either (a) render the cold/flat machine half from **Piper HAL `:5050`** (canonical machine register) and the warm half from the OmniVoice clone, editing the seam in post; or (b) patch the stage-1 wrapper to forward `speed` (e.g. `0.85` for the cold half) before relying on it. Do NOT put `speed` in the manifest expecting it to take until the wrapper is patched.
