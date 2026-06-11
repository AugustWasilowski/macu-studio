import type { UIStage } from "./types";
import type { TopPage } from "./route";

// One coachmark step. `target` is a [data-tour] selector (null = centered card).
// `stage`/`topPage` navigate the screen *behind* the spotlight for context before
// the step shows — the spotlighted control itself always lives in the topbar.
export interface TourStep {
  target: string | null;
  titleKey: string;
  bodyKey: string;
  stage?: UIStage;
  topPage?: TopPage;
}

export const TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="file-menu"]',
    titleKey: "tour.projectMenu.title",
    bodyKey: "tour.projectMenu.body",
  },
  {
    target: '[data-tour="episode-picker"]',
    titleKey: "tour.episodePicker.title",
    bodyKey: "tour.episodePicker.body",
  },
  {
    target: '[data-tour="tab-script"]',
    titleKey: "tour.script.title",
    bodyKey: "tour.script.body",
    stage: "script",
  },
  {
    target: '[data-tour="tab-audio"]',
    titleKey: "tour.audio.title",
    bodyKey: "tour.audio.body",
    stage: "audio",
  },
  {
    target: '[data-tour="tab-graphics"]',
    titleKey: "tour.graphics.title",
    bodyKey: "tour.graphics.body",
    stage: "graphics",
  },
  {
    target: '[data-tour="tab-video"]',
    titleKey: "tour.video.title",
    bodyKey: "tour.video.body",
    stage: "video",
  },
  {
    target: '[data-tour="tab-assembly"]',
    titleKey: "tour.assembly.title",
    bodyKey: "tour.assembly.body",
    stage: "assembly",
  },
  {
    target: '[data-tour="tab-publish"]',
    titleKey: "tour.publish.title",
    bodyKey: "tour.publish.body",
    stage: "publish",
  },
  {
    target: '[data-tour="tab-docs"]',
    titleKey: "tour.docs.title",
    bodyKey: "tour.docs.body",
    topPage: "docs",
  },
  {
    target: '[data-tour="git-sync"]',
    titleKey: "tour.gitSync.title",
    bodyKey: "tour.gitSync.body",
  },
  {
    // Theme picker lives in the project menu → Settings (default tab).
    target: '[data-tour="file-menu"]',
    titleKey: "tour.theme.title",
    bodyKey: "tour.theme.body",
  },
  {
    // Centered card — the MCP server has no UI control to spotlight.
    target: null,
    titleKey: "tour.mcp.title",
    bodyKey: "tour.mcp.body",
  },
  {
    target: '[data-tour="file-menu"]',
    titleKey: "tour.ready.title",
    bodyKey: "tour.ready.body",
  },
];
