# {{SHOW_NAME}} — Character & Prompt Bible

_Show id: `{{SHOW_ID}}`. Created {{DATE}}._
_(Seeded from the new-show template — replace every [BRACKETED] prompt with real content.)_

> 🔧 **PIPELINE-CRITICAL — do not rename.** This file's name MUST end in `Character_Prompt_Bible.md`.
> `shotgen.py` / `cardgen.py` find it by the glob `docs/shows/{{SHOW_ID}}/*Character_Prompt_Bible.md` and
> feed it to the LLM as look/family guidance when proposing shots and cards. A renamed file = an empty
> bible = the model invents inconsistent characters.

T2V (ModelScope/zeroscope) prompt library for {{SHOW_NAME}}. **Every shot prompt = character/scene CORE +
the GLOBAL STYLE SUFFIX below; the GLOBAL NEGATIVE is applied to every shot.** Keep cores SHORT — at small
render sizes the model ignores fine detail; nouns and silhouette beat long adjective lists.

---

## Global style suffix (append to every positive prompt)

```
[FILL: the show's visual signature, appended verbatim to every shot. Inherit the MACU look and specialize.
 Universe default (The MACU Report):
   , black and white, grainy vintage analog television footage, 1970s broadcast, retro futurism, low
   resolution, washed out, soft focus
 Specialize for THIS show's format — e.g. a soap reads as "1970s daytime soap opera, videotape, soft
 interior lighting, melodramatic"; a game show as "garish 1970s game-show stage, hard studio lighting".]
```

## Global negative (use on every shot)

```
shutterstock, watermark, text, caption, logo, color, colour, modern, smartphone, digital screen, hd, 4k,
sharp, blurry, low quality, distorted, deformed, mutated, extra limbs, extra fingers
```
> `shutterstock` is mandatory and load-bearing — it suppresses the ModelScope Shutterstock-watermark bug.
> Keep `color`/`colour` in to hold black-and-white.

## Recommended render defaults

[FILL from the show's `episode_defaults.comfyui` in shows.json — e.g. 24 frames · 384×384 · 30 steps ·
cfg 15. Pin a per-character SEED so a character looks the same across shots and episodes.]

---

## Characters

For each recurring character: a short CORE (the visual prompt body), a FIXED SEED (so they're consistent),
the VOICE (see Voice_Roster.md), and a register note. Speaker name in the script → this character key.

### [Character Name]  _(voice: [profile] — see Voice_Roster.md)_  _(seed [INT])_
[One line: who they are, their register, the joke of them.]
```
CORE: [short visual prompt — silhouette, wardrobe, age, one defining prop, framing. End-state gets the
global suffix appended automatically. e.g. "an elegant elderly matriarch in black mourning dress and
pearls, severe silver chignon, glacial composure, candlelit interior"]
```

### [Character Name]  _(voice: [profile])_  _(seed [INT])_
[…]
```
CORE: […]
```

---

## B-roll anchors

Non-character establishing shots the script references as `» b-roll: <key>`. Give each a stable CORE.

- **[broll_key]** — `[short core, e.g. "a vast cracked clay basin under a flat grey sky"]`
- **[broll_key]** — `[…]`

## Seed ledger (keep unique within the show)

| key | seed | kind |
|---|---|---|
| [character] | [INT] | character |
| [character] | [INT] | character |

> Look-dev tip: pick a seed, render one test shot per character at the show's defaults, lock the seed once
> the look reads right, then reuse it verbatim everywhere. Seeds are arbitrary fixed ints — just keep them
> distinct within the show.
