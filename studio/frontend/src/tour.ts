import type { UIStage } from "./types";
import type { TopPage } from "./route";

// One coachmark step. `target` is a [data-tour] selector (null = centered card).
// `stage`/`topPage` navigate the screen *behind* the spotlight for context before
// the step shows — the spotlighted control itself always lives in the topbar.
export interface TourStep {
  target: string | null;
  title: string;
  body: string;
  stage?: UIStage;
  topPage?: TopPage;
}

export const TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="file-menu"]',
    title: "Project menu",
    body: "New or open shows and episodes, import/export a project, and settings — all live here. Studio can hold multiple shows now.",
  },
  {
    target: '[data-tour="episode-picker"]',
    title: "Episode picker",
    body: "Pick an episode; the ◀ ▶ arrows step through them. The dot is its git-sync state — green means pushed, red means local changes.",
  },
  {
    target: '[data-tour="tab-script"]',
    title: "Script",
    body: "Write the episode in Markdown, then hit Generate manifest to turn it into cues the pipeline can render.",
    stage: "script",
  },
  {
    target: '[data-tour="tab-audio"]',
    title: "Audio",
    body: "Per-cue voiceover — play it, regenerate a line, and drop sound effects into the gaps between cues.",
    stage: "audio",
  },
  {
    target: '[data-tour="tab-graphics"]',
    title: "Graphics",
    body: "Title cards and on-screen overlays. Generate card text and render the compositions that get composited over the video.",
    stage: "graphics",
  },
  {
    target: '[data-tour="tab-video"]',
    title: "Video",
    body: "The shot list — every character and b-roll clip. Render the missing or stale ones; the preview shows each result.",
    stage: "video",
  },
  {
    target: '[data-tour="tab-assembly"]',
    title: "Assembly",
    body: "The render dashboard. Runs the full pipeline end-to-end to a finished video, with live per-stage progress. It's the deep end — explore it once the rest clicks.",
    stage: "assembly",
  },
  {
    target: '[data-tour="tab-youtube"]',
    title: "YouTube",
    body: "Match episodes to their uploads and manage the video title/description metadata.",
    topPage: "youtube",
  },
  {
    target: '[data-tour="tab-docs"]',
    title: "Docs",
    body: "The canon — character bible, prompt docs, and pipeline notes. Reference, not editing.",
    topPage: "docs",
  },
  {
    target: '[data-tour="git-sync"]',
    title: "Git sync",
    body: "Commits this episode's text — script, manifest, youtube.txt — into the repo and pushes it. Generated media stays local; this is the portable source of truth.",
  },
  {
    target: null,
    title: "That's the tour",
    body: "Reopen it anytime from the project menu → Tutorial. Have fun.",
  },
];
