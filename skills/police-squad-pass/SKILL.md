---
name: police-squad-pass
description: >-
  Run the Police Squad pass — a deadpan / ZAZ (Zucker-Abrahams-Zucker) punch-up layer over a script in
  August's Mayor Awesome universe (The MACU Report, As The World Burns, or any MACU show). It threads in
  absurd lines delivered in a completely settled register — "say the unsettling thing flat, don't acknowledge
  it, cut" — plus literal-mindedness, name/visual puns, fake title cards, the murdered special-guest-star, and
  anti-comedy timing. Run it AFTER the writers' room and BEFORE cast lock. Trigger when August says "police
  squad pass", "run the police squad", "ZAZ pass", "punch up the deadpan", "add deadpan non-sequiturs",
  "naked gun / airplane it up", or asks to layer deadpan gags onto a MACU script — even if the word "skill"
  is never said. Show-aware: it reads the active show's own `Police_Squad_Pass.md` for the show-specific
  vehicles, runners, and examples, and falls back to the general craft in this file.
---

# The Police Squad pass

A thin, surgical-but-dense punch-up layer in the Police Squad! / Airplane! / Naked Gun tradition. It does NOT
rewrite jokes or plot — it layers deadpan gags onto the existing scenes. Run it **after the writers' room,
before locking the cast**, on a revised draft.

## The two rules (universal — always apply)

**Rule Zero — play it absolutely straight.** This is the biggest rule; everything serves it. The humor is the
gap between ridiculous *content* and dead-serious *tone* — Leslie Nielsen's Drebin says insane things with the
gravity of a real cop drama. No character ever knows they're funny; nobody winks. The horror/absurdity lives
in the content, never the delivery. (This is enforced at the voice layer too — MACU shows clone dramatically
committed source voices on purpose so the performance never breaks.)

> Say the unsettling thing flat. Don't acknowledge it. Cut.

**Rule One — density / joke-per-second.** Gags come relentlessly, faster than you can catch them — which
rewards rewatching; if one doesn't land, another arrives a second later. Stack a foreground line, a background
sight gag, and a literal misunderstanding into one moment. Layer the channels: dialogue · narration/VO · what's
on screen (b-roll / title cards) · what a character does while saying something else. **Density never excuses a
wink — Rule Zero always wins.** (Note: The MACU Report historically kept this surgical at ~1–2 beats/segment;
As The World Burns runs denser. Defer to the show's own doc.)

## The techniques (named, so the pass can reach for them)

- **Settled register** — deliver the alarming line as small talk, a status update, or a housekeeping note.
- **The literal answer** — a grave question met with a true, irrelevant, literal observation ("Doctor, will he
  make it?" → "He has very good posture.").
- **Literalized figures of speech & dead clichés** — take the cliché at its word in a world where it's true
  ("she's dead to me," "over my dead body," "till death do us part").
- **The fake title card** — the burned-in episode title contradicts the one spoken aloud; never reconciled.
- **The murdered special guest star** — a "very special guest" introduced and dead before the cold open ends,
  every episode, never mentioned again.
- **Name & visual puns** — character/place names taken literally; one-off "Nice beaver / I just had it stuffed"
  two-handers where the reply takes the line literally.
- **The warm line with a dark tail** — a friendly sentiment that curdles on the last clause.
- **Validate-then-forget** — affirm the human, then instantly drop them for a metric or a chore.
- **A single beat of pure normalcy** dropped in right before a payoff so the reaction lands harder.
- **The almost-notice** — one character (the audience surrogate) states the wrongness plainly, one beat too
  late to act on it.
- **Anti-comedy timing** — hold the reaction past comfort (→ a hold cue), run a trivial scene too long,
  escalate absurdly with total commitment.

## Process

### 1. Identify the show + the target script, and load the show's flavor

Determine which show/episode you're punching up (from context, or ask). Then read the show-specific Police
Squad doc for its vehicles, recurring runners, world hooks, and worked examples:

- **As The World Burns** (and other new shows): `docs/shows/<show-id>/Police_Squad_Pass.md`.
- **The MACU Report**: `skills/macu-report/references/police-squad-pass.md`.
- If the show has no flavor doc, use the general craft above (and offer to create one for that show).

Also read the script you're punching up (e.g. the episode's `script.md`).

### 2. Dispatch the pass

Read `pass-prompt.md` and dispatch a focused expert subagent with: the revised script + the show's flavor doc
+ the two rules above. It returns **only proposed insertions** — each a segment/scene anchor plus the new
line(s), OR a structural runner (a fake title card, a cold-open guest star). It does not touch plot or existing
punchlines. Go **dense** per Rule One (subject to the show's doc), but never let a single beat wink (Rule Zero).
For a light pass you may do this inline instead of as a subagent.

### 3. Accept / reject with August

Present the proposed beats as a list (anchor + line) so August accepts or rejects each. Do not apply silently.

### 4. Apply the accepted beats — keep it pipeline-clean

Insert accepted beats into the script in the show's grammar:
- The spoken line is **clean prose** (it becomes the VO *and* the burned subtitle).
- Delivery notes go in parentheses on their own line, never inside the spoken text.
- A fake title card goes in the `»` shot line (`… card`); a held beat becomes a **hold cue** (see
  `docs/_common/MANIFEST_SCHEMA.md`).
- **Protect the weird** — if a beat is confusing rather than strange, cut it; never sand off the strangeness.
- **Git-sync this version immediately** once applied, so the pass is its own reviewable commit:
  `POST /api/episodes/<slug>/git-sync` with `{"message":"<slug> v<N> (Police Squad pass)"}`. One labeled
  commit per version; commit+push is pre-authorized for script-revision syncs.

### 5. Bank any runner that became canon

If an accepted beat establishes a recurring runner (the murdered-guest bit, a name pun, the title-card
mismatch), note it in the show's `Story_Arcs.md` so future episodes keep it consistent. Then continue to cast
lock and the manifest.
