import { create } from "zustand";

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

interface State {
  drawerOpen: boolean;
  logOpen: boolean;
  terminalOpen: boolean;
  updateOpen: boolean;
  toasts: Toast[];
  log: LogEntry[];
  activeSlug: string | null;
  activeShow: string;
  selectedCueId: string | null;
  selectedShotKey: string | null;
  selectedTitleKey: string | null;
  playingKey: string | null;
  busy: Record<string, boolean>;
  runs: Record<string, AssemblyRun>;
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
  setActiveSlug: (slug: string | null) => void;
  setActiveShow: (show: string) => void;
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
}

let toastSeq = 1;

export const useStore = create<State & Actions>((set) => ({
  drawerOpen: false,
  logOpen: false,
  terminalOpen: false,
  updateOpen: false,
  toasts: [],
  log: [],
  activeSlug: null,
  activeShow: localStorage.getItem("macu.show") || "the-macu-report",
  selectedCueId: null,
  selectedShotKey: null,
  selectedTitleKey: null,
  playingKey: null,
  busy: {},
  runs: {},

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
  setActiveSlug: (slug) => set({ activeSlug: slug }),
  setActiveShow: (show) => { localStorage.setItem("macu.show", show); set({ activeShow: show }); },
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
}));
