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
  season?: number | null;
  episode_num?: number | null;
  se_label?: string | null; // "S01-E1" or null (pre-series / non-ep)
  synced?: boolean; // working text files match the tracked episode_meta copy
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
  configured?: boolean; // object-form HyperFrames entry → regennable directly
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

// ---------------------------------------------------------------------------
// Manifest shapes — mirror studio/backend/macu_studio/models.py (pydantic).
// NOTE: these describe the on-disk manifest.json. They are DISTINCT from the
// derived-row types above (Cue/Shot/TitleAsset), which are what the /cues,
// /shots, /titles endpoints return (manifest + filesystem status, flattened).
// All interfaces carry an index signature for forward-compatibility (extra=allow).
// ---------------------------------------------------------------------------
export interface VoiceProfile {
  engine?: string | null;
  profile_id?: string | null;
  voice_name?: string | null;
  speed?: number | null;
  guidance_scale?: number | null;
  seed?: number | null;
  instruct?: string | null;
  [k: string]: unknown;
}

export interface CharacterDef {
  seed?: number | null;
  core?: string | null;
  [k: string]: unknown;
}

export interface ManifestShot {
  id?: string;
  kind?: string;
  who?: string;
  asset?: string;
  seed?: number | null;
  fill?: string;
  [k: string]: unknown;
}

export interface ManifestCue {
  id: string;
  segment?: string | null;
  speaker?: string | null;
  vo?: string | null;
  shots?: ManifestShot[];
  hold_seconds?: number | null;
  hold_style?: string | null;
  no_subs?: boolean | null;
  pad_seconds?: number | null;
  [k: string]: unknown;
}

export interface TitleAssetObj {
  source?: string | null;
  composition?: string | null;
  resolution?: string | null;
  duration_seconds?: number | null;
  fields?: Record<string, unknown> | null;
  path?: string | null;
  render_args?: Record<string, unknown> | null;
  [k: string]: unknown;
}

export type OverlayMode = "insert" | "overlay";
export type OverlayPosition = "lower_third" | "bug_tl" | "bug_tr" | "center" | "full";

// A spanning title-card placement (the video twin of a music bed). Cue-tethered
// via anchor_cue + start_offset so the timeline can drag/resize freely; the
// renderer resolves it to absolute seconds against the cumulative cue-offset map.
export interface Overlay {
  id?: string;            // stable id, minted ov_NNN by gen_manifest
  asset: string;          // key into title_assets
  mode: OverlayMode;
  anchor_cue: string;     // cue the start is tethered to
  start_offset: number;   // seconds into anchor_cue
  duration: number;       // seconds on screen
  position?: OverlayPosition; // overlay-mode only
  scale?: number;
  opacity?: number;
  fade_in?: number;
  fade_out?: number;
  [k: string]: unknown;
}

export interface Manifest {
  episode?: string;
  title?: string;
  version?: number;
  voice?: { speaker_map?: Record<string, VoiceProfile>; [k: string]: unknown };
  comfyui?: Record<string, unknown>; // LOCKED, opaque
  style?: { suffix?: string; negative?: string; [k: string]: unknown };
  render_rule?: string;
  title_assets?: Record<string, TitleAssetObj | string>;
  music?: Record<string, unknown>;
  subtitles?: Record<string, unknown>; // LOCKED, opaque
  characters?: Record<string, CharacterDef | string>;
  broll?: Record<string, unknown>;
  cues?: ManifestCue[];
  sfx?: Record<string, unknown>[];
  overlays?: Overlay[];
  [k: string]: unknown;
}

// Asset versioning (versions.py summary payload)
export interface VersionEntry {
  v: number;
  file: string;
  ts: number;
  meta?: { seed?: number | null; [k: string]: unknown };
}

export interface VersionSummary {
  kind: "cue" | "shot" | "ythumb";
  key: string;
  canonical: string;
  current: { exists: boolean; mtime: number | null };
  history: VersionEntry[];
  count: number;
}
