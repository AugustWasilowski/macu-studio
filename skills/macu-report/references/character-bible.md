# MACU Character & Prompt Bible

Prompt library for The MACU Report. Every shot = a character/scene **core** + the **global style suffix**,
rendered with the **global negative**. Keep cores short — the model renders at 384×384, so nouns and a couple
of strong adjectives beat long sentences. Pin a per-character **seed** so a recurring face stays roughly
consistent across an episode.

## Global style suffix (append to every positive prompt)
```
, black and white, grainy vintage analog television footage, 1970s broadcast,
retro futurism, low resolution, washed out, soft focus
```

## Global negative (every shot)
```
shutterstock, watermark, text, caption, logo, color, colour, modern, smartphone,
digital screen, hd, 4k, sharp, blurry, low quality, distorted, deformed, mutated,
extra limbs, extra fingers
```
The `shutterstock` term is legacy belt-and-suspenders. The real watermark fix was swapping the model to
`zeroscope_v2_576w` (the DAMO ModelScope checkpoint had the watermark baked into its weights). Keep the
negative anyway — `color/colour` also helps hold the B&W before the jank filter's `hue=s=0` finishes it.

---

## Voice casting

Each character has a cloned voice (OmniVoice); **HAL (Piper) is reserved for AI/appliance characters** — that
contrast is the joke. Set these in the manifest's `voice.speaker_map` (keyed by the cue `speaker` string).
Full catalog + profile IDs are in `manifest-schema.md`.

| character (cue speaker) | voice | feel |
|---|---|---|
| RON | Burgundy | Will Ferrell anchor swagger |
| WALTER | Walter | Cronkite gravity |
| MOTHER MARIGOLD | Laura | friendly, disarming |
| TALLY MAN | David | Attenborough gravitas → creepy |
| THE VENDOR | **HAL** | machine (Piper) |
| BARTHOLOMEW | Seth | Rogen nervous energy |
| MR. CRICKET | Snoop | laid-back drawl vs. creepy puppet |
| NORM | Howie | cheerful "How It's Made" host |
| ANNOUNCER | Announcer | generic commercial pitch |
| SAFE | **HAL** | machine (Piper) |
| EVERWELL | **HAL** | machine (Piper) — appliance/AI |

When you invent a character, cast them from the catalog and add a row here. If nothing fits, a new voice can
be cloned on Max (`voices/clone_one.sh`) — flag it in the render handoff.

---

## ANCHORS (always present)

### Ron  _(seed 77777)_
Lead anchor. Earnest, booming, self-important. Will Ferrell / Ron Burgundy.
```
Will Ferrell as a 1970s television news anchor, thick brown mustache, side-parted brown hair,
wide-lapel grey suit and tie, sitting at a vintage news desk reading the news, looking at camera
```

### Walter  _(seed 24601)_
Senior co-anchor. Dry, grave, authoritative. Walter Cronkite.
```
Walter Cronkite, older television news anchor, balding grey hair, thin grey mustache, dark suit
and tie, seated at a news desk in front of a bookshelf, reporting gravely
```

---

## RECURRING SEGMENT CAST (zany / creepy)

### Mother Marigold — "The Bloom Hour"  _(seed 4040)_
Beatific wellness/cult guru; never stops smiling; preaches inhaling spores. Menace by softness.
```
a serene smiling woman with flowers and dried plants woven into her long hair, draped in pale robes,
sitting cross-legged in a greenhouse full of overgrown fungus and hanging vines, speaking softly to
camera, beatific expression
```

### The Tally Man — population PSA bumper  _(seed 1313)_
Gaunt government enumerator who counts the living door to door. Monotone, never blinks.
```
a tall gaunt pale man in a black undertaker suit and bowler hat, holding a large leather ledger and
a pencil, standing in a doorway at dusk, expressionless, staring directly at camera
```

### Unit 7 / "The Vendor" — home-shopping segment  _(seed 7007)_
Sentient pre-war vending machine; cheery jingles; demands "tribute." Friendly surface, hungry underneath.
```
a battered old glass-front vending machine with a glowing dial face, standing alone in an empty
concrete room, cables trailing from its base, single round indicator light, ominous appliance
```

### Bartholomew & Mr. Cricket — creepy children's corner  _(seeds 9090 / 9091)_
Sweating puppet-show host and his cricket marionette, who clearly runs the show and knows too much.
```
host (9090):   a sweating nervous man in a frayed cardigan and bow tie kneeling behind a small puppet
               stage, forcing a smile, dim playroom, a marionette on strings beside him
puppet (9091): an old wooden cricket marionette with a wide painted grin and glass eyes, strings
               leading up out of frame, sitting on a tiny stool under a spotlight, unsettling
```

### Norm Glubb — "Norm from Nuclear"  _(seed 6262)_
Aggressively relaxed Glow Plant spokesman; downplays catastrophe with folksy cheer.
```
a smiling cheerful man in a short-sleeve dress shirt and clip-on tie, standing in front of a hulking
concrete cooling tower, giving a relaxed thumbs up, suburban-salesman energy
```

### SAFE — "the Strictly Analog Friendship Engine"  _(seed 9001)_
The flagship gag and the best use of the HAL voice: a "safe" alternative to AI that will never turn on
humanity — *for real this time* — voiced in calm HAL register. A wooden living-room console with a single
glowing lens/screen; reassures with escalating serene menace.
```
a vintage wooden console cabinet with a single round glowing glass lens in its center, sitting in a
cozy 1950s living room, soft lamplight, floral wallpaper, an ominous calm household appliance, the
lens softly glowing
```
Slogan: **"Friendship you can trust. Probably."**

### (Bench) Sister Agnes of the Antenna  _(seed 1010)_
Founder of the Church of Reception; worships the last broadcast tower; speaks half in static.
```
a stern robed woman with a headdress made of bent antennas and wire, standing at the base of a giant
rusted radio tower at night, arms raised in worship, fog
```

_Retired (don't reuse without reason): Bobby's Outpost, Chef Martha / Scavenger's Feast, Dr. Moira Sterling._

---

## ENVIRONMENTS / B-ROLL (cutaways, no people)

| key | core |
|-----|------|
| news_set | `empty 1970s television news studio set, news desk, studio lights, curtains backdrop` |
| wasteland | `desolate post-apocalyptic wasteland, ruined buildings, ashen sky, blowing dust` |
| capitol_remnants | `ruins of a grand domed capitol building, crumbling columns, overgrown rubble` |
| empty_room | `a bare concrete room with a single flickering ceiling light, long shadows` |
| greenhouse | `overgrown greenhouse choked with fungus and vines, broken glass panels, spores in the air` |
| broadcast_tower | `a giant rusted radio broadcast tower against a stormy sky, red warning light` |
| cooling_tower | `a massive concrete nuclear cooling tower venting steam over a ruined town` |
| weather_map | `a hand-drawn weather map of a wasteland region on a chalkboard, arrows and symbols` |

---

## Inventing a new character (do this often — MACU loves new weirdos)

1. Give them a one-line hook (what's funny/creepy about them) and a register that plays in the HAL voice.
2. Write a short core: a person/object + setting + 2–3 strong adjectives. No long sentences.
3. Assign a fresh seed (any 4–5 digit number not already used above).
4. Add the block to this file under RECURRING SEGMENT CAST so it's canon next time.
5. If they anchor a sponsor/ad, note the slogan and add the sponsor to world-lore.

Good MACU registers: cult-serene, bureaucratic-ominous, too-cheerful-spokesman, sentient-appliance,
children's-host-gone-wrong, doomsday-preacher. Avoid retreading retired bits (cars, cooking, AI-defense).
