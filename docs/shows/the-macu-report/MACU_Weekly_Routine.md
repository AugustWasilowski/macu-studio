# MACU Weekly Routine — the Saturday "Writers' Room"

Production cadence (set 2026-05-31): **5 episodes/week, released Mon–Fri, weekends off.** Episodes are
written + rendered over the weekend. Every **Saturday 6:00 AM (US Central)** an automated routine drafts the
NEXT week's five scripts plus a one-page plan, so August wakes up to a full week to react to. We punch it up
together Saturday, then build manifests/graphics and hand the week to Max to render Sat/Sun.

This file is the standing spec for that Saturday draft. The scheduled task points here. Keep it current.

## What the Saturday routine produces (and does NOT do)

PRODUCE, then STOP:
1. **Five episode scripts** — `episodes/epN/script.md` for the next five unused episode numbers, written in
   full MACU screenplay form with `» shot:` annotations (same format as ep6–ep10), following the
   `macu-report` skill (step 2) and `references/joke-engineering.md`.
2. **A one-page week plan** — `episodes/week-<NN>-plan.md` (see template below).

Do **NOT** this routine: build manifests, build graphics, clone voices, or hand anything to Max. Those
happen after the Saturday review (cheap to change a script; expensive to redo a manifest/render). Leave a
clear "READY FOR SATURDAY REVIEW" note and notify August.

## Before drafting — read the state

1. `MACU_Story_Arcs.md` — the Ron paranoia arc + the breakout cadence + any **banked beats** for the
   upcoming episode numbers (e.g. ep11 = gaslit-reset aftermath; ~ep15 = next breakout). Honor them.
2. `MACU_Character_Prompt_Bible.md` — cast, seeds, voices; reuse recurring cores/seeds verbatim.
3. The `macu-report` skill `references/` (character-bible, world-lore, manifest-schema, joke-engineering).
4. The highest existing `episodes/epN/` to get the next episode number; continue from there.
5. `OmniVoice_Voice_Roster.md` (the live voice index — every profile_id by character; flag any NEW voice to
   clone) + `OmniVoice_Voice_Tips.md` (how to shape delivery: `speed` / `seed` / `instruct` / `guidance_scale`,
   incl. two-register characters like STRIDE via `instruct`). Cast from the roster; don't invent voices.

## The weekly structure (the unit)

The **week is the arc**: five connected episodes, **Monday plant → Friday button**, with the Ron paranoia
simmering underneath. Specifically:
- **Mon:** open the week's mini-theme; plant 1–2 throwaways that pay off later in the week.
- **Tue–Thu:** develop; rotate segment types so no week feels samey; midweek runner callbacks.
- **Fri:** the **button** — collide the week's threads in the signoff; satisfying close.
- **Ron arc:** keep it a LOW SIMMER (~1–2/10) — one small, ignored Ron beat per episode — UNLESS a banked
  breakout falls in this week (then escalate per `MACU_Story_Arcs.md`).
- **Freshness:** introduce ~one new character/sponsor/segment per week; note any new **voice** to clone so
  Saturday review can approve it before Max clones. Reuse the bench otherwise.
- Length: default ~3–5 min standalone episodes; a breakout week can run one long (~12–15 min) episode —
  schedule that one first for Max.
- Keep it black-and-white, analog, MACU voice. Each character writes to its own voice (HAL reserved for
  AI/appliances).
- **Transitions (ease the seams):** a newscast never hard-cuts. Toss INTO and button OUT of segments with a
  one-line anchor interstitial (usually Walter) — never slam from dialogue straight into weather or into a
  commercial. A title-card flash on the toss is welcome. See `joke-engineering.md` §7.

## `episodes/week-<NN>-plan.md` template

```
# MACU — Week <NN> (epA–epE) — <week theme>
Release: Mon <date> – Fri <date>

Theme / throughline: <one line>
Friday button: <what pays off Fri>
Ron-arc beat this week: <level /10; what + which day; or "banked breakout — see arc doc">
New this week: <new character/sponsor/segment + which voice; flag clones needed>
Runners/callbacks in play: <moon? "mild"? "you worry too much, Ron"? Little Seven? etc.>

Mon  epA — <title> — <logline> — segments: <...>
Tue  epB — <title> — <logline> — segments: <...>
Wed  epC — <title> — <logline> — segments: <...>
Thu  epD — <title> — <logline> — segments: <...>
Fri  epE — <title> — <logline> — segments: <...>  [BUTTON]

Notes for Saturday review: <new clones to approve, any big swing, open questions>
```

## After Saturday review (manual, with August)

Lock scripts → build the 5 manifests + any new B&W Hyperframes cards → queue any voice clones → hand the
week to Max via Vikunja (heaviest/breakout episode first) → Max renders Sat/Sun → release Mon–Fri, with each
episode's `youtube.txt` written as part of the build.
