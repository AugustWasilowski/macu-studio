export type StageKey =
  | "vo"
  | "masters"
  | "rife"
  | "assemble"
  | "music"
  | "whisper"
  | "srt"
  | "burn";

export type UIStage = "script" | "audio" | "graphics" | "video" | "assembly" | "publish";
export const UI_STAGES: { key: UIStage; label: string; n: number }[] = [
  { key: "script", label: "Script", n: 1 },
  { key: "audio", label: "Audio", n: 2 },
  { key: "graphics", label: "Graphics", n: 3 },
  { key: "video", label: "Video", n: 4 },
  { key: "assembly", label: "Assembly", n: 5 },
  { key: "publish", label: "Publish", n: 6 },
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
  show?: string; // owning show id
  published?: boolean; // manifest `published` → public on macu-web (else hidden draft)
  youtube_id?: string | null; // video id from youtube.txt → drives the macu-web embed
  parent_slug?: string | null; // localized variant (ep9-uk) → its English source slug (ep-009); else null
  language?: string | null; // 2-letter code for a localized variant (uk/hi/es); null for the English canonical
}

// ---- Multi-show ----
export interface ShowSummary {
  id: string;
  name: string;
  episodes_dir: string;
  assets_dir?: string;
  title_prefix?: string;
  episode_count: number;
  is_default: boolean;
}

export interface ShowConfig {
  id: string;
  name: string;
  episodes_dir: string;
  assets_dir?: string;
  title_prefix?: string;
  episode_defaults?: Record<string, unknown>;
  [k: string]: unknown;
}

// ---- Archive ----
export interface ArchivedEpisode {
  name: string; // container dir name = stable id for unarchive
  slug: string; // original episode slug
  title: string;
  show: string;
  archived_at_iso?: string | null;
  variants: string[];
}

export interface ArchivedShow {
  name: string; // container dir name = stable id for unarchive
  show: string; // show id
  display_name: string;
  archived_at_iso?: string | null;
  episode_count: number;
}

export interface ArchiveList {
  episodes: Record<string, ArchivedEpisode[]>; // keyed by show id
  shows: ArchivedShow[];
}

export interface ImportResult {
  ok: boolean;
  show?: string; // "" / absent for voices-only imports
  kind: string;
  created_show?: boolean;
  created?: string[];
  updated?: string[];
  templates?: string[];
  voices?: string[];
  sfx?: string[];
  music?: string[];
  docs?: string[];
  characters?: string[];
  stills?: number;
  clips?: number;
  errors?: string[];
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
  shots: {
    id: string; kind: string; who?: string; asset?: string; seed?: number | null;
    // cloud (higgsfield/lipsync) shot fields — round-tripped through putCueShots:
    model?: string; prompt?: string; duration?: number; source_still?: string;
    crop?: { x?: number; y?: number; zoom?: number } | null;
    trim?: { in?: number; out?: number } | null;
    jank?: boolean;
  }[];
  wav_exists: boolean;
  wav_mtime: number | null;
}

export interface Shot {
  key: string;
  kind: "character" | "broll" | "higgsfield" | "lipsync";
  seed: number | null;
  prompt: string;
  status: AssetStatus;
  webp_exists: boolean;
  webp_mtime: number | null;
  // Cloud (Higgsfield) rows only — per-shot-id, hash-accurate status:
  cue?: string;
  model?: string;
  source_still?: string | null;
  clip_exists?: boolean;
  clip_mtime?: number | null;
}

export const isCloudKind = (k: string): boolean => k === "higgsfield" || k === "lipsync";

export interface TitleAsset {
  key: string;
  hint: string;
  scope: "local" | "shared" | "hyperframes";
  status: AssetStatus;
  exists: boolean;
  mtime: number | null;
  configured?: boolean; // object-form HyperFrames entry → regennable directly
  composition?: string | null; // present on configured (object-form) cards
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
