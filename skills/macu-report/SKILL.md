---
name: macu-report
description: >-
  Collaboratively write and generate an episode or segment of The MACU Report — the black-and-white,
  post-apocalyptic, retro-futurist faux-newscast in August's Mayor Awesome Cinematic Universe (MACU).
  Use this whenever August wants to make a MACU episode, write a MACU Report, add a new segment / ad /
  sponsor bit, invent a new MACU character, draft a MACU script, or "kick off generation" of a MACU video.
  Trigger on phrases like "new MACU episode", "write a MACU Report", "MACU segment/ad/character",
  "make episode N", "let's generate the MACU video", or any mention of Ron, Walter, The MACU Report, or the
  Mayor Awesome universe — even if the word "skill" is never said. The skill brainstorms and writes the
  script with August first, builds the episode manifest, and (only on his explicit OK) hands the render off
  to Max via Vikunja.
---

# The MACU Report — episode generator

The MACU Report is a recurring fake newscast inside the **Mayor Awesome Cinematic Universe (MACU)**: a
comedic, intentionally-janky, black-and-white, analog, post-apocalyptic retro-future. Two anchors (Ron and
Walter) cut to absurd, often creepy segments, ads, and sponsors. The "bad early-AI-video" look is the joke.

This skill drives the whole creative front end: **brainstorm + write the script with August → turn it into a
render manifest → hand the heavy generation off to Max.** August authors here on Leo (his Windows box / this
session); all GPU + audio + assembly work runs on **Max** (the Linux home server), reached over a shared
Syncthing folder and the Vikunja coordination board.

## Before you start — read the references

These hold the canon and the mechanics. Read the ones you need; don't reinvent them:

- `references/character-bible.md` — the cast, their locked ModelScope/zeroscope **prompt cores + seeds**, the
  global style suffix + negative, environments/b-roll, sponsors, and how to invent new characters.
- `references/world-lore.md` — MACU canon: the AI Wars of 2028, geography, tone rules, running gags.
- `references/manifest-schema.md` — the exact `manifest.json` shape, the **locked render settings** (do not
  regress these), music + subtitle blocks, and authoring conventions (seed reuse, b-roll keys, title slots,
  per-shot timing).
- `references/pipeline-and-handoff.md` — what Max's pipeline does end-to-end, the gotchas to respect, and the
  **precise Vikunja handoff procedure** (project, user ids, the assignee proxy, how to ping and poll).

## The workflow

### 1. Brainstorm the episode with August (default: brainstorm-first)

Start as a creative partner, not a form. Riff with him on the premise and the run of show before writing
prose. Good things to land together: the episode's theme or "cold open" hook, which **recurring cast** appear
(Ron + Walter always anchor), what **segments / ads / sponsors** to include, and — the fun part — whether to
**invent a new creepy/zany character or sponsor** for this one. MACU leans weird: cults, sentient appliances,
ominous PSAs, too-cheerful spokesmen. Pitch a few, let him pick.

Keep the structure loose but recognizable as a newscast: cold-open anchor intro → segments interleaved with
ads/bumpers → weather → a feel-good closer → signoff. EP5 is the reference for length and rhythm (~27 cues,
~4–5 min). You don't have to match it — shorter single-segment bits are fine too.

### 2. Write the script

Write it in MACU voice — earnest-anchor delivery over absurd post-apocalyptic content, dry and a little
menacing, comedic. Two rules that matter for the pipeline:

- **Each character has its own voice now** (cloned via OmniVoice — Will-Ferrell-ish Ron, Cronkite Walter,
  Attenborough Tally Man, Snoop Mr. Cricket, etc.), so write *to* each character. The exception is the
  machine characters: **SAFE and the Vendor keep the calm HAL register** — that's the joke, and why the SAFE
  ad ("a 'safe' AI that swears it'll never turn on humanity, *for real this time*") lands. You'll cast each
  speaker's voice in step 4; the catalog of available voices is in `references/manifest-schema.md`.
- Keep lines as **clean spoken prose** — the line text becomes both the VO and the burned-in subtitle, so
  avoid stage directions inside the spoken text (put those in parentheses on their own).

Save the script to `episodes/<slug>/script.md` (readable screenplay form, with a `» shot:` annotation per line
so it doubles as the shot list — see EP5). Revise with August until he's happy. **Do not move on to the
manifest until the script is approved.**

### 3. Lock the cast → prompt cores, seeds, and voices

For every speaker and b-roll location in the script, you need a prompt. For **recurring** cast, reuse their
core + seed from the bible verbatim. For any **new** character or sponsor, write a short prompt core (nouns +
2–3 strong adjectives — the model is low-res, so don't overwrite) and assign a fresh seed (any 4–5 digit
number not already used). Same for new environments/b-roll.

**Cast a voice for every speaker.** Each distinct cue `speaker` gets an entry in `voice.speaker_map` (see the
voice catalog in `references/manifest-schema.md`). Match voice to character — an Attenborough for an ominous
narrator, a cheerful infomercial pitch for a huckster — and **reserve HAL for AI/appliance characters**
(SAFE, the Vendor). The bible records each recurring character's voice; carry it forward. If no catalogued
voice fits a new character, note that a new clone is needed — that's a quick Max-side step in the handoff.

**Persist new characters to the living bible** so they're canon next time: the bundled `references/character-bible.md`
is a starting snapshot, but the project's working copy at `E:\August\MACU\MACU\MACU_Character_Prompt_Bible.md`
(synced to Max) is the source of truth — add new cast there. (In a sandbox/dry-run with no access to that path,
just note the addition in your output instead of writing it.) The character also goes in the manifest's
`characters{}` regardless, so a render never depends on the bible file.

### 4. Build the manifest

Create `episodes/<slug>/manifest.json` following `references/manifest-schema.md` exactly. The non-negotiables:

- Copy the **locked `comfyui` block** (zeroscope_v2_576w @ 384×384×24f, steps 30, cfg 15, fps 8) — this is
  what makes watermark-free + square + B&W + VRAM-fit all true at once. Don't bump resolution.
- Carry the `style` (suffix + negative), `music` (intro/outro big-band theme beds), and `subtitles` (Better
  VCR font) blocks forward.
- One cue per spoken line: `{id, segment, speaker, vo, shots[]}`. Shots reference `characters[*]`,
  `broll[*]`, or `title_assets` by key. Reuse one master per character across their cues (the assembler does
  this automatically — same key = one generation).

Then **validate** it:

```
python scripts/validate_manifest.py episodes/<slug>/manifest.json
```

Fix anything it flags (broken refs, seed mismatches, duplicate ids, missing locked settings) before handoff —
bad manifests are slow to debug after they've been sent.

### 5. Confirm, then hand off to Max (build-then-confirm)

Before sending anything, show August a short summary: episode slug, runtime estimate, cue/shot counts, **which
characters are new** (and their seeds), and the rough render cost (~30–40s GPU per unique master + a few min
assembly). Get his explicit OK.

**The handoff has real side effects** — it creates a Vikunja task, pings Max's live session, and can kick off
a ~25-minute GPU render. So never fire it on assumption: only create/assign the task after August has
explicitly approved the build. If you're unsure, dry-running, or being tested, stop at the summary and ask —
producing the script and a validated manifest is the win; sending is a separate, deliberate step.

On his go, hand the render to Max via Vikunja — full procedure in `references/pipeline-and-handoff.md`. In
short: confirm the episode folder has synced to Max, create a task on project 3 describing the episode +
manifest path, **assign it to Max (user id 5) via the n8n assignee-proxy workflow** (the MCP `assign` is a
silent no-op — the proxy is the only thing that works *and* pings him), and verify the assignee took.

Then tell August it's running and that he should **ping you to check the board** when Max responds — you have
no notification hook for replies. When he does, pull Max's comment and relay the result (and the output path:
`episodes/<slug>/final/<slug>.mp4`, which syncs back to Leo).

### 6. Iterate

Re-renders are cheap and incremental: VO/masters/titles are cached, so tweaks (a new line, a different sub
style, the music gain) only redo what changed. If August wants changes after seeing a cut, update the
script/manifest and send Max a focused follow-up rather than regenerating everything.

## Notes

- **You can't reach Max's LAN or pull renders directly from this session** — the sandbox allowlist blocks
  `10.0.0.245` and webhooks. Everything moves through the Syncthing `macu` folder (= `E:\August\MACU\MACU\`)
  and the bridged MCPs. So: author files in the synced folder, hand execution to Max.
- **Titles** (`macu_report_title`, `macu_report_bumper`) are built separately as Hyperframes compositions and
  live in `episodes/<slug>/titles/`. Reuse the existing ones unless August wants a new look; see
  `references/pipeline-and-handoff.md` for rebuilding.
- If August only wants a **single segment or ad** (not a full episode), the same flow works — just a smaller
  manifest. Don't force a full newscast structure on a one-off bit.
- **Slug:** numbered episodes use `epN` (e.g. `ep6`); one-off bits use a short descriptive slug
  (`<sponsor>-bit`, `<topic>`). The manifest's `episode` field always equals the folder slug.
- **Weather and sports** are delivered by the anchors (Ron/Walter) unless you invent a presenter for them —
  there's no default weather character.
- **Music beds** assume episode-length runs. On a short bit (≲6 cues) the intro/outro beds overlap — shrink
  each to one cue or set `music.enabled` to false. Always set each bed's `cues` to this piece's real first/last
  cue ids; leaving a placeholder will fail validation (which is the point).
