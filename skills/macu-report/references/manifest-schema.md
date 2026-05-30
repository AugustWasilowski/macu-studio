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
  "authored_by": "leo",
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
  "default":   { "engine": "piper", "endpoint": "http://10.0.0.245:5050/" },
  "endpoints": { "piper": "http://10.0.0.245:5050/", "omnivoice": "http://10.0.0.245:3900" },
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
  "endpoint": "http://10.0.0.245:8188/",
  "frames": 24, "width": 384, "height": 384, "steps": 30, "cfg": 15, "extract_fps": 8,
  "out_pattern": "clips/<shot_id>.webp"
}
```
**Why locked:** zeroscope_v2_576w (not DAMO ModelScope) removes the baked-in shutterstock watermark; 384×384
keeps the required 1:1 square, fits the 2080 Ti's 11 GB at 24 frames, and pulls the B&W cue harder than 16:9.
Bumping to 576×320×24f triggers ComfyUI lowvram offload and crashes the temporal modules — don't.

```json
"music": {
  "enabled": true,
  "source_dir": "/mnt/storage/shares/MACU/Musak",
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
  "force_style": "FontName=Better VCR,Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=32,Alignment=2"
}
```
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

Need a voice that isn't here? Clone one on Max: `/mnt/storage/shares/MACU/voices/clone_one.sh <Name> <ref.mp3>`,
which prints a new persistent `profile_id`. (That's a Max-side step — ask via the render handoff.)

### EP5 casting (worked example)

RON→Burgundy, WALTER→Walter, MOTHER MARIGOLD→Laura, TALLY MAN→David, BARTHOLOMEW→Seth, MR. CRICKET→Snoop,
NORM→Howie, ANNOUNCER→Announcer, and the two machines — **THE VENDOR→HAL, SAFE→HAL** (Piper). HAL on the
appliances is the joke; everyone else gets a real voice.

### Voice gotchas (encode in the handoff if relevant)

- **Stage 1 (VO) must run on Max** — OmniVoice binds to `127.0.0.1:3900` (loopback-only); there's no remote path.
- **Serial**: ~3 s per OmniVoice cue, ~0.5 s per Piper cue (OmniVoice asserts under concurrency).
- **VO-only iteration**: change `voice.speaker_map` or a cue's text, delete just the affected `vo/<cue>.wav`,
  `touch` the rest forward past the manifest mtime, then re-render `from_stage: 1`. Stages 4-8 cascade.

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
  - `{"kind":"title","asset":"macu_report_title"|"macu_report_bumper"}` — looked up under
    `episodes/<slug>/titles/<asset>.mp4`.

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

## Worked reference

`E:\August\MACU\MACU\episodes\ep5\manifest.json` is the canonical, validated example — read it when in doubt.
Copy its `voice`, `comfyui`, `style`, `render_rule`, `music`, `subtitles` blocks into a new episode and only
change `episode`/`title`/`characters`/`broll`/`cues` and the music bed cue ids.
