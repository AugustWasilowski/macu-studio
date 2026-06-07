# As The World Burns — Voice Roster

_Show id: `as-the-world-burns`. v0.1 — 2026-06-06._

Character → voice index for AWB. Keep in sync with `Character_Prompt_Bible.md` and the show's
`episode_defaults.voice` in `studio/shows.json`. For delivery shaping (speed / instruct / seed) see
`docs/_common/OmniVoice_Voice_Tips.md`.

---

## Engines

- **OmniVoice** (:3900) — cloned human voices. Easiest: the **Create Voice** button on the Audio page
  (upload a clip → clone). CLI: `/mnt/storage/shares/MACU/voices/clone_one.sh`. Needs a short clean clip.
- **Piper HAL** (:5050) — synthetic/flat fallback. AWB's manifest default is currently `piper`, so until
  the clones exist, all VO renders as HAL — usable for a rough cut, not the final soap tone.

## Roster

| Character | Engine | Profile | id | Register / delivery |
|---|---|---|---|---|
| Narrator | TBD | — | — | Grave, unhurried soap announcer — "voice of a thousand afternoons." The hourglass tagline + lore + "next week" teaser. |
| Vivian Vandermeer | TO CLONE | — | — | Elderly matriarch; glacial, immaculate, cruelly civil. Slow, measured, never raises her voice. |
| Mona | TO CLONE | — | — | Weary, ash-walked, certain. Low energy but unwavering — the outsider stating impossible things plainly. |
| Brick Vandermeer | TO CLONE | — | — | Handsome, hollow, mildly inconvenienced by his own deaths. Pleasant, unbothered, faintly bored. |

## To clone (TODO — needs reference clips from August)

- **Vivian** — aim: a Maggie-Smith-dowager register; cold velvet. Source clip = [plan].
- **Mona** — aim: tired, grounded, no melodrama in the voice (the world is melodramatic enough). Source = [plan].
- **Brick** — aim: soap-hunk flat affect; charming and empty. Source = [plan].
- **Narrator** — aim: classic daytime-soap announcer gravitas. Could be an OmniVoice clone OR a deep, slow
  Piper voice if we want the announcer to feel slightly synthetic/in-universe. Decide during awb-001 VO.

## Notes

- A voice may be reused across non-co-appearing characters (The MACU Report does this).
- Per episode, the speaker→voice mapping also lives in the manifest (`voice` / `characters{}`), so a render
  never depends solely on this doc — this is the human-canon index.
