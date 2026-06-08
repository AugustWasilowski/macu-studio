// Studio ↔ macu-web (mayorawesome.com) publishing.
async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export interface MacuWebStatus { connected: boolean; base?: string | null; web?: string | null; }
export interface PublishResult { ok: boolean; pushed?: boolean; committed?: boolean; files?: number; log?: string; }
export interface EpisodeWebStatus { visibility: "PUBLIC" | "UNLISTED" | "PRIVATE"; public: boolean; url: string | null; }

export const macuWeb = {
  status: () => fetch("/api/macu-web/status").then((r) => J<MacuWebStatus>(r)),
  connect: (token: string) =>
    fetch("/api/macu-web/connect", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }).then((r) => J<{ ok: boolean; base: string }>(r)),
  publish: (show: string) =>
    fetch(`/api/shows/${show}/publish`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }).then((r) => J<PublishResult>(r)),
  setPublished: (slug: string, published: boolean) =>
    fetch(`/api/episodes/${slug}/macu-web/published`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ published }),
    }).then((r) => J<{ ok: boolean; published: boolean }>(r)),
  setVideoId: (slug: string, video_id: string) =>
    fetch(`/api/episodes/${slug}/macu-web/youtube`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id }),
    }).then((r) => J<{ ok: boolean; video_id: string | null }>(r)),
  setMeta: (slug: string, fields: { title?: string; notes?: string; season?: number | string | null; episode_num?: number | string | null }) =>
    fetch(`/api/episodes/${slug}/macu-web/meta`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    }).then((r) => J<{ ok: boolean }>(r)),
  episodeStatus: (slug: string) =>
    fetch(`/api/episodes/${slug}/macu-web/episode`).then((r) => J<EpisodeWebStatus>(r)),
  setVisibility: (slug: string, visibility: "PUBLIC" | "UNLISTED" | "PRIVATE") =>
    fetch(`/api/episodes/${slug}/macu-web/visibility`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visibility }),
    }).then((r) => J<EpisodeWebStatus & { ok: boolean }>(r)),
};
