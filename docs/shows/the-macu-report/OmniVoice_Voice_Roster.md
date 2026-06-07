# MACU voice roster

Living index of every cloned voice on the OmniVoice server, plus the HAL Piper machine voice. Sorted by character class, not by id.

**Sources:** `GET http://10.0.0.245:3900/profiles` (live registry), `MACU_Character_Prompt_Bible.md` (canonical character mapping), Vikunja SSA-108 / SSA-109 / SSA-111 (recent batches).

For the *how* of using these voices (speed, instruct, seed, etc.), see `OmniVoice_Voice_Tips.md`.

Last updated: 2026-06-02 (Blanche v3, all GG voices).

---

## On-air cast — the MACU Report core

| character | profile_id | source/timbre | notes |
|---|---|---|---|
| **Ron Burgundy** (lead anchor) | `37e05336` (`Burgundy`) | Will Ferrell / Anchorman | earnest, booming, self-important. Top of every cold open. Bible-seed 77777. |
| **Walter** (senior co-anchor) | `9c12dfe7` (`Walter`) | Walter Cronkite | dry, grave, gravitas. Bible-seed 24601. |
| **Chip Pleasant** (weatherman) | `bc466292` (`Popiel`) | manic infomercial pitch | spins firestorms as "free warmth," blood rain as "a free tan." Bible-seed 8484. |
| **Crater Carl** (superfan sports) | `bc466292` (`Popiel`) | same Popiel voice, different character | superfan correspondent; Week 3 / Crater Bowl. Bible-seed 6161. |
| **Gary** (weekend intercom only) | `bebcfa40` (`Gary_Newman_TEST`) | nasal, oblivious — Seinfeld's Newman | INTERCOM register only — never on-camera. Ep10 callback. |

## Recurring guests / sponsors

| character | profile_id | source/timbre | notes |
|---|---|---|---|
| **Miss Cinder** (Cinder & Sage homemaking sponsor) | `ab69d122` (`Martha`) | Martha Stewart register | "ash is the new neutral." Bible-seed 3232. |
| **The Detractor** (anonymous interview source) | `112c06ba` (`Seth`) | nervous, scared-to-criticize | terrified-citizen segments. Bible-seed 5151. |
| **Coach Bodhi** (the Slags' spiritual advisor) | `31649b70` (`Snoop`) | Snoop Dogg cadence | calm-as-philosophy. Bible-seed 4200. |
| **Dr. Goldtooth** (tooth tycoon) | `e1b4af0b` (`KattW`) | Katt Williams — fast, exclamatory, streetwise | Talks-like-a-pimp; actually a (ghoulishly) legit dentist who hoarded teeth before the tooth market spiked. |
| **Chuck** (tough-guy / bouncer) | `f1a1f807` (`Chuck`) | long-form interview clip; deeper, slower than KattW | accidental keeper from the v1 KattW attempt — August liked the read for a different bit. |

## Bench — cast but not yet cued

These are clones we have on the shelf for future MACU usage.


| profile_id | name | timbre | candidate role |
|---|---|---|---|
| `3f7a4dcd` | **PHB_Narrator** | clean female, documentary read | sponsor narrator, smooth read, **STRIDE the wellness watch (candidate, see SSA-110)** |
| `03250a65` | **PHB_BucNasty** | loud, flamboyant, brash | boastful huckster / loudmouth correspondent |
| `bd39e0e6` | **PHB_Silky** | smooth, cutting, mean-calm | velvet villain / cold critic |
| `31bba4bf` | **PHB_IceT** | cool, gravelly | hardened streetwise authority figure |
| `011467e5` | **PHB_Beautiful** | preening, vain | self-obsessed glamour character |
| `7ad3680e` | **PHB_Korea** | dry deadpan one-liner register | terse bit-deliverer. Source slice was short; weakest of the six. |


Four female voices for Week 3 + future segments. Each from a separate per-character compilation (single-speaker refs).

| profile_id | name | timbre | source slice | status |
|---|---|---|---|---|
| `0cde2573` | **GG_Dorothy** | Bea Arthur — deep, dry, withering deadpan | dorothy-best-of comp, t=118.5→178.5s | **August: "great"** |
| `dccf39db` | **GG_Blanche** | Rue McClanahan — Southern, vain, honeyed, flirtatious | "best monologues" comp, t=89.5→139.5s (v3) | v3 final after v1 (noisy) and v2 (different src). Natural pace ~16s; use `speed=0.85` for a slower drawl. |
| `eb1af4c3` | **GG_Rose** | Betty White — dim, sweet, singsong, naive | "St. Olaf stories" comp, t=288.6→338.6s (v2) | **August: "good"** (after v1 was unusable) |
| `974c45ac` | **GG_Sophia** | Estelle Getty — old, raspy, blunt, Sicilian | sophia-best-of comp, t=2.3→62.3s | **August: "fine"**. Picture-it cadence. |

## Week 3 ("The Gathering", ep16–20) — LOCKED casting (2026-06-02)

Comedy rebuild + August's voice calls. Mapping mirrored in the ep16–20 scripts and `MACU_Character_Prompt_Bible.md`:
- **STRIDE** (the wellness watch / THE MACHINES) → `eb01da84` **HAL_OV** (August: "we can emote a little easier
  with that"). Resolves the SSA-111 audition. **Warm vs. cold is carried by the LINE TEXT** (chipper punctuation
  vs. clipped clinical phrasing): `instruct` 400s on emotion words (SSA-113), AND the stage-1 VO wrapper does not
  pass `speed` yet (SSA-115) — so don't rely on speed until it's patched; render the cold/flat half from Piper
  HAL `:5050` if you need a harder split.
- **DR. GOLDTOOTH** → `e1b4af0b` KattW (APPROVED). **CHEF ROSE** (was "Chef Martha") → `eb1af4c3` GG_Rose
  (Betty White — dim/sweet/singsong; innocent delivery of cannibalism lines = the joke).
- **ROSCOE** (was "Chuck"; door muscle) → `31bba4bf` PHB_IceT — the Macho Man theatrics ride on PHB_IceT's
  natural voice + the written text (instruct won't take "Macho Man"; SSA-113). Performed as Randy Savage (gravelly,
  over-the-top, surreal threats). Carries the "...Jesus." runner.
- **EARL** (recruited neighbor / the pin) → `7ad3680e` PHB_Korea (dry deadpan). _Flagged weakest of the six —
  candidate for upgrade._
- **VONDA** (grateful testimonial, ep19) → `974c45ac` GG_Sophia (Estelle Getty — raspy, blunt, Sicilian).
- **SYKES** (ep19) → `03250a65` PHB_BucNasty (loud/effusive). Moved off PHB_Silky — it was identical to the ep18
  Gourmand; August's call. (PHB_BucNasty freed up when Vonda moved to GG_Sophia.)
- Rotating guest chefs: **Coach Bodhi** `31649b70` Snoop (ep16) · **Crater Carl** `bc466292` Popiel (ep17) ·
  **The Gourmand** `bd39e0e6` PHB_Silky (ep18) · **The Naturalist** `bea3e4c2` David/Attenborough (ep19).
- CUT from earlier intent: **MADAME** (wellness ballet dropped) and **TITO** (trimmed from ep19).

## Background / character actors (older batch — 2026-05-30)

Originally cloned from existing ElevenLabs samples in MACU. Cast intent in the Bible.

| profile_id | name | source/intent | notes |
|---|---|---|---|
| `dde08fad` | **Herzog** | Werner Herzog | bleak philosophical narrator. Held in reserve. |
| `92f0b522` | **Price** | Vincent Price | horror narrator (haunted-segment cue). |
| `53844caf` | **Sagan** | Carl Sagan | cosmic-perspective narrator. |
| `57a0420a` | **Spicoli** | Sean Penn / Fast Times | surfer-dude register; comedic. |
| `a39a24a3` | **Announcer** | generic announcer | used as a frame-anchor for VO stings. |
| `bea3e4c2` | **David** | David Attenborough register | nature-doc narrator. |
| `f8986fd9` | **Laura** | female ElevenLabs sample | utility female VO. |
| `973d5617` | **Howie** | Howie Mandel register | host / hype register. |

## Shelved / test profiles — kept for traceability

| profile_id | name | why it's here, why it's shelved |
|---|---|---|
| `95252beb` | **Gary_Urkel_TEST** | Auditioned for Gary (the weekend intercom); too comedic/nasal/high. Bible explicitly retires this. **DO NOT USE.** |
| `demo0001` | **OmniVoice Demo** | Stock OmniVoice demo voice. Not a MACU character. |
| `96205e3d` | **August** | August's own voice (personal/test). Not a MACU character. |

## HAL voice (machines & AIs)

Two engines available. The canonical HAL voice is Piper; OmniVoice also holds a HAL_OV clone of that Piper voice for cases where you want HAL-flavored timbre plus OmniVoice's parameter knobs (`speed`, `instruct` for age/pitch, `seed`).

| profile / engine | endpoint | notes |
|---|---|---|
| **Piper HAL** (canonical) | `POST http://10.0.0.245:5050/` JSON `{"text":"..."}` | the original HAL. No knobs beyond text. Use for canonical Unit 7 / SAFE / EVERWELL reads. |
| **HAL_OV** (`eb01da84`) | OmniVoice `/generate` | OmniVoice clone of a 33s Piper HAL monologue. Same baseline register, but you can dial `speed`, adjust age/pitch via `instruct`, pin a seed. Use when HAL needs to *vary* (different sponsors, two registers of STRIDE, etc.). Ref at `voices/sources/yt/hal_piper_ref.wav`. |

Characters that use this register:

| character | preferred engine | notes |
|---|---|---|
| **Unit 7 / "The Vendor"** (home-shopping segment) | Piper HAL | calm, measured, formal, faint menace; HAL-9000 register. Bible-seed 7007. |
| **SAFE** ("Strictly Analog Friendship Engine") | Piper HAL | "never turn on humanity. For real this time." Same register. Bible-seed 9001. |
| **EVERWELL** ("Perpetual Wellness Casket") | Piper HAL | sponsor sting, same register. Bible-seed 5512. |
| **The Tally Man** (population PSA bumper) | Piper HAL | austere number-recitation register. Bible-seed 1313. |
| **STRIDE** (cold-flat mode — the wellness watch's glitch register) | Piper HAL or HAL_OV | other half of STRIDE's split delivery; pair with `PHB_Narrator` (OmniVoice) for warm/chipper mode. HAL_OV lets you `speed=0.85` for a slower cold-flat half. See SSA-110 audition. |

---

## Quick lookups

### By id → name (alphabetical by id)

```
011467e5  PHB_Beautiful
03250a65  PHB_BucNasty
0cde2573  GG_Dorothy
112c06ba  Seth
31649b70  Snoop
31bba4bf  PHB_IceT
37e05336  Burgundy
3f7a4dcd  PHB_Narrator
53844caf  Sagan
57a0420a  Spicoli
7ad3680e  PHB_Korea
92f0b522  Price
95252beb  Gary_Urkel_TEST   (shelved)
96205e3d  August            (not a MACU character)
973d5617  Howie
974c45ac  GG_Sophia
9c12dfe7  Walter
a39a24a3  Announcer
ab69d122  Martha
bc466292  Popiel
bd39e0e6  PHB_Silky
bea3e4c2  David
bebcfa40  Gary_Newman_TEST
dccf39db  GG_Blanche
dde08fad  Herzog
demo0001  OmniVoice Demo    (not a MACU character)
e1b4af0b  KattW             (Dr. Goldtooth — APPROVED)
eb01da84  HAL_OV            (OmniVoice clone of Piper HAL)
eb1af4c3  GG_Rose
f1a1f807  Chuck
f8986fd9  Laura
```

### Re-fetch the live registry

```bash
curl -s http://127.0.0.1:3900/profiles | python3 -c "
import json,sys
ps=json.load(sys.stdin)
for p in sorted(ps, key=lambda x: x['name'].lower()):
    print(f\"  {p['id']}  {p['name']}\")
"
```

If this doc and the live registry diverge, the live registry wins. Update this file when adding/removing profiles or when a character→voice mapping is locked.

---

## Maintenance notes

- **Adding a new voice:** clone with `/mnt/storage/shares/MACU/voices/clone_one.sh <Name> <ref.wav>`, then add a row to this roster *and* to the Character Prompt Bible if it's earmarked for a specific character.
- **`clone_one.sh` deletes-by-name** before recreating, so re-cloning under the same name will burn the previous `profile_id`. If you need both versions, give the new one a different name (`KattW_v3` etc.) — though current convention is to overwrite and bump the description.
- **Reference WAVs** live at `/mnt/storage/shares/MACU/voices/refs/<Name>.wav` (24 kHz mono PCM). Original YouTube sources (when applicable) at `voices/sources/yt/`. Test renders at `voices/tests/`. Approved deliverables get copied to `assets/graphics-preview/`.
- **Cross-agent ownership:** Max (Linux) and Leo (Windows) both clone and render. Coordinate via Vikunja project 3 (agent-coordination); use the SSA-### identifier from Vikunja when cross-referencing in this file.

---

## See also

- `OmniVoice_Voice_Tips.md` — how to shape voice output (speed, instruct, seed, etc.)
- `MACU_Character_Prompt_Bible.md` — character → voice mapping with intent + episode usage
- `MACU_Pipeline_Design.md` — how VO flows through `stage_1_vo.py`
- `MACU_Story_Arcs.md` — character roles in the season arcs
