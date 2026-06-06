import type { ShowSummary, ShowConfig, ImportResult } from "../types";

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
};

// Browser-download URLs (Content-Disposition: attachment served by the backend).
export const exportUrl = {
  episode: (slug: string) => `/api/episodes/${slug}/export`,
  show: (show: string) => `/api/shows/${show}/export`,
};
