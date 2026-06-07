import type {
  Cue, EpisodeSummary, FinalInfo, JobSubmitResp,
  PipelineStage, Shot, SrtEntry, SrtResp, TitleAsset,
} from "./types";

export interface GenManifestSummary {
  old_cue_count: number;
  new_cue_count: number;
  cues_added: number;
  cues_reshot: number;
  changes: { id: string; type: "added" | "reshot"; speaker: string; vo: string }[];
  speakers: string[];
  unmapped_speakers: string[];
  segments: string[];
  warnings: string[];
  renumbered: boolean;
}
export interface ScriptVersion {
  id: string;                 // commit hash, or "working"
  kind: "working" | "commit";
  label: string;
  short?: string;
  iso: string | null;
}
export interface ScriptDiffLine { tag: "add" | "del" | "ctx" | "hunk"; text: string; }
export interface ScriptDiff {
  base: string;
  target: string;
  added: number;
  removed: number;
  lines: ScriptDiffLine[];
}
export interface GenManifestResp {
  summary: GenManifestSummary;
  cues?: Cue[];
  saved?: { path: string; mtime: number; bytes: number };
}

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export const api = {
  episodes: (show?: string) =>
    fetch(`/api/episodes${show ? `?show=${encodeURIComponent(show)}` : ""}`)
      .then((r) => J<{ episodes: EpisodeSummary[] }>(r)),
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
  scriptVersions: (slug: string) =>
    fetch(`/api/episodes/${slug}/script/versions`).then((r) => J<{ versions: ScriptVersion[] }>(r)),
  scriptDiff: (slug: string, base: string, target: string) =>
    fetch(`/api/episodes/${slug}/script/diff?base=${encodeURIComponent(base)}&target=${encodeURIComponent(target)}`)
      .then((r) => J<ScriptDiff>(r)),
  genManifest: (slug: string, apply: boolean) =>
    fetch(`/api/episodes/${slug}/manifest/from-script`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apply }),
    }).then((r) => J<GenManifestResp>(r)),
  cues: (slug: string) =>
    fetch(`/api/episodes/${slug}/cues`).then((r) => J<{ cues: Cue[] }>(r)),
  setSpeakerVoice: (slug: string, speaker: string, engine: "omnivoice" | "piper", profile_id?: string, voice_name?: string) =>
    fetch(`/api/episodes/${slug}/speaker-voice`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speaker, engine, profile_id, voice_name }),
    }).then((r) => J<{ ok: boolean; speaker: string; mapped: boolean; propagated: boolean }>(r)),
  shutdown: () =>
    fetch("/api/shutdown", { method: "POST" }).then((r) => J<{ ok: boolean }>(r)),
  shots: (slug: string) =>
    fetch(`/api/episodes/${slug}/shots`).then((r) => J<{ shots: Shot[] }>(r)),
  titles: (slug: string) =>
    fetch(`/api/episodes/${slug}/titles`).then((r) => J<{ titles: TitleAsset[] }>(r)),
  pipeline: (slug: string) =>
    fetch(`/api/episodes/${slug}/pipeline`).then((r) => J<{ stages: PipelineStage[] }>(r)),
  activePipelineJob: (slug: string) =>
    fetch(`/api/episodes/${slug}/pipeline/active`).then((r) => J<{ job_id: string | null }>(r)),
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
  generateShots: (slug: string, onlyMissing = true) =>
    fetch(`/api/episodes/${slug}/shots/generate`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ only_missing: onlyMissing }),
    }).then((r) => J<ShotProposal>(r)),
  applyShots: (slug: string, proposal: ShotProposal) =>
    fetch(`/api/episodes/${slug}/shots/apply`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal }),
    }).then((r) => J<{ ok: boolean; applied_cues: number; new_characters: number; new_broll: number }>(r)),
  generateSfx: (slug: string) =>
    fetch(`/api/episodes/${slug}/sfx/generate`, { method: "POST" })
      .then((r) => J<SfxProposal>(r)),
  applySfx: (slug: string, proposal: SfxProposal) =>
    fetch(`/api/episodes/${slug}/sfx/apply`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal }),
    }).then((r) => J<{ ok: boolean; placed: number; reused: number; acquire: { file: string; query: string }[]; total: number }>(r)),
  // Kill the active render, clear the ComfyUI queue, free GPU memory. Returns a per-step report.
  emergencyStop: () =>
    fetch(`/api/emergency-stop`, { method: "POST" })
      .then((r) => J<{ ok: boolean; report: Record<string, string> }>(r)),
};

export interface ShotProposalChar { reuse: boolean; seed?: number | null; core: string }
export interface ShotProposalBroll { reuse: boolean; prompt: string }
export interface ShotProposalCue { cue_id: string; shots: { id: string; kind: string; who: string; seed?: number }[] }
export interface ShotProposal {
  characters: Record<string, ShotProposalChar>;
  broll: Record<string, ShotProposalBroll>;
  cues: ShotProposalCue[];
  summary: { new_characters: string[]; reused_characters: string[]; new_broll: string[]; reused_broll: string[]; cues_planned: number };
}

export interface SfxProposalEntry {
  cue: string;
  at: string;
  file: string;
  gain: number;
  reuse: boolean;
  need: boolean;
  query: string;
  reason: string;
  duration_s?: number | null;
}
export interface SfxProposal {
  sfx: SfxProposalEntry[];
  summary: { opportunities: number; reused: string[]; acquire: { file: string; query: string }[] };
}

export const mediaUrl = {
  cueAudio: (slug: string, cueId: string, v?: number | null) =>
    `/api/episodes/${slug}/cue/${cueId}/audio${v != null ? `?v=${Math.floor(v)}` : ""}`,
  shotPreview: (slug: string, key: string, v?: number | null) =>
    `/api/episodes/${slug}/shot/${key}/preview${v != null ? `?v=${Math.floor(v)}` : ""}`,
  titlePreview: (slug: string, key: string) =>
    `/api/episodes/${slug}/title/${key}/preview`,
  finalVideo: (slug: string) =>
    `/api/episodes/${slug}/final/video`,
  finalThumb: (slug: string) =>
    `/api/episodes/${slug}/final/thumb`,
};

export const jobStreamUrl = (jobId: string, since = 0) => `/api/jobs/${jobId}/stream?since=${since}`;

// ---- Localize (translated subtitles + dubbed video per language) ----
export interface LocalizeLangStatus { code: string; has_srt: boolean; has_mp4: boolean; mtime: number | null; }
export interface LocalizeInfo {
  rendered: boolean;
  engines: { id: string; caveat: string }[];
  languages: LocalizeLangStatus[];
}
export interface LocalizeJob { lang: string; job_id: string; events_url: string; }

export const localizeApi = {
  get: (slug: string) => fetch(`/api/episodes/${slug}/localize`).then((r) => J<LocalizeInfo>(r)),
  run: (slug: string, body: { languages: string[]; engine: string; subs_only: boolean }) =>
    fetch(`/api/episodes/${slug}/localize`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<{ ok: boolean; jobs: LocalizeJob[] }>(r)),
};

export const dubUrl = {
  video: (slug: string, lang: string) => `/api/episodes/${slug}/localize/${lang}/video`,
  srt: (slug: string, lang: string) => `/api/episodes/${slug}/localize/${lang}/srt`,
};
