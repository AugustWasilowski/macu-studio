export type StageKey =
  | "vo"
  | "masters"
  | "rife"
  | "assemble"
  | "music"
  | "whisper"
  | "srt"
  | "burn";

export type UIStage = "script" | "audio" | "graphics" | "video" | "assembly";
export const UI_STAGES: { key: UIStage; label: string; n: number }[] = [
  { key: "script", label: "Script", n: 1 },
  { key: "audio", label: "Audio", n: 2 },
  { key: "graphics", label: "Graphics", n: 3 },
  { key: "video", label: "Video", n: 4 },
  { key: "assembly", label: "Assembly", n: 5 },
];

export type AssetStatus =
  | "missing"
  | "stale"
  | "generated"
  | "rendered"
  | "exists"
  | "shared"
  | "draft"
  | "done"
  | "ok"
  | "running"
  | "idle"
  | "failed";

export interface EpisodeSummary {
  slug: string;
  title: string;
  modified_iso: string;
  done_stages: number;
}

export interface Cue {
  id: string;
  speaker: string;
  text: string;
  is_hold: boolean;
  hold_seconds?: number | null;
  status: AssetStatus;
  duration_s: number | null;
  engine?: string | null;
  profile_id?: string | null;
  voice_name?: string | null;
  segment?: string | null;
  shots: { id: string; kind: string; who?: string; asset?: string; seed?: number | null }[];
  wav_exists: boolean;
  wav_mtime: number | null;
}

export interface Shot {
  key: string;
  kind: "character" | "broll";
  seed: number | null;
  prompt: string;
  status: AssetStatus;
  webp_exists: boolean;
  webp_mtime: number | null;
}

export interface TitleAsset {
  key: string;
  hint: string;
  scope: "local" | "shared" | "hyperframes";
  status: AssetStatus;
  exists: boolean;
  mtime: number | null;
}

export interface PipelineStage {
  key: StageKey;
  name: string;
  n: number;
  status: AssetStatus;
  last: string;
  note: string;
}

export interface FinalInfo {
  exists: boolean;
  path: string;
  size_mb: number | null;
  duration_s: number | null;
  mtime: number | null;
  thumb_exists: boolean;
  srt_exists: boolean;
}

export interface SrtEntry {
  i: number;
  start: string;
  end: string;
  text: string;
}

export interface SrtResp {
  text: string;
  entries: SrtEntry[];
  exists: boolean;
}

export interface JobSubmitResp {
  job_id: string;
  queued: boolean;
  events_url: string;
  status_url: string;
}

export interface PipelineEvent {
  ts: number;
  kind: string;
  n?: number;
  name?: string;
  wall_s?: number;
  error?: string;
  result?: Record<string, unknown>;
  [k: string]: unknown;
}
