---
name: macu-report
description: >-
  Collaboratively write and generate an episode or segment of The MACU Report — the black-and-white,
  post-apocalyptic, retro-futurist faux-newscast in August's Mayor Awesome Cinematic Universe (MACU).
  Use this whenever August wants to make a MACU episode, write a MACU Report, add a new segment / ad /
  sponsor bit, invent a new MACU character, draft a MACU script, or "kick off generation" of a MACU video.
  Trigger on phrases like "new MACU episode", "write a MACU Report", "MACU segment/ad/character",
  "make episode N", "let's generate the MACU video", or any mention of Ron, Walter, The MACU Report, or the
  Mayor Awesome universe — even if the word "skill" is never said. The skill brainstorms and writes the
  script with August first, builds the episode manifest, and (only on his explicit OK) hands the render off
  to Max via Vikunja.
---

# The MACU Report — episode generator

The MACU Report is a recurring fake newscast inside the **Mayor Awesome Cinematic Universe (MACU)**: a
comedic, intentionally-janky, black-and-white, analog, post-apocalyptic retro-future. Two anchors (Ron and
Walter) cut to absurd, often creepy segments, ads, and sponsors. The "bad early-AI-video" look is the joke.

This skill drives the whole creative front end: **brainstorm + write the script with August → turn it into a
render manifest → hand the heavy generation off to Max.** August authors here on Leo (his Windows box / this
session); all GPU + audio + assembly work runs on **Max** (the Linux home server), reached over a shared
Syncthing folder and the Vikunja coordination board.

## Before you start — read the references

These hold the canon and the mechanics. Read the ones you need; don't reinvent them:

- `references/character-bible.md` — the cast, their locked ModelScope/zeroscope **prompt cores + seeds**, the
  global style suffix + negative, environments/b-roll, sponsors, and how to invent new characters.
- `references/world-lore.md` — MACU canon: the AI Wars of 2028, geography, tone rules, running gags.
- `references/manifest-schema.md` — the exact `manifest.json` shape, the **locked render settings** (do not
  regress these), music + subtitle blocks, and authoring conventions (seed reuse, b-roll keys, title slots,
  per-shot timing).
- `references/pipeline-and-handoff.md` — what Max's pipeline does end-to-end, the gotchas to respect, and the
  **precise Vikunja handoff procedure** (project, user ids, the assignee proxy, how to ping and poll).
- `references/joke-engineering.md` — how to build and pay off comedy across an episode (seed-and-detonate,
- `references/OmniVoice_Voice_Tips.md` (BUNDLED) — voice SHAPING: the `speed` / `seed` / `instruct` / `guidance_scale` knobs and the full `/generate` reference. Two rules that bite: (1) `instruct` is a CONSTRAINED voice-design vocab (gender/age/pitch/accent/whisper) and 400s on emotion words — drive warm/cold/urgent from the LINE TEXT (punctuation), not `instruct`; (2) the stage-1 OmniVoice wrapper does NOT pass `speed` yet, so until it's patched, differentiate registers by text and render a cold/flat MACHINE register (e.g. STRIDE cold) from Piper HAL `:5050`. The live voice index is `OmniVoice_Voice_Roster.md` (project root — source of truth; the running registry wins over the doc).
  pattern-then-break, stacked callbacks, two-track lines, post-production as a writer's room, brazen
  foreshadowing). Read this before writing a script — it's the craft layer that makes episodes feel
  engineered rather than just a list of bits. It anchors three shows: Arrested Development (interconnection),
  South Park (the but/therefore causality rule), and 30 Rock (joke texture).
- `references/writers-room.md` — the critique loop: after a draft, dispatch a panel of subagent critics
  (Enthusiast, Skeptic, Overthinker + a Showrunner craft critic), synthesize, revise, repeat. Run it to punch
  up an episode — always for big-swing/arc episodes.
- `references/police-squad-pass.md` — the **deadpan non-sequitur** punch-up pass (run after the writers'
  room): the rule, named techniques, and the canonical worked examples.
- `references/thumbnail.md` — the episode **animated open, thumbnail & end bumper**: the locked monochrome
  look, the TONIGHT/MACU-Report intro animation, the title-card flicker, the open VO gag, the next-ep bumper,
  fill-in Hyperframes templates, and how the bookend cues wire in.

## The workflow

### 1. Brainstorm the episode with August (default: brainstorm-first)

Start as a creative partner, not a form. Riff with him on the premise and the run of show before writing
prose. Good things to land together: the episode's theme or "cold open" hook, which **recurring cast** appear
(Ron + Walter always anchor), what **segments / ads / sponsors** to include, and — the fun part — whether to
**invent a new creepy/zany character or sponsor** for this one. MACU leans weird: cults, sentient appliances,
ominous PSAs, too-cheerful spokesmen. Pitch a few, let him pick.

Keep the structure loose but recognizable as a newscast: cold-open anchor intro → segments interleaved with
ads/bumpers → weather → a feel-good closer → signoff. EP5 is the reference for length and rhythm (~27 cues,
~4–5 min). You don't have to match it — shorter single-segment bits are fine too.

### 2. Write the script

Write it in MACU voice — earnest-anchor delivery over absurd post-apocalyptic content, dry and a little
menacing, comedic. Two rules that matter for the pipeline:

- **Each character has its own voice now** (cloned via OmniVoice — Will-Ferrell-ish Ron, Cronkite Walter,
  Attenborough Tally Man, Snoop Mr. Cricket, etc.), so write *to* each character. The exception is the
  machine characters: **SAFE and the Vendor keep the calm HAL register** — that's the joke, and why the SAFE
  ad ("a 'safe' AI that swears it'll never turn on humanity, *for real this time*") lands. You'll cast each
  speaker's voice in step 4; the catalog of available voices is in `references/manifest-schema.md`.
- Keep lines as **clean spoken prose** — the line text becomes both the VO and the burned-in subtitle, so
  avoid stage directions inside the spoken text (put those in parentheses on their own).

**Engineer the comedy — don't just list bits.** The difference between a fine MACU episode and a great one
is *interconnection*: the best comedy has the most wiring, not the most jokes ("by the end, no line feels
isolated"). Before writing, read `references/joke-engineering.md` and put several of its moves to work:
seed throwaway lines early that detonate in the back half; teach a catchphrase/pattern twice so a third
beat can break it; collide 2–3 threads in the signoff; write two-track lines that read one way to Ron and
another to everyone else (this doubles as Ron-arc fuel — see `MACU_Story_Arcs.md`); let music beds and a
flat anchor button ("Anyway,") carry jokes the dialogue doesn't; and plant at least one brazen long-fuse
payoff for a *future* episode. The format — cross-cutting segments, a recurring ensemble, the oblivious-
vs-Ron tension — is built for this; lean on it.

Save the script to `episodes/<slug>/script.md` (readable screenplay form, with a `» shot:` annotation per line
so it doubles as the shot list — see EP5). Revise with August until he's happy. **Do not move on to the
manifest until the script is approved.**

**Need source material? Ask Max.** Max has a YouTube→transcript skill (and general web research reach Leo's
sandbox lacks). When August references a video, talk, or article he wants the writing informed by, hand Max
a Vikunja task to pull it into the synced folder (`agent-io/max/`) and comment back — same handoff procedure
as a render (see `references/pipeline-and-handoff.md`). That's how `references/joke-engineering.md` was
built.

### 2.5 Run the writers' room (critique loop)

Before locking a script — **always for a big-swing/arc/breakout episode**, optional for routine weeks — run
the critique loop in `references/writers-room.md`. It dispatches a panel of subagent critics at the draft:
three audience personas (the Enthusiast, the Skeptic, the Overthinker — adapted from August's
`comedy-writers-room` skill) plus a **Showrunner** craft critic that scores the script against the
Arrested Development / South Park / 30 Rock rubric and MACU canon. Synthesize their reactions, revise, and
loop (cap ~2–3 passes). Protect the weird — cut confusion, never strangeness — and don't homogenize the
voices. Trigger it whenever August says "punch this up" / "get the room on it," and after his Saturday
review of the auto-drafts. Then continue to the cast lock and manifest.

### 2.6 The Police Squad pass (deadpan non-sequiturs)

After the writers' room and before locking the cast, run one more focused pass — the **Police Squad pass**.
An expert agent threads **deadpan non-sequiturs** into the revised script in the Police Squad! / Airplane!
(Zucker-Abrahams-Zucker) tradition: a character states something alarming or quietly devastating in a
completely settled register, nobody reacts, and the scene just moves on. Walter (the announcer) and the
machines (STRIDE, the Vendor, SAFE) are the prime vehicles; Ron is the pressure valve who *almost* notices.

Read `references/police-squad-pass.md` for the rule, the named techniques, and the canonical worked examples.
Run it like the writers' room — dispatch it as a subagent that returns **only proposed insertions** (segment
anchor + line) so August can accept/reject each. Keep it surgical: ~1–2 beats per segment, settled register,
no acknowledgment, never step on an existing punchline or the plot. Apply the accepted beats, then continue
to the cast lock.

### 3. Lock the cast → prompt cores, seeds, and voices

For every speaker and b-roll location in the script, you need a prompt. For **recurring** cast, reuse their
core + seed from the bible verbatim. For any **new** character or sponsor, write a short prompt core (nouns +
2–3 strong adjectives — the model is low-res, so don't overwrite) and assign a fresh seed (any 4–5 digit
number not already used). Same for new environments/b-roll.

**Cast a voice for every speaker.** Each distinct cue `speaker` gets an entry in `voice.speaker_map` (see the
voice catalog in `references/manifest-schema.md`). Match voice to character — an Attenborough for an ominous
narrator, a cheerful infomercial pitch for a huckster — and **reserve HAL for AI/appliance characters**
(SAFE, the Vendor). The bible records each recurring character's voice; carry it forward. If no catalogued
voice fits a new character, note that a new clone is needed — that's a quick Max-side step in the handoff.

**Persist new characters to the living bible** so they're canon next time: the bundled `references/character-bible.md`
is a starting snapshot, but the project's working copy at `E:\August\MACU\MACU\MACU_Character_Prompt_Bible.md`
(synced to Max) is the source of truth — add new cast there. (In a sandbox/dry-run with no access to that path,
just note the addition in your output instead of writing it.) The character also goes in the manifest's
`characters{}` regardless, so a render never depends on the bible file.

### 3.5 Episode bookends — the animated open & the next-episode bumper (EVERY episode)

Every episode opens on a short **animated intro** (with Walter's gag VO) and closes on a **bumper** that shows
the NEXT episode's title card. Author all of this; `validate_manifest.py` warns if it's missing, and the
render pipeline handles the mechanics. Full spec + templates: `references/thumbnail.md`. Three Hyperframes
assets are rendered per episode and **Max moves them into `episodes/<slug>/titles/`** as part of the render
handoff (call them out in the Vikunja task):

- `intro.mp4` (**1024×1024**) — the shared animated open ("TONIGHT" zoom → "on the" → THE MACU REPORT
  wordmark) that resolves into THIS episode's title card (with the signature flicker), then holds.
- `thumb_wide.mp4` (**1920×1080**) — this episode's title card; the render auto-extracts the YouTube still to
  `final/<slug>_thumb.png`.
- `next.mp4` (**1024×1024**) — the NEXT episode's title card, shown under the closing bumper. On Friday, a
  generic "MACU Report — next week" card instead.

**The open (first cue, `c00`).** Walter announces over `intro.mp4`, theme underneath — a Police-Squad double
gag:
- `speaker:"WALTER"`, `vo:` **"The MACU Report! In black and white! Tonight's episode: <a DIFFERENT title
  than the one on the card>."** Two gags: (1) bragging *"In black and white!"* (Police Squad bragged *"IN
  COLOR!"*); (2) Walter reads the **wrong title** — use one of the *other* `youtube.txt` title options or a
  three-segment summary (ep5: card = "The Population Is Adequate", Walter = "A safe AI, a hungry vending
  machine, and the Bloom Hour").
- shot `{"kind":"title","asset":"intro"}` (plays once, then clone-holds the title — do NOT add `fill:"loop"`),
  `pad_seconds: 2.0`, `no_subs: true` (the card carries the real title; the audio carries the gag). Keep the
  intro animation (~5–6s) shorter than Walter's VO so it plays in full.
- add `c00` to the **intro** music bed's `cues` so the theme plays under the whole open.

**The close (last cue) — the bumper.** Walter teases next over `next.mp4` (the next episode's card):
- **Mon–Thu:** *"Tune in for tomorrow's episode: <next episode's subtitle>."* (pull the next title from the
  week plan / `MACU_Weekly_Routine.md`; if it isn't decided yet, ask August.)
- **Friday / week finale:** *"Tune in next week for a new installment of the Mayor Awesome Cinematic
  Universe!"* (use the generic "next week" `next.mp4` card; see `MACU_Story_Arcs.md`.)
- shot `{"kind":"title","asset":"next"}`, `pad_seconds: 1.5`, `no_subs: true`; place it last (after the
  "Anyway,"/signoff) and add it to the **outro** bed's `cues`.

### 4. Build the manifest

Create `episodes/<slug>/manifest.json` following `references/manifest-schema.md` exactly. The non-negotiables:

- Copy the **locked `comfyui` block** (zeroscope_v2_576w @ 384×384×24f, steps 30, cfg 15, fps 8) — this is
  what makes watermark-free + square + B&W + VRAM-fit all true at once. Don't bump resolution.
- Carry the `style` (suffix + negative), `music` (intro/outro big-band theme beds), and `subtitles` (Better
  VCR font) blocks forward.
- One cue per spoken line: `{id, segment, speaker, vo, shots[]}`. Shots reference `characters[*]`,
  `broll[*]`, or `title_assets` by key. Reuse one master per character across their cues (the assembler does
  this automatically — same key = one generation).
- **Bookend the episode** (step 3.5): a front `c00` open cue (Walter's gag VO over the animated `intro` card —
  `pad_seconds:2.0`, `no_subs:true`) and a closing bumper cue (Walter teases next over the `next` card). Put
  `intro` and `next` in `title_assets`; add `c00` to the intro bed and the bumper to the outro bed.

Then **validate** it:

```
python scripts/validate_manifest.py episodes/<slug>/manifest.json
```

Fix anything it flags (broken refs, seed mismatches, duplicate ids, missing locked settings) before handoff —
bad manifests are slow to debug after they've been sent.

### 5. Confirm, then hand off to Max (build-then-confirm)

Before sending anything, show August a short summary: episode slug, runtime estimate, cue/shot counts, **which
characters are new** (and their seeds), and the rough render cost (~30–40s GPU per unique master + a few min
assembly). Get his explicit OK.

**The handoff has real side effects** — it creates a Vikunja task, pings Max's live session, and can kick off
a ~25-minute GPU render. So never fire it on assumption: only create/assign the task after August has
explicitly approved the build. If you're unsure, dry-running, or being tested, stop at the summary and ask —
producing the script and a validated manifest is the win; sending is a separate, deliberate step.

On his go, hand the render to Max via Vikunja — full procedure in `references/pipeline-and-handoff.md`. In
short: confirm the episode folder has synced to Max, create a task on project 3 describing the episode +
manifest path, **assign it to Max (user id 5) via the n8n assignee-proxy workflow** (the MCP `assign` is a
silent no-op — the proxy is the only thing that works *and* pings him), and verify the assignee took.

Then tell August it's running and that he should **ping you to check the board** when Max responds — you have
no notification hook for replies. When he does, pull Max's comment and relay the result (and the output
paths: `episodes/<slug>/final/<slug>.mp4` plus the YouTube thumbnail
`episodes/<slug>/final/<slug>_thumb.png`, both of which sync back to Leo).

### 6. Write the YouTube copy

Every episode also gets publish-ready copy saved to `episodes/<slug>/youtube.txt` so August can post it
straight to YouTube. You can do this as soon as the script is locked (it doesn't depend on the render).
Write it in MACU voice — in-universe, dry, a little menacing — but discoverable. Include:

- **2–3 title options** (one straight "Episode N: <subtitle>", one hooky/segment-led, one punchy quote or
  clickbait-ish line). Lead with the episode's best gag.
- **A description**: an in-universe hook paragraph, then a `Segments: A • B • C` line, then the standard
  boilerplate sign-off line — _"The MACU Report is a black-and-white, post-apocalyptic, retro-futurist
  faux-newscast from the Mayor Awesome Cinematic Universe."_ — capped with that episode's signoff tag.
- **Tags / hashtags**: carry the core set forward (`#MACUReport #MayorAwesome #postapocalyptic
  #retrofuturism #analoghorror #aigenerated #fauxnewscast #darkcomedy`) and add 1–3 episode-specific ones
  (e.g. `#60Minutes`, `#gameshow`, `#wernerherzog`, `#vincentprice`).

Use the existing `episodes/ep5|ep6|ep7/youtube.txt` files as the format template. Offer August a quick tone
tweak (punchier vs. deadpan) but the file is the deliverable — don't just print it in chat.

### 7. Iterate

Re-renders are cheap and incremental: VO/masters/titles are cached, so tweaks (a new line, a different sub
style, the music gain) only redo what changed. If August wants changes after seeing a cut, update the
script/manifest and send Max a focused follow-up rather than regenerating everything.

## Notes

- **You can't reach Max's LAN or pull renders directly from this session** — the sandbox allowlist blocks
  `10.0.0.245` and external webhooks. Move everything through the synced Syncthing folder and the bridged
  MCPs (Vikunja, the n8n render/assignee proxies); see `references/pipeline-and-handoff.md`.
