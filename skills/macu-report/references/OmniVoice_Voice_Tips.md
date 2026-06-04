# OmniVoice voice-shaping tips

Practical knobs for the cloned MACU voices. Every param below is a form field on `POST http://127.0.0.1:3900/generate` (multipart -F). Default values shown; pass only the ones you want to change.

**Runs on Max** (Linux home server) — this box owns both the cloning and the pipeline. Keep this file in sync with `OmniVoice_Voice_Roster.md`.

OmniVoice Studio upstream: <https://github.com/debpalash/OmniVoice-Studio>. Container runs the source from `/app` inside `omnivoice` on max (port 3900, loopback-only — use `127.0.0.1` from max, `10.0.0.245` from elsewhere on the LAN).

---

## TL;DR — the 4 knobs you'll actually reach for

| knob | default | what it does | when to use |
|---|---:|---|---|
| `speed` | 1.0 | linear-ish stretch/squash of delivery rate. 0.7 = ~30% slower, 1.3 = ~30% faster. Validated empirically (GG_Blanche: 1.0→16s, 0.85→18.9s, 0.7→22.1s). | re-cloning won't change prosody — `speed` does. First-line fix for "this voice talks too fast". |
| `seed` | random | int. Pin a seed → identical wav every render (assuming same model + same params). | re-rendering an approved take; A/B-testing other params without prosody drift contaminating the comparison. |
| `instruct` | "" (or the profile's stored instruct) | **constrained voice-DESIGN vocabulary** — gender, age, accent, pitch, whisper. Not free text, not emotional direction. Server returns 400 with the valid list if you pass anything else. | dialing voice timbre attributes on top of a clone. e.g. `instruct=male, elderly, low pitch` will age & deepen a baseline voice. **Use the text + `speed` to drive emotion**, not `instruct`. |
| `guidance_scale` | 2.0 | CFG strength. Higher = more faithful to the ref voice & instruct, but more brittle. Lower = looser, more natural variance. | bump to 2.5–3.0 if a clone "doesn't sound like the source"; drop to 1.5 if it sounds robotic / over-precise. |

If the voice is wrong, try `speed` and rewriting the text first (punctuation drives delivery). `instruct` only shifts timbre attributes, not performance. Don't re-clone.

---

## Engine choice

Two TTS engines in play. Pick by character type:

| engine | use for | URL |
|---|---|---|
| **OmniVoice :3900** | every human-cast clone (Ron, Walter, Burgundy, Goldtooth, the Golden Girls, Crater Carl, …). Reference-audio cloning. | `http://127.0.0.1:3900/generate` |
| **Piper HAL :5050** | machines / AIs that need the canonical HAL register (Unit 7 / The Vendor, SAFE, EVERWELL casket pitch, STRIDE's cold-flat mode). | `http://127.0.0.1:5050/` (POST JSON `{"text": "..."}`) |

If a character has *both* a human and a machine voice (STRIDE does — warm/chipper + cold/flat), render each register from its own engine and edit the seam in post.

---

## Full `/generate` parameter reference

All of these are multipart form fields. Code source: `/app/backend/api/routers/generation.py` inside the omnivoice container.

### Required

| field | type | notes |
|---|---|---|
| `text` | string | the actual line to speak. Em-dashes and ellipses are honored (introduce pauses); CAPS aren't louder; numbers are read as numerals ("ten thousand" not "10000"). |

### Voice selection (pick ONE)

| field | type | notes |
|---|---|---|
| `profile_id` | string (8 chars) | the cloned-voice id from `GET /profiles`. Pulls ref_audio + ref_text + instruct + seed from DB (any per-request param overrides). |
| `ref_audio` | file upload | inline reference WAV for one-shot cloning without saving a profile. |

### The four big knobs (covered above)

`speed`, `seed`, `instruct`, `guidance_scale`.

### Less-common quality dials

| field | type | default | notes |
|---|---|---:|---|
| `language` | string | `"Auto"` | `"English"`, `"Spanish"`, `"French"`, …, or `"Auto"` for detection. Pin it for MACU (always `English`) — auto-detect can flip on lines with a few Italian/Spanish words. |
| `ref_text` | string | profile default | transcript of the reference clip. Setting this *correctly* improves the clone's pronunciation alignment. We leave it empty for MACU clones and it still works — set it only if a clone is mispronouncing something specific from the ref. |
| `duration` | float seconds | unset | target total duration. Model tries to hit it by stretching/squeezing prosody. Use sparingly — `speed=…` is cleaner. Useful when you need to slot a line into a fixed cue window. |
| `num_step` | int | 16 | diffusion steps. 8 = faster + rougher; 32 = slower + cleaner. 16 is fine for our use. |
| `t_shift` | float | unset (model default) | flow-matching noise schedule shift. Don't touch unless a clone is consistently breathy/fuzzy. |
| `denoise` | bool | `True` | post-process denoise pass. Leave on. |
| `postprocess_output` | bool | `True` | mastering chain (EQ + normalize to -2 dBFS). Leave on. |
| `position_temperature` | float | unset | sampling temperature for positional tokens. Lower = more deterministic prosody; higher = more variation. |
| `class_temperature` | float | unset | sampling temperature for content tokens. Same shape as above, different head. |
| `layer_penalty_factor` | float | unset | low-level repetition penalty. Worth touching only if you see a clone stutter or loop a syllable. |

---

## Recipes

### 1. Standard MACU line — voice from the roster

```bash
curl -s -o out.wav \
  -X POST \
  -F "text=Welcome to MACU. The world has ended; the broadcast has not." \
  -F "profile_id=e1b4af0b" \
  -F "language=English" \
  http://127.0.0.1:3900/generate
```

### 2. Slow it down (cleanest fix for "voice sounds rushed")

```bash
# +30% duration — try 0.85 first, drop to 0.7–0.8 only if needed
curl -s -o out.wav \
  -X POST \
  -F "text=...your line..." \
  -F "profile_id=dccf39db" \
  -F "language=English" \
  -F "speed=0.85" \
  http://127.0.0.1:3900/generate
```

Past ~0.6 you start to hear artifacting. Above 1.3 it sounds like fast-forward.

### 3. Pin a seed so you can rebuild the exact take

```bash
curl -s -o out.wav \
  -X POST \
  -F "text=..." \
  -F "profile_id=e1b4af0b" \
  -F "language=English" \
  -F "seed=42" \
  http://127.0.0.1:3900/generate
```

`X-Seed` is also echoed back as a response header on every render — fish it out of the headers and stash it next to the approved wav to make re-renders reproducible.

### 4. Voice DESIGN with `instruct` (constrained vocab — NOT emotion)

`instruct` accepts ONLY items from a small enum. The validator returns HTTP 400 with the full valid list if you pass anything outside it. Don't try to use it for "warm" / "cold" / "encouraging" — those words will be rejected.

**Valid English items (full list):**

```
gender:     female, male
age:        child, teenager, young adult, middle-aged, elderly
pitch:      very low pitch, low pitch, moderate pitch, high pitch, very high pitch
style:      whisper
accent:     american accent, australian accent, british accent, canadian accent,
            chinese accent, indian accent, japanese accent, korean accent,
            portuguese accent, russian accent
```

Combine with `, ` (comma + space). Example: `male, middle-aged, low pitch, british accent`.

```bash
# Age + deepen a cloned HAL voice
curl -s -o hal_elderly.wav \
  -X POST \
  -F "text=All systems nominal. Proceed when ready." \
  -F "profile_id=eb01da84" \
  -F "language=English" \
  -F "instruct=male, elderly, low pitch" \
  -F "guidance_scale=3.5" \
  http://127.0.0.1:3900/generate

# Whispered low-pitch sponsor read
curl -s -o stride_whisper.wav \
  -X POST \
  -F "text=The system thanks you." \
  -F "profile_id=3f7a4dcd" \
  -F "language=English" \
  -F "instruct=female, low pitch, whisper" \
  http://127.0.0.1:3900/generate
```

**Quirk:** the server *also* exposes `GET /personalities` returning items like `Narrator → "Speak as a calm, authoritative documentary narrator…"`. Those are UI-side suggestions intended for a different (future?) code path — they FAIL the current `/generate` validator. Ignore the personalities endpoint until upstream wires it back up.

### 4b. Performance / emotion — drive it from the text + `speed`

OmniVoice has no "emotion" knob. Warm vs cold vs urgent comes from how the line is *written* and rendered, not from `instruct`:

| effect | how to get it |
|---|---|
| **warm / encouraging** | exclamation marks, contractions, second-person address ("you did it!"), `speed=1.0–1.1` |
| **cold / clinical** | short clipped sentences, no contractions, technical phrasing, em-dashes for hard stops, `speed=0.85–0.95`, optional `instruct=male, low pitch` |
| **measured / authoritative** | full sentences, commas not dashes, `speed=0.9`, `guidance_scale=3.0` |
| **rushed / panicked** | run-on sentences, ellipses-mid-clause, `speed=1.15–1.25` |
| **whispered** | `instruct=…, whisper` is the cleanest path |

For the STRIDE warm→cold register flip: write two different *lines* (warm one with chipper punctuation, cold one with clinical phrasing), render each from the same profile, edit the cut in post. One profile + two text-and-speed pairs, not one profile + two instructs.

### 5. One-shot clone from a fresh WAV (no saved profile)

```bash
curl -s -o out.wav \
  -X POST \
  -F "text=test line" \
  -F "language=English" \
  -F "ref_audio=@/path/to/30-second-ref.wav" \
  http://127.0.0.1:3900/generate
```

Reference clip rules of thumb: mono, 24 kHz, 30–60 seconds, single speaker, minimal music. Laugh-track bleed is tolerable; underscore music is not. Skip the first 15–30s of any compilation video — that's almost always intro music.

### 6. OpenAI-compatible endpoint (for tools that expect it)

OmniVoice also exposes an OpenAI-shaped endpoint at `POST /v1/audio/speech` (JSON body, accepts `model`, `voice`, `input`, `speed`, etc.). Use the native `/generate` for everything new; `/v1/audio/speech` exists so off-the-shelf OpenAI-SDK clients work.

---

## Workflow patterns

### A new character — pick a ref clip first time

1. Find a YouTube clip with that voice (compilation video is ideal: one speaker, lots of speech).
2. `yt-dlp -x --audio-format wav <url>` → mono-down with `ffmpeg -ac 1 -ar 24000`.
3. Slice 30–60s of clean, contiguous speech (skip intro music — start ≥30s in).
4. Pass through `/mnt/storage/shares/MACU/voices/clone_one.sh <Name> <ref.wav>`.
5. Render a couple of MACU-flavored test lines; iterate on `speed`/`instruct` before re-slicing the ref. Re-cloning rarely changes pace; it does change timbre and accent.

### A character that's "almost there"

Try these in order before re-cloning:
1. `speed=0.85` (or 1.15) — fix delivery rate
2. rewrite the text — punctuation drives prosody; em-dashes for pauses, ellipses for trail-offs, exclamation marks for energy
3. `instruct=male, elderly, low pitch` etc. — adjust *timbre* (valid vocab only — see §4)
4. `guidance_scale=2.5–3.5` — fix "doesn't sound like the source"
5. only now re-cut the ref slice

### A character that needs two registers (warm + cold, sober + drunk, etc.)

One profile, two *text-and-speed* pairs (not two `instruct` strings — see §4b). Write the warm half with chipper punctuation at `speed=1.0`, the cold half with clinical phrasing at `speed=0.85`. Render each, edit the seam in post. Pin different seeds per register so each register stays consistent across episodes.

### A reproducible take

Capture the `X-Seed` response header on the first render, pin it as `seed=<n>` for all re-renders of that line.

---

## Common pitfalls

- **"My clone sounds rushed" → don't re-clone.** Add `speed=0.85`. Three back-to-back rolls at default speed will produce nearly identical durations regardless of ref slice; the cadence is set at render time.
- **"My clone sounds noisy" → re-slice the ref, don't tune render params.** Most noise comes from intro music or laugh-track bleed in the reference window. Use a deeper / cleaner slice (start ≥30s into the source). [[Blanche v3 vs v1]] is a clean example.
- **"Numbers come out garbled"** — spell them out in `text` ("four hundred souls", not "400 souls").
- **"Mispronounces a proper noun"** — phonetic respelling in `text` ("Brøndar" already works because the model treats it phonetically; "St. Olaf" sometimes reads as "saint olaf" / "ess tee olaf" — try `St. Olaf,` with a comma to force the model to read it as a name).
- **"Random word appears at the start"** — usually means the ref slice begins mid-sentence; re-cut the ref to start at a silence/breath boundary. Cosmetic; only worth fixing if it shows up consistently.
- **"Out of memory"** — OmniVoice's resident model is ~5 GB on the 2080 Ti. Faster-whisper large-v3 in fp16 won't fit alongside it; use `compute_type="int8_float16"` or `medium.en int8` if you're transcribing while OmniVoice is loaded.

---

## Profile lifecycle (less common, but worth knowing)

- **List:** `GET /profiles` — returns full registry with ids, names, ref paths, seeds.
- **Get one:** `GET /profiles/{id}`
- **Create:** `POST /profiles` (form: `name`, `ref_audio` file, optional `ref_text`, `instruct`, `language`, `seed`, `personality`). The MACU `clone_one.sh` wraps this.
- **Update (rename / change instruct / set seed):** `PUT /profiles/{id}` (JSON body — `{"name": "...", "instruct": "...", ...}`)
- **Delete:** `DELETE /profiles/{id}`
- **Lock a ref:** `POST /profiles/{id}/lock` — captures the current generation as a "locked" canonical sample so future renders re-use that exact audio embedding rather than re-encoding the ref. Not used by MACU today; worth knowing if a clone starts drifting between renders.

Per-profile records hold `instruct`, `ref_text`, and `seed` — if you set them on the profile they become the default for every `/generate` call against that `profile_id` (still overridable per request).

---

## See also

- **Voice roster:** `OmniVoice_Voice_Roster.md` — every profile, its id, its source, and where it shows up on the MACU Report.
- **Pipeline:** `MACU_Pipeline_Design.md` — how cloned voices flow through `stage_1_vo.py`.
- **Characters:** `MACU_Character_Prompt_Bible.md` — canonical character → voice mapping (seeds, personalities, intended register).
- **Source:** `/app/backend/api/routers/generation.py` inside the omnivoice container is the source of truth for /generate params if you ever need to dig deeper.
