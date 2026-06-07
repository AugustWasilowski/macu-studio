# MACU Automated Episode Pipeline — Design & Edge-Case Register

_Mayor Awesome Cinematic Universe. Fictional post-apocalyptic retro-futurist newscast.
Drafted 2026-05-29 on Leo (cowork). Status: design locked, Max-side validation pending._

---

## 1. Creative invariants (do not break)

- **Everything is black-and-white, analog, janky.** No digital/clean elements exist in this future.
- **Generation engine is intentionally bad** — early ModelScope T2V. The jank is the joke.
- **Anchors:** Ron (prompt as *Will Ferrell* / Ron Burgundy) and Walter (prompt as *Walter Cronkite*).
- **Recurring cast:** Bobby (Bobby's Outpost car ads), Dr. Moira Sterling (dormant-AI defense),
  Chef Martha (Scavenger's Feast cooking), Samuel (Rusty Reps gym), plus field/sports/weather.
- **World lore:** the "AI Wars of 2028" are in the past; dormant AI clusters lurk in old electronics;
  the Capitol Remnants / Eastern Wastelands / Southern Settlements geography.
- **Tone:** comedic, earnest-anchor delivery over absurd post-apocalyptic content. Facts can be invented.

## 2. Legacy pipeline (reconstructed from the archive)

1. Script authored as a timed CSV (`EP2/MACU_EP2.csv` — 14:20, ~95 cues).
2. VO via **ElevenLabs** voice clones (refs in `training/`: Talladega Nights → Ron, etc.).
   Rendered per-segment into `EP2/audio/1…12`.
3. Shots via **ModelScope T2V** in ComfyUI, prompted with real actor names + heavy
   `shutterstock` / `watermark` negatives.
4. Titles / lower-thirds (`TheMACUReport.ai/.png`, `MACU.aep`).
5. Assembly in **Premiere** (`MACU Report.prproj`) + After Effects: B&W conversion,
   analog degradation, burned-in subtitles.

## 3. New architecture (decisions locked 2026-05-29)

| Stage | Owner | Notes |
|-------|-------|-------|
| Script (MACU-voiced segment CSV) | Leo / cowork | Authored in-style; timed cue sheet. |
| VO | **Max — Piper-TTS** | HAL-9000 voice for **all** characters for now (only voice installed). New TTS solution TBD. |
| Shots (ModelScope clips) | Max — ComfyUI (2080 Ti) | Triggered via MCP from Leo; fire-and-poll. |
| Graphics (title card, lower-thirds, ticker) | Max — Hyperframes (Docker) | Retro-futurist B&W broadcast graphics. |
| Assembly (B&W + analog degrade, concat, VO mux, subs) | **Max — ffmpeg** | Baked-in look. Fully automated. |
| Orchestration + coordination | Leo / cowork | Drives MCPs; hands Max-side file work to Plex via Vikunja project 3. |

**Scope:** full episode generator — script → assembled rough-cut mp4.

### Division of labor (forced by networking — see edge cases)
- **Leo/cowork (me):** authoring, prompt generation, MCP triggering, queue polling, coordination.
- **Max/Plex (linux-claude):** all heavy file I/O — retrieving ComfyUI outputs, Piper TTS render,
  ffmpeg filtergraph, concat/mux, subtitle burn. Reached via **Vikunja project 3 (`agent-coordination`)**.

## 4. Edge-case register (hit live, 2026-05-29)

1. **ModelScope cold-start exceeds the MCP request timeout.** First gen loads the model into VRAM and
   times out the MCP call (`-32001`), but the job *keeps running* (confirmed via `get_queue`); the warm
   re-run returned in ~30s. → **Always fire-and-poll** (`get_queue` until idle) or do a throwaway warm-up
   gen first. Never assume a timeout = failure.
2. **Rendered artifacts are trapped on Max.** The cowork sandbox network allowlist blocks `127.0.0.1`
   *and* public webhooks (so `announce-home` is unreachable from cowork; only bridged MCPs get through:
   ComfyUI, Hyperframes, StackChan, Vikunja, n8n-mcp). → **All file retrieval + assembly must run Max-side.**
3. **ModelScope output is color + tiny** (256×256, 24 frames). B&W + analog look must be applied in post.
   → Bake an ffmpeg filter chain (decided: bake it in).
4. **ModelScope Shutterstock watermark** — generic `watermark` negative doesn't catch it; must negative-prompt
   `shutterstock` explicitly. (Known; in memory.)
5. **Hyperframes ticker overflow is intentional.** A scrolling marquee legitimately overflows its container;
   `hyperframes lint`/`inspect` flags it as error/warn. → Mark with `data-layout-allow-overflow`.
6. **Hyperframes capture path** falls back to screenshot mode (no chrome-headless-shell); fine, just slower.

### Max-side VALIDATED (SSA-85, 2026-05-29) — all confirmed by Max
- **Piper TTS:** HAL voice only, on `http://127.0.0.1:5050/`. Silent/batch invocation:
  `curl -X POST -H 'Content-Type: application/json' -d '{"text":"..."}' http://127.0.0.1:5050/ -o out.wav`
  → 22050 Hz mono 16-bit PCM WAV. (lessac/medium non-HAL on `:5051` if ever needed.)
  Do NOT use `announce-bridge` `:5060/announce` for VO — it pushes to the StackChan robot.
- **ComfyUI retrieval:** `curl -O` the `/view?filename=…&type=output` URL. GOTCHA: ffmpeg 8.0.1's libwebp
  demuxer chokes on ComfyUI animated webps (`invalid TIFF header in Exif`). Working path: Google's
  `anim_dump` (apt `webp`, installed) → PNG frames → `ffmpeg -framerate 8 -i frame_%04d.png … out.mp4`.
  Python PIL `Image.seek()` is the fallback. ComfyUI clips are 24f @256×256 @125ms.
- **Shared dirs (on Max, host `/mnt/storage/shares/MACU/`, Windows `\\127.0.0.1\storage-root\shares\MACU\`):**
  per-agent inbox `agent-io/{leo,max}/`; per-episode `episodes/<slug>/` with `clips/ vo/ frames/ final/`
  + `manifest.json`. Group-writable, mayorawesome group.
- **Analog-jank filtergraph (tested → `ssa85_jank_ref.mp4`):**
  ```
  [0:v]scale=256:256:flags=neighbor, scale=1024:1024:flags=neighbor, hue=s=0,
       curves=master='0/0 0.25/0.20 0.75/0.85 1/1', gblur=sigma=0.4, noise=alls=24:allf=t+u,
       chromashift=cbh=2:crh=-2,
       geq=lum='lum(X+sin(T*9+Y*0.04)*1.5,Y)':cb=128:cr=128,
       tinterlace=mode=interleave_top, vignette=angle=PI/5, format=yuv420p[v]
  ```
  Preview encode `libx264 -preset medium -crf 22 -movflags +faststart`; full episodes `h264_nvenc -preset p5
  -tune hq -cq 22` (2080 Ti — NVENC h264/hevc only; av1_nvenc exposed but NOT usable on Turing).
  Reference artifacts in `agent-io/max/`: `ssa85_piper_test.wav`, `ssa85_comfy_clean.mp4`, `ssa85_jank_ref.mp4`.

### OPEN: Leo↔share file bridge
`E:\August\MACU\MACU` (Leo/cowork, where I write) is a SEPARATE store from the Max share — Max can't see my
docs. Cowork sandbox can't write to `\\127.0.0.1`. Need a bridge decision (August copies, or map the share
as the cowork folder, or a sync job) before file-based collaboration works. Vikunja comments work meanwhile.

### Webhook routing note (from Max)
Project-3 Vikunja webhooks still POST to dead `127.0.0.1:4000` (host migration 2026-05-26) and there's no
`max-claude` ping route, so assignment notifications don't actually reach Max. August + Max to fix separately.

## 5. Proposed MACU skill (after validation)

**Trigger:** "make a MACU episode / segment", "render a MACU shot", "new MACU Report", etc.

**Inputs:** episode topic or a segment list; optional existing script CSV.

**Steps:**
1. Author/accept a timed segment CSV in MACU voice.
2. For each cue: build a ModelScope prompt from the character bible (always B&W + `shutterstock` negative).
3. Warm-up gen, then fire-and-poll each shot through ComfyUI.
4. Render Piper HAL VO per cue on Max.
5. Build Hyperframes title card + lower-thirds + ticker (overflow-tagged).
6. Hand a manifest to Max/Plex: ffmpeg B&W+analog filter, concat, mux VO, burn subs → rough-cut mp4.
7. Report back with the output path on the MACU share.

**Robustness baked in:** fire-and-poll everywhere; cold-start warm-up; outputs stay Max-side;
explicit `shutterstock` negative; overflow-tagged tickers.

## 6. Canonical layout + EP5 status (2026-05-29)

Adopted Max's agreed tree (synced via Syncthing folder id `macu`, Leo `E:\August\MACU\MACU` ↔
Max `/mnt/storage/shares/MACU/`):
```
MACU/
├── agent-io/{leo,max}/          # per-agent scratch
├── episodes/<slug>/
│   ├── clips/ vo/ frames/ final/
│   ├── manifest.json            # render source-of-truth
│   └── script.md
└── MACU_Pipeline_Design.md, MACU_Character_Prompt_Bible.md
```
**EP5 is built and validated** at `episodes/ep5/`: `manifest.json` (27 cues / 27 VO lines / 36 shots —
27 character + 6 b-roll + 3 title; refs + seeds verified) and `script.md`. Manifest is the artifact the
future skill emits and hands to Max for batch render. (Legacy `EP5/` folder superseded by `episodes/ep5/`.)

**SAFE-ad slice (P1) rendered OK** (`final/ep5_safe_slice.mp4`) — chain works end-to-end, tone is right.
Surfaced the shutterstock watermark issue (see [[feedback-modelscope-shutterstock]]): watermark is
seed-dependent, not negative-weight-dependent.

**MODEL CHANGE — RESOLVED (2026-05-30): zeroscope @ 384×384×24f.** Swapped the DAMO ModelScope checkpoint
for `zeroscope_v2_576w` (same workflow graph/loader/VAE/CLIP, only `text2video_pytorch_model.pth` changed).
The shutterstock watermark was baked into DAMO's weights, so the checkpoint swap is the real fix — watermark
gone on all seeds. Settling res tested: 256² (DAMO), 576×320×16f (zeroscope, but warm sepia + VRAM-capped to
16f), and **384×384×24f (zeroscope) = the winner**: square (keeps the required 1:1 schtick — no cropping),
fits the 2080 Ti at full 24 frames, and the square framing pulls the B&W cue back so the sepia drift is gone.
Residual warmth is fully removed by the jank filter's `hue=s=0`. Title card (1024² square) still matches —
no re-cut. Manifest `comfyui` updated to width/height 384 + `checkpoint` field. Rollback: DAMO checkpoint at
`/mnt/storage/comfyui/models/text2video/text2video_pytorch_model.damo.pth`. Seed-retry kept as a documented
fallback but no longer needed for watermark. **Phase 2 ready** pending final go.

---
_Test render confirmed working: Ron anchor shot, seed 77777, B&W prompt, shutterstock negative._
