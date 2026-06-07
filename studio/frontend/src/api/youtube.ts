async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export interface YoutubeUpload {
  video_id: string;
  title: string;
  thumbnail: string;
  view_count: number;
  published_at: string;
  url: string;
}

export interface YoutubeMatches {
  matches: Record<string, YoutubeUpload | null>;
  episodes: { slug: string; title: string }[];
}

export interface YtAuth { has_client: boolean; connected: boolean; }
export interface YtDeviceStart { handle: string; user_code: string; verification_url: string; interval: number; }
export interface YtPoll { connected?: boolean; pending?: boolean; error?: string; }
export interface YtCaptionTrack { id: string; language: string; name: string; track_kind: string; }
export interface YtCaptions {
  connected: boolean;
  has_client: boolean;
  video_id: string | null;
  matched_title: string | null;
  available: { lang: string }[];
  existing: YtCaptionTrack[];
  error: string | null;
}
export interface YtUploadResult { ok: boolean; results: { lang: string; action: "inserted" | "updated" | "error"; error?: string }[]; }

const post = <T>(url: string, body?: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined }).then((r) => J<T>(r));

export const youtubeApi = {
  uploads: () =>
    fetch("/api/youtube/uploads").then((r) => J<{ uploads: YoutubeUpload[] }>(r)),
  matches: () =>
    fetch("/api/youtube/matches").then((r) => J<YoutubeMatches>(r)),

  auth: () => fetch("/api/youtube/auth").then((r) => J<YtAuth>(r)),
  setClient: (client_id: string, client_secret: string) => post<YtAuth>("/api/youtube/auth/client", { client_id, client_secret }),
  authStart: () => post<YtDeviceStart>("/api/youtube/auth/start"),
  authPoll: (handle: string) => post<YtPoll>("/api/youtube/auth/poll", { handle }),
  disconnect: () => post<YtAuth>("/api/youtube/auth/disconnect"),

  captions: (slug: string) => fetch(`/api/episodes/${slug}/youtube/captions`).then((r) => J<YtCaptions>(r)),
  uploadCaptions: (slug: string, languages?: string[]) =>
    post<YtUploadResult>(`/api/episodes/${slug}/youtube/captions`, languages ? { languages } : {}),
};
