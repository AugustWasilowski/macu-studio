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

export const youtubeApi = {
  uploads: () =>
    fetch("/api/youtube/uploads").then((r) => J<{ uploads: YoutubeUpload[] }>(r)),
  matches: () =>
    fetch("/api/youtube/matches").then((r) => J<YoutubeMatches>(r)),
};
