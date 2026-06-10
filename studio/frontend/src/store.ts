import { create } from "zustand";
import { applyLocale } from "./i18n";

export type ToastKind = "info" | "ok" | "run" | "err";
export interface Toast {
  id: number;
  text: string;
  kind: ToastKind;
}
export interface LogEntry {
  id: number;
  ts: number; // epoch ms
  text: string;
  kind: ToastKind;
}

const LOG_CAP = 300;

// Per-episode Assembly run state — lives in the store (not the component) so the
// log tail + stage state survive navigating away from the Assembly tab. `seen` is
// the count of render-server events consumed, used to reconnect the SSE from where
// we left off (?since=seen) instead of replaying or losing events.
export type StageStatus = "running" | "done" | "failed" | null;
export interface AssemblyRun {
  jobId: string | null;
  running: boolean;
  seen: number;
  logLines: string[];
  live: Record<string, StageStatus>;
}
export const DEFAULT_RUN: AssemblyRun = { jobId: null, running: false, seen: 0, logLines: [], live: {} };

// ---- Guided walkthrough ("wizard") — opt-in, follow-along, survives reloads. -------------
// Distinct from the first-run spotlight Tour: the wizard is a non-blocking docked panel and
// its progress is tied to a real practice episode it seeds in the active show.
export type WizardStatus = "active" | "paused" | "done" | "dismissed";
export interface WizardState {
  slug: string;          // the practice episode the walkthrough drives
  step: number;          // index into WIZARD_STEPS
  skipped: string[];     // ids of steps the user skipped (shown in the recap)
  status: WizardStatus;
  collapsed: boolean;    // shrunk to the corner chip while the user works
}
const WIZARD_KEY = "macu.wizard.v1";
function loadWizard(): WizardState | null {
  try {
    const raw = localStorage.getItem(WIZARD_KEY);
    if (!raw) return null;
    const w = JSON.parse(raw) as WizardState;
    if (typeof w?.slug === "string" && typeof w?.step === "number") return w;
  } catch { /* corrupt → ignore */ }
  return null;
}
function saveWizard(w: WizardState | null) {
  try {
    if (w) localStorage.setItem(WIZARD_KEY, JSON.stringify(w));
    else localStorage.removeItem(WIZARD_KEY);
  } catch { /* storage full / disabled — non-fatal */ }
}

interface State {
  drawerOpen: boolean;
  logOpen: boolean;
  terminalOpen: boolean;
  updateOpen: boolean;
  diagnosticsOpen: boolean;
  toasts: Toast[];
  log: LogEntry[];
  activeSlug: string | null;
  activeShow: string;
  locale: string;
  selectedCueId: string | null;
  selectedShotKey: string | null;
  selectedTitleKey: string | null;
  playingKey: string | null;
  busy: Record<string, boolean>;
  runs: Record<string, AssemblyRun>;
  wizard: WizardState | null;
}

interface Actions {
  openDrawer: () => void;
  closeDrawer: () => void;
  toggleDrawer: () => void;
  openLog: () => void;
  closeLog: () => void;
  toggleLog: () => void;
  clearLog: () => void;
  openTerminal: () => void;
  closeTerminal: () => void;
  toggleTerminal: () => void;
  openUpdate: () => void;
  closeUpdate: () => void;
  openDiagnostics: () => void;
  closeDiagnostics: () => void;
  setActiveSlug: (slug: string | null) => void;
  setActiveShow: (show: string) => void;
  setLocale: (locale: string) => void;
  pushToast: (text: string, kind?: ToastKind) => void;
  dropToast: (id: number) => void;
  selectCue: (id: string | null) => void;
  selectShot: (key: string | null) => void;
  selectTitle: (key: string | null) => void;
  setPlaying: (key: string | null) => void;
  setBusy: (key: string, on: boolean) => void;
  resetRun: (slug: string) => void;
  patchRun: (slug: string, partial: Partial<AssemblyRun>) => void;
  appendRunLog: (slug: string, line: string, seen: number) => void;
  setRunLive: (slug: string, key: string, status: StageStatus) => void;
  startWizard: (slug: string) => void;
  setWizardStep: (step: number) => void;
  skipWizardStep: (id: string) => void;
  setWizardCollapsed: (collapsed: boolean) => void;
  pauseWizard: () => void;
  finishWizard: () => void;
  dismissWizard: () => void;
}

let toastSeq = 1;

export const useStore = create<State & Actions>((set) => ({
  drawerOpen: false,
  logOpen: false,
  terminalOpen: false,
  updateOpen: false,
  diagnosticsOpen: false,
  toasts: [],
  log: [],
  activeSlug: null,
  activeShow: localStorage.getItem("macu.show") || "the-macu-report",
  locale: localStorage.getItem("macu.locale") || "en",
  selectedCueId: null,
  selectedShotKey: null,
  selectedTitleKey: null,
  playingKey: null,
  busy: {},
  runs: {},
  wizard: loadWizard(),

  // Opening one right-hand drawer closes the others so they don't overlap.
  openDrawer: () => set({ drawerOpen: true, logOpen: false, terminalOpen: false }),
  closeDrawer: () => set({ drawerOpen: false }),
  toggleDrawer: () => set((s) => ({ drawerOpen: !s.drawerOpen, logOpen: false, terminalOpen: false })),
  openLog: () => set({ logOpen: true, drawerOpen: false, terminalOpen: false }),
  closeLog: () => set({ logOpen: false }),
  toggleLog: () => set((s) => ({ logOpen: !s.logOpen, drawerOpen: false, terminalOpen: false })),
  clearLog: () => set({ log: [] }),
  openTerminal: () => set({ terminalOpen: true, drawerOpen: false, logOpen: false }),
  closeTerminal: () => set({ terminalOpen: false }),
  toggleTerminal: () => set((s) => ({ terminalOpen: !s.terminalOpen, drawerOpen: false, logOpen: false })),
  openUpdate: () => set({ updateOpen: true }),
  closeUpdate: () => set({ updateOpen: false }),
  openDiagnostics: () => set({ diagnosticsOpen: true }),
  closeDiagnostics: () => set({ diagnosticsOpen: false }),
  setActiveSlug: (slug) => set({ activeSlug: slug }),
  setActiveShow: (show) => { localStorage.setItem("macu.show", show); set({ activeShow: show }); },
  // Persist immediately, load the catalog + flip <html> lang/dir, THEN update state so
  // the re-render reads a populated catalog (avoids a flash of raw keys).
  setLocale: (locale) => { localStorage.setItem("macu.locale", locale); applyLocale(locale).then(() => set({ locale })); },
  pushToast: (text, kind = "info") => {
    const id = toastSeq++;
    const entry: LogEntry = { id, ts: Date.now(), text, kind };
    set((s) => ({
      toasts: [...s.toasts, { id, text, kind }],
      log: [...s.log, entry].slice(-LOG_CAP),
    }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 3200);
  },
  dropToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  selectCue: (id) => set({ selectedCueId: id }),
  selectShot: (key) => set({ selectedShotKey: key }),
  selectTitle: (key) => set({ selectedTitleKey: key }),
  setPlaying: (key) => set({ playingKey: key }),
  setBusy: (key, on) => set((s) => ({ busy: { ...s.busy, [key]: on } })),
  resetRun: (slug) => set((s) => ({ runs: { ...s.runs, [slug]: { ...DEFAULT_RUN, running: true } } })),
  patchRun: (slug, partial) => set((s) => ({ runs: { ...s.runs, [slug]: { ...(s.runs[slug] ?? DEFAULT_RUN), ...partial } } })),
  appendRunLog: (slug, line, seen) => set((s) => {
    const r = s.runs[slug] ?? DEFAULT_RUN;
    return { runs: { ...s.runs, [slug]: { ...r, seen, logLines: [...r.logLines.slice(-300), line] } } };
  }),
  setRunLive: (slug, key, status) => set((s) => {
    const r = s.runs[slug] ?? DEFAULT_RUN;
    return { runs: { ...s.runs, [slug]: { ...r, live: { ...r.live, [key]: status } } } };
  }),
  // Wizard actions — every mutation mirrors to localStorage so progress survives reloads.
  startWizard: (slug) => set(() => {
    const w: WizardState = { slug, step: 0, skipped: [], status: "active", collapsed: false };
    saveWizard(w);
    return { wizard: w };
  }),
  setWizardStep: (step) => set((s) => {
    if (!s.wizard) return {};
    const w = { ...s.wizard, step: Math.max(0, step), status: "active" as WizardStatus, collapsed: false };
    saveWizard(w);
    return { wizard: w };
  }),
  skipWizardStep: (id) => set((s) => {
    if (!s.wizard) return {};
    const skipped = s.wizard.skipped.includes(id) ? s.wizard.skipped : [...s.wizard.skipped, id];
    const w = { ...s.wizard, skipped };
    saveWizard(w);
    return { wizard: w };
  }),
  setWizardCollapsed: (collapsed) => set((s) => {
    if (!s.wizard) return {};
    const w = { ...s.wizard, collapsed };
    saveWizard(w);
    return { wizard: w };
  }),
  pauseWizard: () => set((s) => {
    if (!s.wizard) return {};
    const w = { ...s.wizard, status: "paused" as WizardStatus };
    saveWizard(w);
    return { wizard: w };
  }),
  finishWizard: () => set((s) => {
    if (!s.wizard) return {};
    const w = { ...s.wizard, status: "done" as WizardStatus };
    saveWizard(w);
    return { wizard: w };
  }),
  dismissWizard: () => set(() => {
    saveWizard(null);
    return { wizard: null };
  }),
}));
