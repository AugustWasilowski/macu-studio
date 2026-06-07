# {{SHOW_NAME}} — Production Routine

_Show id: `{{SHOW_ID}}`. Created {{DATE}}._
_(Seeded from the new-show template — replace every [BRACKETED] prompt with real content.)_

How to take {{SHOW_NAME}} from idea → finished episode. The per-show playbook on top of the shared pipeline
(`docs/_common/MACU_Pipeline_Design.md`).

---

## Read order before writing an episode

1. **`Series_Bible.md`** — tone law, setting, the engine.
2. **`Story_Arcs.md`** — what's happened, what's planted, running-gag state. **Pay off banked beats.**
3. **`Character_Prompt_Bible.md`** — cast, cores, seeds, voices. Reuse recurring cores/seeds verbatim.
4. **`Voice_Roster.md`** — who speaks with which voice.
5. `docs/_common/` as needed — `MANIFEST_SCHEMA.md`, voice tips, the PROMPT_* generator prompts.

## Episode shape

[FILL: this show's format and length. e.g. "~2.5–3 min pilot; cold open → 2–3 acts → button. Soap: end on
a cliffhanger sting + narrator 'next week' teaser." Newscast: "desk segments + ads + bumper." Define the
default act structure so episodes feel consistent.]

## Script grammar (how the manifest is generated from script.md)

Write `script.md` in the MACU grammar so **Generate manifest** parses it into cues:

- `## ACT / SEGMENT HEADER` → a segment boundary.
- `**SPEAKER:** dialogue …` → one cue (VO). Stage directions in `_(parentheses)_` are stripped from the
  spoken line. Dialogue wraps until the next `»`, blank line, `**`, or `##`.
- `» Foo core → b-roll: bar → BAZ card` → the shots for that cue, in order. `X core` = a character shot
  (key resolved against the Character Bible / manifest characters, seed copied); `b-roll: X` = a b-roll
  shot; `… card` / `… bumper` = a title shot. A cue with no `»` gets one character shot for its speaker.

## From script to finished video

1. Write `script.md` (read order above).
2. **Generate manifest** (Script page) → cues.
3. **Generate shot list** (shotgen) → proposes characters/b-roll/shots; it reads this show's
   `*Character_Prompt_Bible.md`. Review, then apply.
4. Assign **voices** per speaker (Voice_Roster.md) — clone new characters first if needed.
5. Set the **style** suffix/negative + per-character seeds (Character Bible ↔ manifest).
6. **Render** (macu-render pipeline / Studio) — VO → masters → interpolate → assemble → music → subs.

## Cadence / conventions

[FILL: how often episodes ship, naming convention for slugs (e.g. `{{SHOW_ID}}-001`), where assets live,
any show-specific render quirks.]

## Update-after-each-episode checklist

- [ ] New characters persisted to `Character_Prompt_Bible.md` (core + seed + voice).
- [ ] `Story_Arcs.md` updated: running-gag state, arcs advanced, plants banked/paid.
- [ ] Episode added to the `Series_Bible.md` episode index.
- [ ] New voices added to `Voice_Roster.md`.
