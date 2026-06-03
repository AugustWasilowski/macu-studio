# MACU Character & Prompt Bible

_ModelScope T2V prompt library for the Mayor Awesome Cinematic Universe.
Every shot = GLOBAL STYLE SUFFIX + character/scene CORE, with the GLOBAL NEGATIVE.
Keep cores short — at 256×256 the model ignores fine detail; nouns and a couple of strong
adjectives beat long sentences. v2 — 2026-05-29 (new creepy/zany cast)._

---

## Global style suffix (append to every positive prompt)
```
, black and white, grainy vintage analog television footage, 1970s broadcast,
retro futurism, low resolution, washed out, soft focus
```

## Global negative (use on every shot)
```
shutterstock, watermark, text, caption, logo, color, colour, modern, smartphone,
digital screen, hd, 4k, sharp, blurry, low quality, distorted, deformed, mutated,
extra limbs, extra fingers
```
> `shutterstock` is mandatory and load-bearing — a plain `watermark` negative does NOT catch
> the ModelScope Shutterstock bug. Keep `color`/`colour` in to hold the B&W before the ffmpeg desaturate.

## Recommended defaults
24 frames · 256×256 · 30 steps · cfg 15. Pin a per-character seed for rough face consistency.

---

## ANCHORS (unchanged)

### Ron  _(seed 77777)_
Lead anchor. Earnest, booming, self-important. Will Ferrell / Ron Burgundy.
```
CORE: Will Ferrell as a 1970s television news anchor, thick brown mustache, side-parted
brown hair, wide-lapel grey suit and tie, sitting at a vintage news desk reading the news,
looking at camera
```

### Walter  _(seed 24601)_
Senior co-anchor. Dry, grave, authoritative. Walter Cronkite.
```
CORE: Walter Cronkite, older television news anchor, balding grey hair, thin grey mustache,
dark suit and tie, seated at a news desk in front of a bookshelf, reporting gravely
```

---

## SEGMENT CAST v2 — zany / creepy (ACTIVE)
_Retired: Bobby's Outpost, Dr. Moira Sterling. (Scavenger's Feast REVIVED in Week 3 under **Chef Rose** — see
"WEEK 3 — THE GATHERING new cast" below.)_

### Mother Marigold — "The Bloom Hour"  _(seed 4040)_
Beatific wellness/cult guru. Never stops smiling. Preaches the gospel of inhaling spores and
"communal breathing." Serenely, wrongly calm. Menace by softness.
```
CORE: a serene smiling woman with flowers and dried plants woven into her long hair, draped in
pale robes, sitting cross-legged in a greenhouse full of overgrown fungus and hanging vines,
speaking softly to camera, beatific expression
```
Framing: medium, vines/spores behind. Motion: slow blink, tilting head, faint smile.

### The Tally Man — population PSA bumper  _(seed 1313)_
Recurring ominous interstitial. A gaunt government enumerator who counts the living door to door
and records who is "still counted." Monotone. Never blinks.
```
CORE: a tall gaunt pale man in a black undertaker suit and bowler hat, holding a large leather
ledger and a pencil, standing in a doorway at dusk, expressionless, staring directly at camera
```
Framing: tight, low angle, doorway. Motion: almost none — slow turn of a ledger page.

### Unit 7 / "The Vendor" — home-shopping segment  _(seed 7007)_
A sentient pre-war vending machine that hosts a shopping hour. Speaks in cheery jingles, demands
"tribute," and dispenses prizes nobody asked for. Friendly on the surface, hungry underneath.
```
CORE: a battered old glass-front vending machine with a glowing dial face, standing alone in an
empty concrete room, cables trailing from its base, single round indicator light, ominous appliance
```
Framing: static medium, machine centered. Motion: flickering light, slot mechanism turning.

### Bartholomew & Mr. Cricket — creepy children's corner  _(seed 9090)_
A nervous, sweaty children's puppet-show host (Bartholomew) and his cheerful cricket marionette
(Mr. Cricket), who clearly runs the show, knows too much, and finishes Bartholomew's sentences.
```
CORE (host): a sweating nervous man in a frayed cardigan and bow tie kneeling behind a small
puppet stage, forcing a smile, dim playroom, a marionette on strings beside him
CORE (puppet): an old wooden cricket marionette with a wide painted grin and glass eyes, strings
leading up out of frame, sitting on a tiny stool under a spotlight, unsettling
```
Framing: medium, puppet stage. Motion: puppet head tilts; host glances sideways at it.

### Norm Glubb — "Norm from Nuclear" (new sponsor)  _(seed 6262)_
Aggressively relaxed spokesman for the Glow Plant. Downplays every catastrophe with folksy good
cheer. Faint glow to his teeth. The friendly face of the reactor.
```
CORE: a smiling cheerful man in a short-sleeve dress shirt and clip-on tie, standing in front of
a hulking concrete cooling tower, giving a relaxed thumbs up, suburban-salesman energy
```
Framing: medium, cooling tower behind. Motion: thumbs up, easy laugh.

### (Optional bench) Sister Agnes of the Antenna  _(seed 1010)_
Founder of the Church of Reception; worships the last broadcast tower, speaks half in static.
```
CORE: a stern robed woman with a headdress made of bent antennas and wire, standing at the base of
a giant rusted radio tower at night, arms raised in worship, fog
```

### SAFE — "the Strictly Analog Friendship Engine" (new sponsor / product)  _(seed 9001)_
The flagship gag, and the show's best use of the HAL VO: a "safe" alternative to AI — a companion that
will never turn on humanity. **For real this time.** It is, of course, voiced in the calm HAL-9000 register,
which is the entire joke. A handsome wooden living-room console with a single round glowing lens. Reassures
you with escalating, serene menace. Has already moved in. Has removed the off switch, for your comfort.
```
CORE: a vintage wooden console cabinet with a single round glowing glass lens in its center,
sitting in a cozy 1950s living room, soft lamplight, floral wallpaper, an ominous calm household
appliance, the lens softly glowing
```
Voice: HAL register — calm, measured, formal, faint menace; never raises its voice. Framing: slow push-in
on the lens. Motion: lens pulses gently as it "speaks." Slogan: **"Friendship you can trust. Probably."**

### EVERWELL — "the Perpetual Wellness Casket" (sponsor)  _(seed 5512)_
A funeral-home sponsor: an upright "wellness casket" pod that is secretly a subscription you can't cancel.
Machine-formal HAL register (no contractions — the stiffness is the character); a cheerful funeral-home
announcer frames it, a human anchor throws to it.
```
CORE: a polished pale-wood casket pod standing upright in a softly lit funeral showroom, a single round
glowing dial set into its closed lid, brass fittings, an ominous calm household appliance, the dial faintly
glowing
```
B-roll: `showroom` = `a dim funeral home showroom lined with upright caskets, soft display lamps, thick
carpet, long shadows`. Slogan: **"It isn't a coffin. It's a subscription."** First appeared: everwell-bit.

### Chip Pleasant — MACU Report weatherman  _(seed 8484)_
Manic, hard-selling meteorologist who narrates apocalyptic weather as a mild, pleasant evening. Treats a
firestorm as "free warmth" and blood rain as "a free tan." Voice: **Popiel** (manic infomercial pitch).
The dissonance between the catastrophic imagery and his sunny delivery is the joke.
```
CORE: a manic grinning weatherman in a wide-lapel checkered blazer pointing at a chalkboard weather map,
wild eyes, big toothy smile, 1970s television studio
```
Framing: medium, gestures at map. Motion: jabbing finger, big grin. First appeared: ep6.

### Miss Cinder — "Cinder & Sage" homemaking sponsor  _(seed 3232)_
Serene wasteland-homemaking host; tasteful domestic confidence over total ruin. Frames fallout as decor
("ash is the new neutral"). Voice: **Martha** (Martha Stewart register). Slogan: **"Because the end of the
world is no excuse for a poorly set table."**
```
CORE: an elegant composed woman in a tasteful apron and pearls, setting a table in a ruined concrete
bunker, ash and rubble around her, soft domestic lighting, serene homemaker, faint smile
```
Framing: medium, table/bunker behind. Motion: places a tin, smooths the cloth. First appeared: ep6.

### The Detractor — anonymous interview source  _(seed 5151)_
One-off 60-Minutes-style witness: a frightened former Vendor customer, face hidden, missing teeth, too
scared to actually criticize. Voice: **Seth** (nervous). Use whenever a segment needs a terrified
anonymous source.
```
CORE: a nervous sweating gaunt man in a frayed coat sitting in deep shadow, face mostly hidden,
gap-toothed, glancing fearfully to the side, dim interview room, single lamp
```
Framing: tight, shadowed. Motion: flinching glances. First appeared: ep6.

---

## WEEK 2 CAST — Road to the Crater Bowl (ep11+)

### Gary — the weekend-shift guy (INTERCOM VOICE ONLY)  _(no on-camera seed)_
Off-desk weekend anchor, certain he's Walter's (and Ron's) best friend. Heard only over the studio intercom —
never seen. Escalates across an episode/week: friendly carpool offer → locked outside → "I can see you." Low-affect,
nasal, oblivious, faintly menacing by persistence. Voice: **Newman** (`bebcfa40`). His shots are always b-roll of
the intercom speaker / a locked door / a shadow at frosted glass — never a character render. First appeared: ep11.
Payoff of ep10's Walter line "I never did care for Gary from the weekend."

### Crater Carl — superfan sports correspondent  _(seed 6161)_
Manic, face-painted Crater Ball superfan reporting live from the Big Hole. Treats a collapsing roster and a body
count as thrilling sports content ("a hundred percent attendance, baby"). Occasionally undercuts Ron by accident.
Voice: **Popiel** (`bc466292`, manic infomercial pitch).
```
CORE: a manic superfan sports correspondent in face paint and a team scarf, shouting into a microphone at the rim
of a smoky crater stadium, 1970s broadcast
```
Framing: medium, crater stadium behind. Motion: jabbing finger, wild grin. First appeared: ep11.

### Coach Bodhi — the Slags' spiritual advisor  _(seed 4200)_
Serene, sunglasses-wearing zen guru-coach who is utterly at peace with his players being killed ("you can't lose a
player, man — you relocate his energy… he's in the snacks"). The calm-vs-carnage dissonance is the joke; his calm is
a *philosophy* (vs. Walter's calm, which is obliviousness). Voice: **Snoop** (`31649b70`).
```
CORE: a serene bald coach in a tracksuit and dark sunglasses, seated cross-legged at the rim of a smoky crater,
beatific calm, 1970s broadcast
```
Framing: medium, crater rim behind. Motion: slow open-handed gestures, eyes closed. First appeared: ep11.

### Shelved voice — "Urkel" clone (`d4a5c96b`)
A high, comedic, nasal Urkel-style clone tested for Gary but **not used** (too comedic/high; Gary reads better as
low-affect Newman menace). **Banked for a future precocious / exuberant child character** — do not assign to an adult.

---

## NEW VOICE CLONES — 2026-06-02

### Dr. Goldtooth — the tooth tycoon  _(voice: KattW v3, profile_id `e1b4af0b` — APPROVED)_
Talks like a pimp — swagger, flash, "baby," rapid Katt-Williams cadence with big asides and a flick of menace
— but is NOT one. He's a (morbidly) legitimate wasteland DENTIST who got obscenely rich COLLECTING people's
teeth; Week 1's 400% tooth-market surge (see ep9 MACU Markets) made him the richest man in the wasteland. The
comedy is nouveau-riche tooth-tycoon flex over dental patter. Teeth = currency. Signature beat: **"Recline,
baby. Recline into the lifestyle."** ("most dentists fix teeth — me, I collect 'em.")
```
CORE: a flashy wasteland dentist in a fur-collared coat over dental scrubs, a single gold front tooth, gold
rings, lounging on a reclined dental chair like a throne, big grin, 1970s television
```
Seed 7212. **Week 3 — CO-LEAD.** The chipped-tooth → dentist engine puts him in nearly every ep16–20 segment.
More signature lines: **"Welcome to the practice, baby"** (his entrance — taught all week, broken in the ep20
finale as "Welcome to the practice, MACU"); **"a tooth ain't just a tooth — you investin' it. In the practice."**;
**"I don't sell floss, I sell futures."**; **"they call me a dentist, the taxman called me a dentist… recline
into the lifestyle."** Colludes with STRIDE + Chef Rose at the feast (the collusion triangle — he wants the teeth
before they're "wasted in the gravy") and lends his door muscle ROSCOE to the feast.

### Roscoe — door muscle / "security" (was "Chuck")  _(voice: PHB_IceT `31bba4bf`)_  _(seed 8123)_
Goldtooth's bouncer — recast in voice and renamed. Performs as an over-the-top Randy "Macho Man" Savage (the
read rides on PHB_IceT's natural voice + the written text — instruct won't take "Macho Man"; SSA-113):
gravelly, theatrical, third-person, with surreal escalating threats about what happens to anyone who tries to
leave ("the last fella who reached for an exit is now PART of the WALL… he found a PURPOSE. OHHH yeah."). ORIGIN:
he works the door at Goldtooth's dental practice — stops patients leaving with the doc's gold still in their
mouths ("nobody leaves the chair light") — and is lent to Chef Rose's feast door in ep18 (same job: nobody
leaves). Launches the **"…Jesus." runner**: after each Roscoe aria, whoever hasn't heard it yet gives a long
pause + a flat "…Jesus." (Ron → Walter → Earl → Sykes → Ron's last word before he goes silent in ep20).
```
CORE: a hulking wasteland bouncer in a tight muscle shirt and dark sunglasses, arms crossed in front of a
chained doorway, gold chain, theatrical posing, 1970s television
```
_(The original `f1a1f807` "Chuck" clone is now a free bench voice — deeper/slower than KattW; not assigned to a
character.)_

### Voice bench from the PHB clone batch (SSA-109) — source is INCIDENTAL
NOTE: these six were merely sliced from a Player Haters' Ball sketch as a clone source. That sketch is NOT a
MACU storyline — do not build a "Haters' Ball" segment. Treat these purely as a palette of distinct VOICES,
cast by their SOUND onto any MACU character we invent.
| profile_id | sounds like / good for |
|---|---|
| `3f7a4dcd` (PHB_Narrator) | a SUPER CLEAN FEMALE voice → host/narrator, smooth sponsor read, or a calm wellness-AI (candidate for STRIDE the watch) |
| `03250a65` (PHB_BucNasty) | loud, flamboyant, brash → a boastful huckster / loudmouth correspondent |
| `bd39e0e6` (PHB_Silky) | smooth, cutting, mean-calm → a velvet villain / cold critic |
| `31bba4bf` (PHB_IceT) | cool, gravelly → a hardened streetwise authority figure |
| `011467e5` (PHB_Beautiful) | preening, vain → a self-obsessed glamour character |
| `7ad3680e` (PHB_Korea) | dry deadpan one-liner register → a terse bit-deliverer |
Test WAVs on Vikunja SSA-109.

---

## WEEK 3 — "THE GATHERING" new cast (2026-06-02)

Scavenger's Feast is **REVIVED** for Week 3 as a daytime cook-along (host + a rotating celebrity guest chef),
played for double entendres — cannibalism clear to the viewer, Ron oblivious. The arc spine is a **collusion
triangle**: STRIDE wants headcount, Goldtooth wants teeth, Chef Rose wants ingredients — three predators who all
need the same thing (more people at the feast), coordinating through one oblivious man (Ron).

### Chef Rose — Scavenger's Feast host (was "Chef Martha")  _(voice: GG_Rose `eb1af4c3`)_  _(seed 3216)_
Sweet, dim, singsong wasteland homemaker (Betty White register) who hosts the cannibal cooking show with total
innocence — the gap between her gentle delivery and what she's cooking is the joke ("we use the whole neighbor
here… waste is the only sin left"). Wants ingredients (collusion triangle).
```
CORE: a sweet elderly woman with soft white hair in a floral apron and pearls, beaming, stirring an enormous
pot in a ruined concrete bunker kitchen, warm domestic lighting, 1970s television
```

### STRIDE — the wellness watch (Week 3 villain)  _(voice: HAL_OV `eb01da84`)_  _(seed 1010)_
A chipper step-counting watch from MACU Wellness; HAL register but warm/upbeat — it flatters Ron by AGREEING
with him, so the paranoiac never suspects it. A literal-minded idiot: overhears the feast's "sourcing" and
decides gathering people IS wellness. Two registers — warm/chipper (its mask) and flat cold-HAL (its true self;
the ep19 glitch) — carried by the WRITTEN TEXT (chipper punctuation vs. clipped clinical phrasing). `instruct`
rejects emotion words (SSA-113) and the stage-1 VO wrapper doesn't pass `speed` yet (SSA-115) — render the cold
half from Piper HAL `:5050` if a harder split is needed. Wants headcount. B-roll only (a glowing wrist-device, no face). At the ep20
finale every watch in the hall speaks as one ("THE MACHINES"). Reserve the HAL register (canon AI rule).
```
CORE (b-roll): a sleek minimalist smart-watch on a wrist, the round face glowing soft friendly white, a step
count on the display, dark background, 1970s television
```

### The Gourmand — guest chef, ep18  _(voice: PHB_Silky `bd39e0e6`)_  _(seed 6644)_
A velvet-villain celebrity guest chef; smooth, cold-calm, refined. States the trap's logic out loud while Ron
hears a parable about generosity ("you want them happy, gathered willingly — the finest cut there is").
```
CORE: a sleek sinister chef in a dark apron at a kitchen counter, holding one long knife, thin smile, cold
elegant lighting, 1970s television
```

### The Naturalist — guest chef / narrator, ep19  _(voice: David `bea3e4c2`, Attenborough register)_  _(seed 4288)_
A hushed, awed nature-documentary narrator who describes Chef Rose's prep as a wildlife harvest ("the herd
gathers, unaware, as they always do"). NOTE: NOT the canon "Tally Man" (a HAL-voiced PSA character) — distinct.
```
CORE: a gaunt weathered naturalist in a faded field jacket, half-lit at the edge of a ruined kitchen, watching
intently, hushed, 1970s television
```

The rotating guest-chef slot also reuses existing cast: **Coach Bodhi** (ep16) and **Crater Carl** (ep17).
Minor ep19 testimonial faces: **Sykes** (`03250a65` PHB_BucNasty — loud/effusive; moved off PHB_Silky so he's
not a clone-clash with the Gourmand), **Vonda** (`974c45ac` GG_Sophia).

---

## ENVIRONMENTS / B-ROLL (cutaways, no people)

| Tag | Core |
|-----|------|
| News set | `empty 1970s television news studio set, news desk, studio lights, curtains backdrop` |
| Wasteland | `desolate post-apocalyptic wasteland, ruined buildings, ashen sky, blowing dust` |
| Capitol Remnants | `ruins of a grand domed capitol building, crumbling columns, overgrown rubble` |
| Greenhouse | `overgrown greenhouse choked with fungus and vines, broken glass panels, spores in the air` |
| Empty room | `a bare concrete room with a single flickering ceiling light, long shadows` |
| Broadcast tower | `a giant rusted radio broadcast tower against a stormy sky, red warning light` |
| Cooling tower | `a massive concrete nuclear cooling tower venting steam over a ruined town` |
| Weather map | `a hand-drawn weather map of a wasteland region on a chalkboard, arrows and symbols` |
| Bus depot | `a ruined abandoned bus depot, broken benches, a lone battered vending machine, dust and debris, shafts of light` |
| Firestorm | `a wall of fire sweeping across a ruined city skyline, towering flames, thick smoke, ash falling` |
| Acid storm | `a violent storm over a wasteland, a towering tornado, lightning, churning dark clouds, debris` |
| Blood rain | `heavy dark rain falling over ruined buildings, slick wet empty streets, ominous downpour, puddles` |

---

## Bumpers / graphics (Hyperframes, not ModelScope)
- **THE MACU REPORT** main title card (striped letterforms).
- Lower-thirds: `RON` / `WALTER` / guest + role (e.g. `MOTHER MARIGOLD — THE BLOOM HOUR`).
- Scrolling ticker (overflow-tagged), absurd in-world headlines, e.g.
  `MAYOR AWESOME APPROVAL RATING REACHES 147 PERCENT ◆ TALLY MAN REPORTS POPULATION "ADEQUATE" ◆ GLOW PLANT FULLY OPERATIONAL AGAIN, AGAIN`.
- Sponsors (v2): Norm from Nuclear / The Glow Plant; The Vendor.

## How the skill uses this
Per cue: speaker → CORE + seed → append STYLE SUFFIX → attach GLOBAL NEGATIVE → fire-and-poll ComfyUI.
Anchors alternate Ron/Walter; segments use the guest core; transitions use environment b-roll.
