# Changelog — MACU Studio

All notable changes to MACU Studio. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions are tagged GitHub releases.

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
