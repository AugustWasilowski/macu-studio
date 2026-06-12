# Changelog — MACU Studio

All notable changes to MACU Studio. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions are tagged GitHub releases.

## [Unreleased]

### Added
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

### Changed
- **Docs moved out of the top bar** into the main menu (directly below Settings) to make
  room for Characters; `#docs` links still work.
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
- The first-run tutorial now covers the **Publish** stage (it previously skipped stage 6).
- **Riff lineage:** importing a downloaded riff bundle into a new local show stamps each episode's
  manifest with `riffed_from` (the source show id), preserving the original origin through forks.

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
