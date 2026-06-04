import { create } from "zustand";

export type ToastKind = "info" | "ok" | "run" | "err";
export interface Toast {
  id: number;
  text: string;
  kind: ToastKind;
}

interface State {
  drawerOpen: boolean;
  toasts: Toast[];
  activeSlug: string | null;
  selectedCueId: string | null;
  selectedShotKey: string | null;
  selectedTitleKey: string | null;
  playingKey: string | null;
  busy: Record<string, boolean>;
}

interface Actions {
  openDrawer: () => void;
  closeDrawer: () => void;
  toggleDrawer: () => void;
  setActiveSlug: (slug: string | null) => void;
  pushToast: (text: string, kind?: ToastKind) => void;
  dropToast: (id: number) => void;
  selectCue: (id: string | null) => void;
  selectShot: (key: string | null) => void;
  selectTitle: (key: string | null) => void;
  setPlaying: (key: string | null) => void;
  setBusy: (key: string, on: boolean) => void;
}

let toastSeq = 1;

export const useStore = create<State & Actions>((set) => ({
  drawerOpen: false,
  toasts: [],
  activeSlug: null,
  selectedCueId: null,
  selectedShotKey: null,
  selectedTitleKey: null,
  playingKey: null,
  busy: {},

  openDrawer: () => set({ drawerOpen: true }),
  closeDrawer: () => set({ drawerOpen: false }),
  toggleDrawer: () => set((s) => ({ drawerOpen: !s.drawerOpen })),
  setActiveSlug: (slug) => set({ activeSlug: slug }),
  pushToast: (text, kind = "info") => {
    const id = toastSeq++;
    set((s) => ({ toasts: [...s.toasts, { id, text, kind }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 3200);
  },
  dropToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  selectCue: (id) => set({ selectedCueId: id }),
  selectShot: (key) => set({ selectedShotKey: key }),
  selectTitle: (key) => set({ selectedTitleKey: key }),
  setPlaying: (key) => set({ playingKey: key }),
  setBusy: (key, on) => set((s) => ({ busy: { ...s.busy, [key]: on } })),
}));
