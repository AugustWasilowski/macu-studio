# As The World Burns — Character & Prompt Bible

_Show id: `as-the-world-burns`. v0.1 — 2026-06-06. Look-dev DRAFT — seeds/cores proposed, not yet
render-confirmed. Render one test shot per character at the defaults, then lock._

> 🔧 **PIPELINE-CRITICAL — do not rename.** `shotgen.py` / `cardgen.py` find this by the glob
> `docs/shows/as-the-world-burns/*Character_Prompt_Bible.md`. A rename = an empty bible.

T2V prompt library for As The World Burns. **Every shot prompt = CORE + the GLOBAL STYLE SUFFIX; the GLOBAL
NEGATIVE applies to every shot.** Keep cores short — at 384² the model reads silhouette and nouns, not
adjective lists.

---

## Global style suffix (append to every positive prompt)

```
, black and white, grainy vintage analog videotape, 1970s daytime soap opera, soft focus, soft interior lighting, melodramatic, low resolution, washed out
```
> Specializes the universe B&W-analog look toward **daytime soap**: videotape (not film), interior, soft and
> melodramatic — vs The MACU Report's "1970s broadcast news." Keeps it unmistakably MACU, distinctly AWB.

## Global negative (use on every shot)

```
shutterstock, watermark, text, caption, logo, color, colour, modern, smartphone, digital screen, hd, 4k, sharp, blurry, low quality, distorted, deformed, mutated, extra limbs, extra fingers
```
> `shutterstock` is mandatory (suppresses the ModelScope watermark bug). `color`/`colour` hold B&W.

## Render defaults

zeroscope_v2_576w · 24 frames · 384×384 · 30 steps · cfg 15 · extract 8fps (same rig as The MACU Report).
Pin the per-character SEED below so a face is consistent across shots and episodes.

---

## Characters

### Vivian Vandermeer  _(voice: TO CLONE — grave matriarch, see Voice_Roster.md)_  _(seed 81001)_
The matriarch. Controls the Pitcher and therefore everything. Has been "dying" for years; runs brunch like
a war cabinet. Immaculate, glacial, perfectly civil while perfectly cruel. The center the cast orbits.
```
CORE: an elegant elderly matriarch in a black mourning dress and pearls, severe silver chignon, glacial composed expression, candlelit bunker ballroom
```

### Mona  _(voice: TO CLONE — weary, certain, see Voice_Roster.md)_  _(seed 81002)_
The amnesiac who walks in from the ash with one devastating secret she doesn't know she has. The audience
surrogate — lore is delivered TO her, flat, as if she's the unreasonable one for not knowing it.
```
CORE: a gaunt weary young woman in a tattered grey traveling coat, ash-smudged face, haunted certain eyes, standing in a heavy bunker doorway
```

### Brick Vandermeer  _(voice: TO CLONE — handsome, hollow, unbothered, see Voice_Roster.md)_  _(seed 81003)_
The cursed heir. Devastatingly handsome, completely hollow, useless. Subject of the **Resurrection Engine**
(see Story_Arcs.md) — keeps dying and downgrading his form factor until he's Sheldon the turtle. His
crowning insult is that he *still won't stop showing up to brunch.*
```
CORE: a devastatingly handsome young man in a dusty black funeral suit, square jaw, completely unbothered expression, an open pale-wood casket behind him
```

> **Narrator** has no character shot — it's VO over b-roll (the grave soap announcer). Voice only; see
> Voice_Roster.md.
> **Sheldon** (Brick's eventual turtle form) and the bench cast (Dr. Vesper, Cassius Drake, a butler) get
> cores + seeds when they first appear.

---

## B-roll anchors

Referenced in script as `» b-roll: <key>`.

- **lake_mirabel** — `a vast cracked dry clay lakebed under a flat grey sky, the dead basin stretching to the horizon`
- **the_bunker** — `a heavy steel blast door dressed with funeral wreaths and crystal, a chandelier, a butler in tails, opulent interior`
- **the_product** — `a single sealed foil sachet of pale drink powder displayed under glass like a sacred relic, soft votive light`

## Seed ledger (unique within the show; AWB band = 810xx)

| key | seed | kind |
|---|---|---|
| vivian | 81001 | character |
| mona | 81002 | character |
| brick | 81003 | character |
| lake_mirabel | 81010 | b-roll (optional pin) |
| the_bunker | 81011 | b-roll (optional pin) |
| the_product | 81012 | b-roll (optional pin) |

> Look-dev next step: render one test shot per character/anchor at the defaults; confirm Vivian reads
> "glacial matriarch," Mona "ash-walker," Brick "hollow heir"; adjust core wording (not seed) until right,
> then lock. Seeds are arbitrary fixed ints — just keep them distinct.
