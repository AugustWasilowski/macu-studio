# Writing a MACU script

How Studio turns your `script.md` into a manifest when you hit **Generate manifest** on the Script tab.
The parser is a heuristic, and it **always shows a preview/diff before writing anything** — so you can't
break a thing by experimenting. Read the diff, then Apply.

## The four building blocks

| You write | Studio reads it as |
|---|---|
| `## COLD OPEN` | a **segment** boundary — groups the cues under it |
| `**RON:** Good evening.` | one **cue** — a line of dialogue spoken by RON |
| `» Ron core → b-roll: lemonade_stand` | the **shots** for the cue above, in order |
| `### Shot tally` | **end of the body** — everything from here down is ignored |

That's the whole grammar. Everything else (voices, seeds, style, music, title assets) lives in the manifest
and is **preserved** across regenerates — Generate manifest only ever rewrites the `cues`.

## Speakers

- A cue starts with a bold, colon-terminated name: `**WALTER:** …`. The colon goes **inside** the bold:
  `**WALTER:**`, not `**WALTER**:`.
- The name should match a speaker in your manifest (the voice map / characters). An unknown speaker still
  makes a cue, but it's flagged in the preview so you can fix the spelling or add the voice.
- **Multi-line dialogue is fine** — keep typing on the next lines. A cue's text runs until the next `»`,
  a blank line, the next `**SPEAKER:**`, or the next `##`.

## Stage directions (not spoken)

Annotate delivery without it being read aloud:

- `_(beat)_`, `_(thrilled)_`, `_(HAL filter)_` — underscore-paren bits are **stripped** from the spoken line.
- A leading parenthetical like `(voiceover)` at the very start of a line is also stripped.

`**RON:** _(weary)_ Good evening, survivors.` → RON says **"Good evening, survivors."**

## Shots — the `»` line

- **No `»` after a cue?** The cue automatically gets one **character shot** of whoever's speaking. So a
  plain talking-head line needs no shot line at all.
- `» Ron core` — a character shot of Ron (the seed comes from `manifest.characters.ron`).
- **Chain shots** with `→` (or `->`), left to right:
  `» Ron core → b-roll: crystal_packets → just_add_water title card`
- `b-roll: NAME` — a b-roll shot. `NAME` must exist in `manifest.broll`.
- `… card` / `… title card` / `… bumper` — a title-card shot, matched against `manifest.title_assets`.
- Anything else on a `»` line is read as a **character name** (matched against `manifest.characters`).
- Unmatched b-roll / title / character references **warn** in the preview — they won't silently vanish,
  but check the diff.

## Tips & gotchas

- **Long lines auto-split.** A single VO line over ~180 characters (~18 seconds) is broken into multiple
  cues at sentence boundaries — the TTS audibly degrades past ~25-30s. Want one unbroken take? Keep the
  line under ~180 chars. Want a deliberate cut? End a sentence (`.`/`!`/`?`).
- **A cue's identity is its text, normalized.** Studio matches cues across edits by their words with
  punctuation and case ignored. So fixing a typo, an em-dash, or capitalization **keeps that cue's voice,
  seed, and already-rendered audio**. A *heavy* rewrite reads as a brand-new cue and will re-generate.
  Move dialogue around freely; rephrase it and expect a re-render.
- **Put notes below a `### heading`.** Shot tallies, arc notes, anything you don't want parsed — drop it
  under any `###` section and the parser stops there.
- **Blank lines matter.** A blank line closes the current cue's dialogue/shot block.
- **Generate manifest is non-destructive.** It's a dry run until you click *Apply — write manifest.json*,
  and it backs up the previous manifest with a timestamp. The diff tells you: how many cues are new or
  being re-shot, which speakers still need a voice, and any shot references it couldn't match.

## A tiny complete example

```markdown
## COLD OPEN

**RON:** _(weary)_ Good evening, survivors. Ron here, with the news that's fit to broadcast.
» Ron core

**WALTER:** And I'm Walter. Tonight: the vending machine wants the moon, and we have thoughts.
» Walter core → b-roll: vending_machine

**RON:** Back to you never, Walter.

### Shot tally
ron ×2, walter ×1, broll: vending_machine ×1   ← ignored by the parser
```
