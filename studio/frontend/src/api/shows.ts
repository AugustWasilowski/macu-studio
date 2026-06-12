import type { ShowSummary, ShowConfig, ImportResult, ArchiveList } from "../types";

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export const showsApi = {
  list: () =>
    fetch("/api/shows").then((r) => J<{ shows: ShowSummary[]; default: string }>(r)),
  create: (id: string, name: string) =>
    fetch("/api/shows", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, name }),
    }).then((r) => J<{ ok: boolean; show: string; name: string }>(r)),
  config: (show: string) =>
    fetch(`/api/shows/${show}/config`).then((r) => J<ShowConfig>(r)),
  putConfig: (show: string, cfg: Partial<ShowConfig>) =>
    fetch(`/api/shows/${show}/config`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    }).then((r) => J<ShowConfig>(r)),
  createEpisode: (show: string, slug: string, title: string) =>
    fetch(`/api/shows/${show}/episodes`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, title }),
    }).then((r) => J<{ ok: boolean; show: string; slug: string; title: string }>(r)),
  importZip: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch("/api/import", { method: "POST", body: fd }).then((r) => J<ImportResult>(r));
  },
  // Ask the backend to open the show's folder in its OS file manager. opened=false
  // (headless / remote server) is a normal outcome — the UI falls back to showing
  // the returned path(s) for manual copy.
  openFolder: (show: string) =>
    fetch(`/api/shows/${show}/open-folder`, { method: "POST" }).then((r) =>
      J<{ ok: boolean; opened: boolean; path: string; windows_path: string | null; reason: string | null }>(r)),

  // ---- Archive: physically move episodes/shows out of (and back into) the active tree.
  listArchive: () => fetch("/api/archive").then((r) => J<ArchiveList>(r)),
  archiveEpisode: (show: string, slug: string) =>
    fetch(`/api/shows/${show}/episodes/${slug}/archive`, { method: "POST" }).then((r) =>
      J<{ ok: boolean; show: string; slug: string; path: string }>(r)),
  // `name` is the archived container's id (from listArchive); newSlug restores under a
  // different slug when the original is taken (the 409 path).
  unarchiveEpisode: (show: string, name: string, newSlug?: string) =>
    fetch(`/api/shows/${show}/episodes/${name}/unarchive`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newSlug ? { new_slug: newSlug } : {}),
    }).then((r) => J<{ ok: boolean; show: string; slug: string }>(r)),
  archiveShow: (show: string) =>
    fetch(`/api/shows/${show}/archive`, { method: "POST" }).then((r) =>
      J<{ ok: boolean; show: string; path: string; episode_count: number }>(r)),
  unarchiveShow: (name: string) =>
    fetch(`/api/shows/${name}/unarchive`, { method: "POST" }).then((r) =>
      J<{ ok: boolean; show: string; path: string }>(r)),
};

// Browser-download URLs (Content-Disposition: attachment served by the backend).
export const exportUrl = {
  // assets = bundle the binary source assets (OmniVoice refs, SFX, music) the show
  // uses, so a recipient can render without re-sourcing them. Off = text + templates.
  episode: (slug: string, assets = true) => `/api/episodes/${slug}/export${assets ? "" : "?assets=0"}`,
  show: (show: string, assets = true) => `/api/shows/${show}/export${assets ? "" : "?assets=0"}`,
  voicesAll: () => `/api/voices/export`,
  voice: (name: string) => `/api/voices/export?name=${encodeURIComponent(name)}`,
};

// Re-clone one imported voice reference into the local OmniVoice (GPU) and rebind a
// show's speaker_map for it. Called once per voice so the UI can show progress.
export function cloneVoiceRef(name: string, show?: string) {
  return fetch("/api/voices/clone-ref", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, show }),
  }).then((r) => J<{ ok: boolean; id: string; name: string; rebound: number }>(r));
}
