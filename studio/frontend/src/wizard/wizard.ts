import type { UIStage } from "../types";

// One step of the guided walkthrough. Unlike the spotlight Tour, a step doesn't just point
// at a control — it sets the user a concrete goal on a real page and watches for that goal to
// actually happen (see useWizardGates). The panel only enables "Next" once `gate` is true.
export type WizardGate =
  | "episodeExists"
  | "manifestHasCues"
  | "speakersCast"
  | "voAllRendered"
  | "sfxPlaced"
  | "titleRendered"
  | "shotRendered"
  | "finalExists";

// A step can be gated on an optional GPU/render service being up; when it's down the panel
// shows an amber notice and promotes Skip.
export type WizardService = "comfyui" | "voice" | "gpu";

export interface WizardStep {
  id: string;
  stage?: UIStage;          // page to navigate to when the step opens (none = leave in place)
  titleKey: string;
  bodyKey: string;
  goalKey?: string;         // one-line description of what completes the step
  gate?: WizardGate;        // the real-state signal that satisfies the goal
  optional?: boolean;       // Skip is always offered; optional steps make it the soft default
  requiresService?: WizardService; // degrade gracefully when this service is unreachable
  action?: "createEpisode"; // a step that performs a one-shot action via its primary button
}

export const WIZARD_STEPS: WizardStep[] = [
  {
    id: "welcome",
    titleKey: "wizard.welcome.title",
    bodyKey: "wizard.welcome.body",
    goalKey: "wizard.welcome.goal",
    gate: "episodeExists",
    action: "createEpisode",
  },
  {
    // Cosmetic, ungated: point at the theme picker before the real work starts.
    id: "theme",
    titleKey: "wizard.theme.title",
    bodyKey: "wizard.theme.body",
    goalKey: "wizard.theme.goal",
    optional: true,
  },
  {
    id: "script",
    stage: "script",
    titleKey: "wizard.script.title",
    bodyKey: "wizard.script.body",
    goalKey: "wizard.script.goal",
    gate: "manifestHasCues",
  },
  {
    id: "cast",
    stage: "audio",
    titleKey: "wizard.cast.title",
    bodyKey: "wizard.cast.body",
    goalKey: "wizard.cast.goal",
    gate: "speakersCast",
    optional: true,
  },
  {
    id: "renderVo",
    stage: "audio",
    titleKey: "wizard.renderVo.title",
    bodyKey: "wizard.renderVo.body",
    goalKey: "wizard.renderVo.goal",
    gate: "voAllRendered",
    requiresService: "voice",
  },
  {
    id: "sfx",
    stage: "audio",
    titleKey: "wizard.sfx.title",
    bodyKey: "wizard.sfx.body",
    goalKey: "wizard.sfx.goal",
    gate: "sfxPlaced",
    optional: true,
  },
  {
    id: "graphics",
    stage: "graphics",
    titleKey: "wizard.graphics.title",
    bodyKey: "wizard.graphics.body",
    goalKey: "wizard.graphics.goal",
    gate: "titleRendered",
    optional: true,
  },
  {
    // Ungated info step (Characters is a top page, not a stage — the body sends
    // the user to the top-bar tab). Optional: a nicety for recurring casts.
    id: "characters",
    titleKey: "wizard.characters.title",
    bodyKey: "wizard.characters.body",
    goalKey: "wizard.characters.goal",
    optional: true,
  },
  {
    id: "shots",
    stage: "video",
    titleKey: "wizard.shots.title",
    bodyKey: "wizard.shots.body",
    goalKey: "wizard.shots.goal",
    gate: "shotRendered",
    optional: true,
    requiresService: "comfyui",
  },
  {
    id: "assemble",
    stage: "assembly",
    titleKey: "wizard.assemble.title",
    bodyKey: "wizard.assemble.body",
    goalKey: "wizard.assemble.goal",
    gate: "finalExists",
    optional: true,
    requiresService: "gpu",
  },
  {
    id: "publish",
    stage: "publish",
    titleKey: "wizard.publish.title",
    bodyKey: "wizard.publish.body",
  },
  {
    id: "done",
    titleKey: "wizard.done.title",
    bodyKey: "wizard.done.body",
  },
];
