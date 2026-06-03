import type {
  Cue, EpisodeSummary, FinalInfo, JobSubmitResp,
  PipelineStage, Shot, SrtEntry, SrtResp, TitleAsset,
} from "./types";

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export const api = {
  episodes: () => fetch("/api/episodes").then((r) => J<{ episodes: EpisodeSummary[] }>(r)),
  manifest: (slug: string) =>
    fetch(`/api/episodes/${slug}/manifest`).then((r) => J<Record<string, unknown>>(r)),
  putManifest: (slug: string, body: unknown) =>
    fetch(`/api/episodes/${slug}/manifest`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<{ path: string; mtime: number; bytes: number }>(r)),
  script: (slug: string) =>
    fetch(`/api/episodes/${slug}/script`).then((r) =>
      J<{ text: string; mtime: number | null; exists: boolean }>(r)
    ),
  putScript: (slug: string, text: string) =>
    fetch(`/api/episodes/${slug}/script`, {
      method: "PUT", headers: { "Content-Type": "text/markdown" }, body: text,
    }).then((r) => J<{ mtime: number; bytes: number }>(r)),
  cues: (slug: string) =>
    fetch(`/api/episodes/${slug}/cues`).then((r) => J<{ cues: Cue[] }>(r)),
  shots: (slug: string) =>
    fetch(`/api/episodes/${slug}/shots`).then((r) => J<{ shots: Shot[] }>(r)),
  titles: (slug: string) =>
    fetch(`/api/episodes/${slug}/titles`).then((r) => J<{ titles: TitleAsset[] }>(r)),
  pipeline: (slug: string) =>
    fetch(`/api/episodes/${slug}/pipeline`).then((r) => J<{ stages: PipelineStage[] }>(r)),
  final: (slug: string) =>
    fetch(`/api/episodes/${slug}/final`).then((r) => J<FinalInfo>(r)),
  srt: (slug: string) =>
    fetch(`/api/episodes/${slug}/srt`).then((r) => J<SrtResp>(r)),
  putSrt: (slug: string, entries: SrtEntry[]) =>
    fetch(`/api/episodes/${slug}/srt`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entries }),
    }).then((r) => J<{ mtime: number; count: number }>(r)),
  run: (slug: string, body: { from_stage?: number; only?: number; notes?: string }) =>
    fetch(`/api/episodes/${slug}/pipeline/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<JobSubmitResp>(r)),
  regenCue: (slug: string, cueId: string) =>
    fetch(`/api/episodes/${slug}/cue/${cueId}/regen`, { method: "POST" })
      .then((r) => J<JobSubmitResp>(r)),
  regenShot: (slug: string, key: string) =>
    fetch(`/api/episodes/${slug}/shot/${key}/regen`, { method: "POST" })
      .then((r) => J<JobSubmitResp>(r)),
};

export const mediaUrl = {
  cueAudio: (slug: string, cueId: string) =>
    `/api/episodes/${slug}/cue/${cueId}/audio`,
  shotPreview: (slug: string, key: string) =>
    `/api/episodes/${slug}/shot/${key}/preview`,
  titlePreview: (slug: string, key: string) =>
    `/api/episodes/${slug}/title/${key}/preview`,
  finalVideo: (slug: string) =>
    `/api/episodes/${slug}/final/video`,
  finalThumb: (slug: string) =>
    `/api/episodes/${slug}/final/thumb`,
};

export const jobStreamUrl = (jobId: string) => `/api/jobs/${jobId}/stream`;
