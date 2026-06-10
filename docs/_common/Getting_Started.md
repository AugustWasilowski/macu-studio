# Getting Started

Welcome to MACU Studio. This is the short version of how a video gets made here: you write a script, the Studio turns it into voices, video, and graphics, and then it stitches everything into a finished episode you can publish. This guide walks the whole loop once. It mirrors the **Guided walkthrough** (open the project menu → *Guided walkthrough…*), which does the same thing live, inside the app, with a practice episode it creates for you.

If you'd rather learn by doing, stop reading and run the walkthrough. If you'd rather read first, keep going.

## The big picture

Everything in Studio flows left to right across the tabs at the top: **Script → Audio → Graphics → Video → Assembly → Publish**. Each tab is a stage in the pipeline, numbered in order. A stage shows a ✓ when it has output. You don't have to finish a stage before peeking at the next — but the natural order is left to right.

![The main menu](/guide/08-menu.png)

The project menu (top left, "MACU STUDIO") is home base: create or switch shows and episodes, import and export projects, connect to MACU Web, run the tutorial or this guided walkthrough, and reach the live site at mayorawesome.com.

## 1 · Write the script

The Script page is where every episode begins. The format is plain and forgiving:

- A line that begins with `**NAME:**` is a spoken **cue** — "NAME" is the speaker, the rest is what they say.
- A line that begins with `##` starts a new **segment** (a labelled section of the show).
- A line that begins with `»` is a **shot direction** — it tells the Video stage what to put on screen (`» NARRATOR core` reuses a character; `» b-roll: an old broadcast tower` describes a clip).

![The Script page](/guide/01-script.png)

Write a few cues, then press **Generate Manifest** (top right). Studio reads your script and proposes a *manifest* — the structured plan for the episode (every cue, every speaker, every shot). Review the summary and press **Apply**. That's the hand-off from "words" to "a thing the pipeline can build."

> Tip: the manifest is regenerated from the script every time. Edit the script, regenerate, apply — your hand-tuned voices and shots are preserved where they still match.

## 2 · Cast the voices

A script names speakers; the Audio page gives each one a voice. New speakers show up **unmapped** — pick a voice for each using the voice picker beside their name. You can use a built-in voice or clone your own.

![The Audio page](/guide/02-audio.png)

This step is optional in the sense that unmapped speakers fall back to a default voice — but casting is half the character, so it's worth doing.

## 3 · Render the voiceover

Still on the Audio page: turn the written lines into actual audio. Use **Regen missing** to render every cue at once, or the regen button on a single cue, then press play to hear it. A small counter tracks how many cues are done. This runs on your machine's voice service — it's the one step you'll do over and over as you tune performances.

## 4 · Sound effects & music (optional)

Also on the Audio page: generate sound-effect suggestions to drop between cues, or switch on a music bed. Skippable — add texture when the episode is otherwise working.

## 5 · Title cards (optional)

![The Graphics page](/guide/03-graphics.png)

The Graphics page builds title cards, lower-thirds, and the YouTube thumbnail from HyperFrames compositions. Render one to see how it looks. Optional, but a single title card makes an episode feel finished.

## 6 · Video shots (optional)

![The Video page](/guide/04-video.png)

The Video page turns your `»` shot directions into short clips with ComfyUI. Use **Generate shots** to propose a shot list from the script, then render one. This stage needs the GPU services running — if they're not up, skip it and come back. (The guided walkthrough detects this for you and offers to skip.)

## 7 · Assemble the episode

![The Assembly page](/guide/05-assembly.png)

Assembly is the payoff. Press **Run** and the full pipeline executes in order — voices, video, music, subtitles — and stitches the final MP4. The live log shows each stage as it goes. This is the GPU-heavy step; expect it to take a while. Every stage is cached, so a second run only redoes what changed.

## 8 · Publish

![The Publish page](/guide/06-publish.png)

When the episode is ready, the Publish page links a YouTube video and pushes the episode to your MACU Web site (the public page at your-name on mayorawesome.com). Nothing here happens by accident — you choose what goes public and when.

## Where to go next

- **Run the Guided walkthrough** (project menu → *Guided walkthrough…*) to do all of the above on a practice episode, with the app pointing the way.
- **Script Style Guide** — the full grammar the manifest parser understands.
- **OmniVoice Voice Tips** — getting better performances out of cloned voices.
- **MACU Pipeline Design** — what each stage actually does under the hood.

You can replay the walkthrough or reopen this guide any time from the project menu.
