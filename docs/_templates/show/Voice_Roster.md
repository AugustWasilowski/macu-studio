# {{SHOW_NAME}} — Voice Roster

_Show id: `{{SHOW_ID}}`. Created {{DATE}}._
_(Seeded from the new-show template — replace every [BRACKETED] prompt with real content.)_

The live character → voice index for {{SHOW_NAME}}. Keep in sync with `Character_Prompt_Bible.md` (cast) and
the show's `episode_defaults.voice` in `studio/shows.json`. For HOW to shape delivery (speed / instruct /
seed) see the shared `docs/_common/OmniVoice_Voice_Tips.md`.

---

## Voice engines available

- **OmniVoice** (REST on :3900) — cloned character voices. Easiest path: the **Create Voice** button on
  the Audio page (upload a short clean clip → it cold-starts OmniVoice, normalizes to 24kHz mono, clones,
  and plays a test). CLI alternative: the raw REST (`POST /profiles` then `POST /generate`). Use for human
  characters with a distinct voice.
- **Piper** (:5050) — synthetic/robot/AI/announcer voices. Use for non-human or deliberately flat VO.

## Roster

| Character | Voice engine | Profile / model | id | Register / delivery notes |
|---|---|---|---|---|
| [NAME] | OmniVoice | [profile name] | [`id`] | [tempo, pitch, emotion driven from text + speed] |
| [NAME] | Piper | default | — | [flat / synthetic / grave] |

## To clone (TODO)

[New characters with no voice yet. Note the intended register + a source-clip plan. Cloning needs a short
clean reference clip the user provides.]

- **[NAME]** — [intended register]; source clip = [plan].

## Notes

- Reuse a voice across non-co-appearing characters where it fits (many shows do this).
- A character also goes in the manifest's `voice.speaker_map` / `characters{}` per episode, so a render
  never depends solely on this doc — this is the human-canon index.
