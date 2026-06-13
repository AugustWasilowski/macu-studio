# Changelog — MACU Studio

All notable changes to MACU Studio. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions are tagged GitHub releases.

## [Unreleased]

_Nothing yet._

## [0.3.3] — 2026-06-12

### Added
- **Light / headless install.** The installer now asks (default **yes** — just hit Enter)
  before pulling the ~18 GB AI model packs. Answer `n` (or pass `--no-models`) and Studio
  installs without any local models: route stills/video/lipsync to Higgsfield or a remote
  MACU render box and the script tools to Claude Code. Pull the packs any time later by
  re-running `./deploy/fetch-models.sh` (idempotent — only missing files download).
- **Claude Code integration.** A connector card on Settings → Engines detects your `claude`
  CLI and provides copy-paste commands (pre-filled with this Studio's MCP URL) to hook up
  Claude Code or Claude Desktop. And a new **Script tools (LLM)** engine route lets shot
  lists, SFX plans, and card text generate through **your Claude subscription** (`claude -p`
  headless) instead of the local Ollama model — no GPU needed, and it works while a render
  holds the card.

### Fixed
- **Remote lipsync on long lines.** VO longer than ~7 s OOMed the remote GPU in a single
  InfiniteTalk pass; it now splits at silence boundaries and chains segments (last frame →
  next start image) automatically, and a remote-service restart fails fast instead of
  hanging the render.

## [0.3.2] — 2026-06-12

### Added
- **Higgsfield.ai integration** — cloud video generation alongside the local zeroscope path.
  Connect your Higgsfield account once in **Settings → Higgsfield** (OAuth; plan + credits shown);
  Studio is the only token holder and brokers all pipeline traffic.
  - **Cloud shots:** new per-cue shot kinds `higgsfield` (text/image-to-video; pick the model per
    shot or set an episode default) and `lipsync` (a character still animated to speak the cue's
    VO; long VO is auto-chunked at silence boundaries and chained). Mix freely with local shots.
  - **Character stills:** `still_prompt` on a character generates a reference still via Higgsfield
    image models — feeds image-to-video and lipsync.
  - **Timeline crop/trim:** cloud clips get per-shot pan/zoom crop, trim in/out, and a broadcast-
    jank toggle, editable in the Assembly timeline's metadata panel. Applied at assembly — editing
    never re-bills.
  - **Price calculator:** the Video tab shows a ☁ estimate/balance chip and any render touching
    stage 2 opens a cost dialog (per-shot credits, cached-free rows, balance check) before
    spending. Hash-keyed caching means re-renders only bill shots whose inputs actually changed.
  - MCP tools: `higgsfield_status`, `higgsfield_models`, `estimate_episode_cost`,
    `set_shot_provider`, `generate_cloud_shot`, `generate_character_still`.
- **Characters page** — a new top-level tab for the show's reusable cast. Each character
  carries prompts (video core + still prompt), a voice hint, and a gallery of reference-still
  **takes** with full provenance (engine, model, seed). Generate takes in-app via the local
  ComfyUI **Z-Image-Turbo** workflow (~5–15 s, free), Higgsfield image models (credits), or a
  remote MACU render service; pick a default take; pull characters into episodes with one
  click (the still lands pre-stamped so cloud-shot estimates stay free, and you're warned when
  replacing a still would re-bill already-paid cloud clips). Bootstrap the roster with
  "Import from episode".
- **Settings → Engines** — route each pipeline capability (zeroscope masters, character
  stills, cloud video, lipsync) to the service that should run it, with live reachability
  dots, endpoint config (local ComfyUI, opt-in remote render service), and env-override
  badges.
- **Workflow registry** — ComfyUI graphs now ship in-repo (`pipeline/workflows/*.json`);
  the installer downloads the Z-Image still models by default and the full Wan 2.1 +
  InfiniteTalk talking-head stack with `--with-talking-head` (~28 GB; powers a future local
  lipsync engine).
- **Video tab still picker** — cloud shots pick their source still visually from the
  episode's stills or the character library (syncing the take in automatically) instead of
  typing a path.
- **Lipsync engines** — lipsync shots follow Settings → Engines routing: **Higgsfield**
  (billed, chunk-and-chain), **local Wan 2.1 + InfiniteTalk** (the shipped workflow on your
  ComfyUI — whole clip in one pass, any length, free), or a **remote MACU render service**
  (e.g. a second GPU box). A `lipsync_preset` manifest knob picks fast vs quality sampling;
  the cost estimate prices by the active routing.
- **Cast builds itself** — generating a manifest from the script (and applying a shot plan)
  auto-creates library character stubs for every new speaker, ready to fill in on the
  Characters page.
- **Theme color variants** — every full theme's swatch dots are clickable: the picked color
  becomes that theme's primary and the displaced color rotates into its slot (Pretty
  Princess in blue, Slate Pro in steel mono, Dracula in ghost violet, …). Three looks per
  theme, defaults untouched.

- The first-run tutorial now covers the **Publish** stage (it previously skipped stage 6).
- **Riff lineage:** importing a downloaded riff bundle into a new local show stamps each episode's
  manifest with `riffed_from` (the source show id), preserving the original origin through forks.

### Changed
- **Docs moved out of the top bar** into the main menu (directly below Settings) to make
  room for Characters; `#docs` links still work.

## [0.2.1] — 2026-06-08

### Added
- **Update modal on launch.** Studio checks for a newer build on startup and opens the update
  modal automatically when one is available — but only *after* the first-run tutorial finishes,
  so new users aren't interrupted.
- **Manifest provenance + migration framework.** Every manifest is stamped with `schema_version`
  and the `studio_commit` that wrote it; `manifest.load()` runs in-memory migrations so older
  manifests stay readable as the schema evolves.
- **Built-in Script style guide** in the Docs tab, linked from the Script stage.
- **Publish: "Change connection"** control — re-point Studio at a different MACU Web instance
  without editing files, even when already connected.
- **Publish: content warnings.** Before pushing, Studio flags fields the web will clamp/skip
  (over-length title/description, an invalid YouTube id, a bad slug) so you catch them early.

### Changed
- **Publish → reindex is explicit.** After a push, Studio triggers the web reindex directly with
  your token instead of relying on the repo's post-receive hook, so the live page updates reliably.
- Title/description entered on the Publish tab are clamped to the web's limits on save.

### Infrastructure
- The Studio demo (demo.mayorawesome.com) now builds and deploys to Fly.

## [0.2.0] — 2026-06-07

- First tagged release: the full Script → Audio → Graphics → Video → Assembly → Publish pipeline,
  i18n (48 locales), Create Voice, Localize (dub + subs), and Publish to MACU Web.
