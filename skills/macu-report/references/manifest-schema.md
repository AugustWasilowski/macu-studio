# MACU manifest.json — schema & conventions

`episodes/<slug>/manifest.json` is the single source of truth Max's pipeline renders from. Build it to match
this exactly. Validate with `scripts/validate_manifest.py` before handoff.

**Slug & the `episode` field:** the `episode` value equals the folder slug. Numbered episodes are `epN`
(`ep6`); one-off bits use a short descriptive slug (`everwell-bit`, `last-clock`). Everything for the piece
lives under `episodes/<slug>/`.

Everything you need is reproduced in this file — the locked blocks below are complete, so you do NOT need to
open the ep5 manifest to build a new one (ep5 is just a fuller worked example if you want one).

## Top-level shape

```json
{
  "episode": "ep6",
  "title": "The MACU Report — Episode 6",
  "version": 1,
  "authored_by": "max",
  "voice":    { ... },          // Piper HAL — copy as-is
  "comfyui":  { ... },          // LOCKED render settings — copy as-is, do not regress
  "style":    { "suffix": "...", "negative": "..." },   // from the bible
  "render_rule": "...",         // prose contract the assembler follows — copy as-is
  "title_assets": { ... },
  "music":    { ... },          // intro/outro theme beds
  "subtitles":{ ... },          // Better VCR font
  "characters": { "<key>": { "seed": N, "core": "..." }, ... },
  "broll":      { "<key>": "<core prompt>", ... },
  "cues": [ ... ]
}
```

## LOCKED blocks — copy verbatim (changing these breaks the proven pipeline)

```json
"voice": {
  "default":   { "engine": "piper", "endpoint": "http://127.0.0.1:5050/" },
  "endpoints": { "piper": "http://127.0.0.1:5050/", "omnivoice": "http://127.0.0.1:3900" },
  "format": "wav 24000Hz mono s16",
  "out_pattern": "vo/<cue_id>.wav",
  "speaker_map": {
    "RON":        { "engine": "omnivoice", "profile_id": "37e05336", "voice_name": "Burgundy" },
    "THE VENDOR": { "engine": "piper", "voice_name": "HAL" }
  }
},
"comfyui": {
  "workflow": "will-smith-modelscope-t2v",
  "checkpoint": "zeroscope_v2_576w",
  "endpoint": "http://127.0.0.1:8188/",
  "frames": 24, "width": 384, "height": 384, "steps": 30, "cfg": 15, "extract_fps": 8,
  "out_pattern": "clips/<shot_id>.webp"
}
```
> **Endpoints are local on Max.** The services run on this box, so the canonical host is `127.0.0.1`
> (OmniVoice in particular binds loopback-only, and stage 1 hardcodes `http://127.0.0.1:3900` in `lib.py`
> regardless of what the manifest says). Older episodes carry `http://10.0.0.245:...` here — that still works
> from Max (Piper/ComfyUI bind `0.0.0.0`), so you don't need to rewrite existing manifests; just use
> `127.0.0.1` in new ones.
**Why locked:** zeroscope_v2_576w (not DAMO ModelScope) removes the baked-in shutterstock watermark; 384×384
keeps the required 1:1 square, fits the 2080 Ti's 11 GB at 24 frames, and pulls the B&W cue harder than 16:9.
Bumping to 576×320×24f triggers ComfyUI lowvram offload and crashes the temporal modules — don't.

```json
"music": {
  "enabled": true,
  "source_dir": "/mnt/storage/shares/MACU/assets/music",
  "clips": ["60s_big_band_00.mp3","60s_big_band_01.mp3","60s_big_band_02.mp3","60s_big_band_03.mp3"],
  "clip_seconds": 19.8, "gain": 0.16, "fade_in": 1.5, "fade_out": 2.5, "random": true,
  "beds": [
    { "name": "intro", "anchor": "start", "cues": ["c01","c02","c03"], "max_seconds": 14 },
    { "name": "outro", "anchor": "end",   "cues": ["<last-2-cue-ids>"], "max_seconds": 14 }
  ]
},
"subtitles": {
  "font": "Better VCR",
  "fontsdir": "/mnt/storage/shares/MACU/assets/fonts",
  "font_file": "/mnt/storage/shares/MACU/assets/fonts/BetterVCR.ttf",
  "fontsize": 18,
  "force_style": "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=32,Alignment=2"
}
```
**Do NOT put `FontName=` or `Fontsize=` inside `force_style`.** Stage 8 prepends its own `FontName=<resolved>,Fontsize=<n>` from the `font`/`fontsize` fields, and libass takes the LAST occurrence of a key — a stale `FontName=Better VCR` in the string overrides stage 8's fc-scan'd family (`Better VCR-JP`) and silently drops subtitles back to the default font. Keep `font: "Better VCR"` (fc-scan resolves it to the real family automatically; don't hard-code `Better VCR-JP`). `force_style` carries only the non-font style keys (colours, border, margin, alignment).
Update each bed's `cues` to this episode's actual intro (first ~3 cues) and outro (last ~2 cues) — replace the
`<last-2-cue-ids>` placeholder with real ids or validation fails. On a **short bit (≲6 cues)** the two beds
overlap: use one cue each (intro = first cue, outro = last cue) or set `music.enabled` to `false` and skip the
theme entirely.

## Voices & casting (`voice.speaker_map`)

Characters have distinct voices now (via the OmniVoice TTS), not one HAL for everyone. Casting is per episode:

- `voice.default` / `voice.endpoints` / `voice.format` (24 kHz) / `voice.out_pattern` are fixed — copy them.
- `voice.speaker_map` is **authored per episode**. Keys are the **exact cue `speaker` strings**, case- and
  punctuation-sensitive (`RON`, `MOTHER MARIGOLD`, `TALLY MAN`, `MR. CRICKET`, `THE VENDOR`, `SAFE`, …). Each
  value is `{ "engine": "omnivoice"|"piper", "profile_id"?: "<8-hex>", "voice_name"?: "<display>" }`.
  - OmniVoice voices need a `profile_id` (and a `voice_name` for readability).
  - Piper has one voice, **HAL** — no profile_id, just `{ "engine": "piper", "voice_name": "HAL" }`.
- **Every distinct speaker in `cues[]` should have a `speaker_map` entry.** Unmapped speakers silently fall
  back to `voice.default` (Piper HAL) — fine for a deliberate robot, wrong for a person.

> **Live voice docs (authoritative — prefer these over the snapshot table below):**
> - `OmniVoice_Voice_Roster.md` — the live index of every cloned voice by character (profile_id, timbre,
>   status). If it and the running registry (`GET :3900/profiles`) diverge, the registry wins.
> - `OmniVoice_Voice_Tips.md` — voice SHAPING: the `speed` / `seed` / `instruct` / `guidance_scale` knobs and
>   the full `/generate` reference. A two-register character (e.g. STRIDE) can be ONE profile with two
>   `instruct` strings ("warm, chipper" vs "flat, robotic") — no second clone needed; `speed=0.85` slows a
>   rushed read before you ever re-clone.
> When you clone, recast, or approve a voice, UPDATE `OmniVoice_Voice_Roster.md` (and the Bible casting intent).

### Voice catalog (cloned OmniVoice profiles — IDs are persistent)

| voice_name | profile_id | sounds like |
|---|---|---|
| Burgundy | `37e05336` | Will Ferrell / Ron Burgundy — anchor swagger |
| Walter | `9c12dfe7` | Walter Cronkite — measured TV anchor |
| Laura | `f8986fd9` | friendly youngish female |
| Martha | `ab69d122` | Martha Stewart — measured female |
| David | `bea3e4c2` | David Attenborough — distinguished narrator (reads as creepy gravitas) |
| Howie | `973d5617` | "How It's Made" cheerful host |
| Seth | `112c06ba` | Seth Rogen — nasal, nervous laugh |
| Announcer | `a39a24a3` | generic commercial announcer pitch |
| Popiel | `bc466292` | Ron Popiel — manic infomercial pitch |
| Snoop | `31649b70` | Snoop Dogg — laid-back drawl (weaker clone, short ref) |
| **HAL** (piper) | — | calm, formal, faintly menacing machine — **reserve for AI/appliance characters** |

Need a voice that isn't here? Clone one locally: `/mnt/storage/shares/MACU/voices/clone_one.sh <Name> <ref.mp3>`,
which prints a new persistent `profile_id`. (`docker start omnivoice` first — the container is stopped between
renders; stop it again afterward to keep the GPU clean for ComfyUI.)

### EP5 casting (worked example)

RON→Burgundy, WALTER→Walter, MOTHER MARIGOLD→Laura, TALLY MAN→David, BARTHOLOMEW→Seth, MR. CRICKET→Snoop,
NORM→Howie, ANNOUNCER→Announcer, and the two machines — **THE VENDOR→HAL, SAFE→HAL** (Piper). HAL on the
appliances is the joke; everyone else gets a real voice.

### Voice gotchas

- **Stage 1 (VO) runs on Max** — OmniVoice binds to `127.0.0.1:3900` (loopback-only), which is exactly where
  you are; there's no remote path and none is needed.
- **Serial**: ~3 s per OmniVoice cue, ~0.5 s per Piper cue (OmniVoice asserts under concurrency).
- **VO-only iteration**: change `voice.speaker_map` or a cue's text, delete just the affected `vo/<cue>.wav`,
  then re-render `--from 1`. Stages 4-8 cascade. (The stage-1 cache is now keyed by per-cue text+voice hash in
  `vo/.cache.json`, so a manifest edit that doesn't touch a cue's own inputs no longer forces its wav to
  regen — see the `macu-render` skill.)

## cues[] — one per spoken line

```json
{
  "id": "c01", "segment": "cold_open", "speaker": "RON",
  "vo": "Good evening, survivors. I'm Ron, broadcasting from the capital remnants...",
  "shots": [
    { "id": "c01_s1", "kind": "character", "who": "ron", "seed": 77777 }
  ]
}
```

- `vo` is the spoken line — clean prose, no stage directions. It becomes BOTH the Piper VO and the burned-in
  subtitle.
- `shots[]` is 1+ shots shown across that cue's airtime. **Per-shot screen time = cue VO duration ÷ number of
  shots** (the assembler computes this at run time from the rendered wav — so VO must render before assembly;
  you don't specify durations). Use 2 shots when you want a cutaway (e.g. character then b-roll).
- Shot kinds:
  - `{"kind":"character","who":"<characters key>","seed":N}` — seed should match `characters[who].seed`.
  - `{"kind":"broll","who":"<broll key>"}` — no seed.
  - `{"kind":"title","asset":"macu_report_title"|"macu_report_bumper"|"thumb"}` — looked up under
    `episodes/<slug>/titles/<asset>.mp4`. Add `"fill":"loop"` to loop the card across its whole slot (the
    open card); default holds the last frame (`tpad`).

## Authoring conventions (from the proven EP5 run)

- **One seed per character; one master render reused across all their cues.** If `safe` appears in 5 cues, it
  generates once and the assembler reuses it. This is why episodes are cheap (~28 unique gens for a 36-shot
  episode). Only give a character multiple seeds if you deliberately want different looks.
- **B-roll keys can repeat** (e.g. `empty_room` reused as a recurring location) and share one master. Want a
  *different* empty room per cue? Give them distinct keys (`empty_room_a`, `empty_room_b`).
- **Title slots fill their full per-shot share** — the assembler clones the last title frame (`tpad`) if the
  title MP4 is shorter than the slot. Never cap a title to a fixed short duration; that truncates VO.
- **`render_rule`** is a prose field the assembler reads; copy EP5's verbatim (it documents full_prompt =
  core + style.suffix, negative = style.negative, fire-and-poll, anim_dump → frames → jank → concat → mux VO
  → subtitles → final mp4).
- **Per-shot `seed` override** is allowed (`shots[*].seed`) for when one character master comes out wrong and
  you want to re-roll just that instance without touching the others.

## Silent beats (`hold` cues) & SFX

**Silent / no-dialogue cues** (comedic reaction beats, animated moments): a cue with `vo: ""` plus
`hold_seconds: N`. Max generates a silent wav of that length so the stage-4 timing math is untouched, and
burns no subtitle. Two modes — set `hold_style`:
- `"freeze"` (Max's default for no-dialogue cues): the shot FREEZES on its first frame. This is the
  **double-take** technique — rapid still cutaways (Ron → Walter → Ron) that read as deadpan reaction stills.
- `"play"`: the shot PLAYS OUT fully (animated). Use when the MOTION is the joke/payoff (e.g. the moon
  blinking out, a slow wave, a final fade). Max must NOT first-frame these — call it out in the handoff too,
  since freeze is the default.

**SFX one-shots**: a top-level `sfx` block (sibling to `music`) — `{ "cue", "file", "gain", "at": "start|end" }`
entries mixed at a cue's timestamp via the same stage-5 adelay→amix chain as music beds. `file` is the bare
basename (no path), resolved as `assets/sfx/<file>`. Missing file → skipped gracefully. **Three ways to get a
file into `assets/sfx/`** (all normalize to 24 kHz mono s16 / −3 dBFS): (1) **`agen` generation** — bespoke
text-to-foley for any sound the script calls for (bonk, car engine, door slam): `python3
pipeline/agen_sfx.py "<prompt>" <basename>` or the Studio Audio-panel "Generate (agen)" toggle; (2) **freesound
CC0** via `pipeline/freesound_fetch.py "<query>" <basename>`; (3) **ffmpeg lavfi synth** for tonal sounds.
agen output is public-domain (de novo) and reproducible (prompt + seed logged). (Both `hold` cues and the `sfx`
block were added in the ep10 work; `agen` generation added 2026-06.)

**Generated music beds**: `music.clips[]` isn't limited to the big-band theme — generate a bed from a prompt
with `python3 pipeline/agen_music.py "<prompt>" <basename> [--engine music|riff]` (or the Studio music-gen
endpoint), then add `<basename>.wav` to `music.clips[]`. `music` = MusicGen (warbly, drifts past ~15–20s);
`riff` = Riffusion (tape-degraded lo-fi). Both land in `assets/music/` and fit the jank — use them for sickly
jazz, broken-broadcast stings, ominous drones, etc. Same GPU gate as SFX (won't run during a render).

## Episode bookends — the animated open & the next-episode bumper

Every episode opens on an **animated intro** (Walter's gag VO over `intro.mp4`) and closes on a **bumper**
showing the NEXT episode's title card. Author both as cues; the pipeline handles the mechanics. Full spec +
templates: `references/thumbnail.md`.

**Open — first cue `c00`:**

```json
{
  "id": "c00", "segment": "intro", "speaker": "WALTER",
  "vo": "The MACU Report! In black and white! Tonight's episode: A safe AI, a hungry vending machine, and the Bloom Hour.",
  "no_subs": true,
  "pad_seconds": 2.0,
  "shots": [ { "id": "c00_s1", "kind": "title", "asset": "intro" } ]
}
```

- `asset:"intro"` is the animated open (TONIGHT → THE MACU REPORT → this episode's title card with flicker),
  which **plays once then clone-holds** the title — do NOT add `fill:"loop"`. `pad_seconds` holds the title
  ~2s past Walter's VO (audio silence-padded to match); `no_subs:true` keeps the gag in the audio only — the
  card shows the *real* title, Walter announces a *different* one (+ brags "in black and white!"). Add
  `intro` to `title_assets`.
- Keep the intro animation (~5–6s) shorter than Walter's VO so it plays in full. Add `c00` to the **intro**
  music bed's `cues` so the theme plays under the whole open.

**Close — last cue (the bumper):** Walter teases next over the NEXT episode's title card.

```json
{ "id": "c99", "segment": "next_time", "speaker": "WALTER",
  "vo": "Tune in for tomorrow's episode: Cavity or a Career.",
  "no_subs": true, "pad_seconds": 1.5,
  "shots": [ { "id": "c99_s1", "kind": "title", "asset": "next" } ] }
```

- **Mon–Thu:** `"Tune in for tomorrow's episode: <next subtitle>."` over `next.mp4` (the next ep's card).
- **Friday / week finale:** `"Tune in next week for a new installment of the Mayor Awesome Cinematic Universe!"`
  over the generic "next week" `next.mp4` card.
- Add it to the **outro** bed's `cues`.

**New cue/shot fields** (all optional; ignored when absent, so existing episodes are unaffected):

- cue `pad_seconds: N` — trailing held/looped video + silence after the VO (tacked onto the last shot).
- cue `no_subs: true` — spoken but deliberately not subtitled.
- title shot `fill: "loop"` — loop the card across its slot instead of clone-holding the last frame (the
  animated `intro`/`next` cards play once and clone-hold, so they do NOT use this).

**Bookend assets in `titles/` (Max renders + moves them):** `intro.mp4` (1024×1024, animated open → this
title card), `thumb_wide.mp4` (1920×1080 → `final/<slug>_thumb.png` for YouTube), and `next.mp4` (1024×1024,
the NEXT episode's card for the bumper; Friday = a generic "next week" card). `intro` and `next` are cue
shots (put them in `title_assets`); `thumb_wide.mp4` is not.

## Worked reference

`/mnt/storage/shares/MACU/episodes/ep-005/manifest.json` is the canonical, validated example — read it when in doubt.
Copy its `voice`, `comfyui`, `style`, `render_rule`, `music`, `subtitles` blocks into a new episode and only
change `episode`/`title`/`characters`/`broll`/`cues` and the music bed cue ids.
