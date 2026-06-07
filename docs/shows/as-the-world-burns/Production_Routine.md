# As The World Burns — Production Routine

_Show id: `as-the-world-burns`. v0.1 — 2026-06-06._

How to take AWB from idea → finished episode. The per-show playbook on top of the shared pipeline
(`docs/_common/MACU_Pipeline_Design.md`).

---

## Read order before writing an episode

1. **`Series_Bible.md`** — tone law, Mirabelle Shores, the Product, the engine.
2. **`Story_Arcs.md`** — Resurrection Engine state, Mona's secret, banked beats. **Pay off the plants.**
3. **`Character_Prompt_Bible.md`** — cast, cores, seeds (810xx band), style suffix. Reuse verbatim.
4. **`Voice_Roster.md`** — who speaks with which voice.
5. **`Police_Squad_Pass.md`** — the deadpan / ZAZ punch-up layer (run after the writers' room, before cast lock).
6. `docs/_common/` as needed — `MANIFEST_SCHEMA.md`, `OmniVoice_Voice_Tips.md`, the PROMPT_* prompts.

## Episode shape (soap format)

- **~2.5–3 min** per episode (can grow). Structure: **COLD OPEN** (hook / a death / a return) → **2–3 short
  ACTS** → **BUTTON** (the sting). End every episode on a **cliffhanger** + the grave Narrator **"Next week,
  on As The World Burns…"** teaser.
- **The Narrator** frames the show: open with the hourglass tagline ("Like ash through the hourglass… these
  are the days of what's left of our lives"), narrate the lore deadpan, close with the teaser.
- Lean on **soap tropes played straight**: the reading of the will, the stranger at the gate, the secret
  relative, the slap-but-civil confrontation, the dramatic entrance. The apocalypse is set dressing; the
  melodrama is the genre.
- **Mona is the lore valve** — when the audience needs world info, a character explains it TO Mona, flat, as
  if she's slow for not knowing.

## Script grammar (script.md → cues)

- `## ACT / COLD OPEN / BUTTON` → segment boundary.
- `**SPEAKER:** dialogue` → one cue. `_(stage directions)_` are stripped from the spoken line.
- `» Vivian core → b-roll: lake_mirabel → AS THE WORLD BURNS card` → shots for the cue, in order.
  `X core` = character shot (key → Character Bible, seed copied); `b-roll: X` = b-roll; `… card/bumper` =
  title shot. Narrator cues use `» b-roll: …` (no character shot).

## From script to finished video

1. Write `script.md` (read order above). Run the **writers' room** critique loop, then the
   **Police Squad pass** (`Police_Squad_Pass.md`) to layer in deadpan/ZAZ density — before locking the cast.
2. **Generate manifest** (Script page) → cues. (Pre-seeded style/characters/broll are preserved.)
3. **Generate shot list** (shotgen) — reads this show's `*Character_Prompt_Bible.md`. Review → apply.
4. **Voices** — clone Vivian/Mona/Brick/Narrator first (see Voice_Roster.md); until then VO falls back to
   the manifest's default engine.
5. Confirm **style** suffix/negative + per-character **seeds** (Character Bible ↔ manifest).
6. **Render** (macu-render / Studio): VO → zeroscope masters → RIFE interpolate → assemble → music → ASR →
   Better-VCR sub burn.

## Cadence / conventions

- Slugs: `awb-NNN` (awb-001, awb-002, …). Episodes under
  `/mnt/storage/shares/MACU/shows/as-the-world-burns/episodes/<slug>/`.
- Title pattern: "As The World Burns — <Episode Title>".
- Same render rig as The MACU Report (zeroscope, 384², B&W) with AWB's soap-videotape style suffix.

## Update-after-each-episode checklist

- [ ] New characters persisted to `Character_Prompt_Bible.md` (core + seed in the 810xx band + voice).
- [ ] `Story_Arcs.md`: advance the Resurrection Engine state; advance arcs; bank/pay plants.
- [ ] Episode added to the `Series_Bible.md` index.
- [ ] New voices added to `Voice_Roster.md`.
