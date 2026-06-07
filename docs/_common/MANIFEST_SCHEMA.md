# Manifest schema & conventions

`episodes/<slug>/manifest.json` is the source of truth for an episode render. As of the 2026-06
typing pass it has a **strongly-typed but lenient** model in
`studio/backend/macu_studio/models.py` (pydantic v2) and a matching TS `Manifest` interface in
`studio/frontend/src/types.ts`.

## The rules

1. **Lenient, not strict.** Every model is `ConfigDict(extra="allow")` and almost every field is
   `Optional`. Validation is a *structural gate* — it catches genuinely malformed manifests (cues
   not a list, a cue without an `id`, a seed that isn't an int) but never rejects a valid existing
   file or an unknown future field.
2. **LOCKED blocks are opaque.** `comfyui` (384×384×24f, steps 30, cfg 15, zeroscope checkpoint) and
   `subtitles` (Better VCR font + `force_style`) are modeled as empty `extra="allow"` classes. Do
   not regress them; do not add `FontName=`/`Fontsize=` inside `subtitles.force_style` (libass
   last-key-wins).
3. **Save preserves the raw dict.** `manifest.save()` validates through the models but writes the
   **original dict**, never `model_dump()`. So round-tripping a manifest is byte-equivalent for the
   LOCKED blocks. Never persist a dumped model.
4. **Manifest shape vs derived rows.** The models above describe the on-disk manifest. The API
   endpoints `/cues`, `/shots`, `/titles` return *derived rows* (manifest + filesystem status) —
   a different, flatter shape (`Cue`/`Shot`/`TitleAsset` in `types.ts`). Don't confuse the two.

## Top-level shape

```
episode, title, version, authored_by?, notes?      — metadata
voice          { default, endpoints, format, out_pattern, speaker_map{<SPEAKER>: VoiceProfile} }
comfyui        — LOCKED, opaque
style          { suffix, negative }
render_rule    — prose contract the assembler follows
title_assets   { <key>: TitleAssetObj | string }
music?         { enabled, source_dir, clips[], beds[] }
subtitles      — LOCKED, opaque
characters     { <key>: {seed, core} | string }
broll          { <key>: <core prompt string> }
cues           [ Cue ]
sfx?           [ {file, cue, at, gain_db?, ...} ]
```

`Cue`: `{id (required), segment?, speaker?, vo?, shots[], hold_seconds?, hold_style?, no_subs?,
pad_seconds?}`. `Shot` kinds: character `{kind, who, seed}`, broll `{kind, who}`, title
`{kind, asset, fill?}`.

## Asset versioning sidecar

`episodes/<slug>/.versions.json` (managed by `versions.py`) tracks archived prior generations of
versioned assets. The **active** version always keeps the canonical filename the pipeline reads, so
the render path is unchanged. History lives under `<dir>/.versions/<key>/<name>.vN.<ext>`. Keys:
`cue:<id>`, `shot:<key>`, `ythumb:<slug>`. This sidecar (and the `.versions/` dirs) are episode
working data — not git-synced.
