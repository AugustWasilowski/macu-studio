import type { Cue, Overlay } from "../types";
import type { MusicBed, SfxEntry } from "../api/library";

const SFX_VIS_LEN = 0.6; // seconds — point sfx are drawn as a short fixed-width marker

/** Cumulative start-second of each cue + episode total, from per-cue durations.
 * Mirrors stage_5_music / stage_4b's cum map. Cues with no duration yet count as 0. */
export function cueOffsets(cues: Pick<Cue, "id" | "duration_s">[]) {
  const cum: Record<string, number> = {};
  let t = 0;
  for (const c of cues) {
    cum[c.id] = t;
    t += c.duration_s ?? 0;
  }
  return { cum, total: t };
}

/** Resolve an overlay to its absolute [start_s, end_s] window. */
export function overlayWindow(ov: Overlay, cum: Record<string, number>): { start: number; end: number } {
  const start = (cum[ov.anchor_cue] ?? 0) + (ov.start_offset ?? 0);
  return { start, end: start + (ov.duration ?? 0) };
}

/** The cue ids whose time-span intersects the overlay window (for read-out / span chips). */
export function coveredCues(
  ov: Overlay,
  cues: Pick<Cue, "id" | "duration_s">[],
  cum: Record<string, number>,
): string[] {
  const { start, end } = overlayWindow(ov, cum);
  const out: string[] = [];
  for (const c of cues) {
    const cs = cum[c.id] ?? 0;
    const ce = cs + (c.duration_s ?? 0);
    if (cs < end && ce > start) out.push(c.id);
  }
  return out;
}

/** Find which cue an absolute second falls in (for timeline drag → re-anchor). */
export function cueAtSecond(
  sec: number,
  cues: Pick<Cue, "id" | "duration_s">[],
  cum: Record<string, number>,
): string | null {
  let last: string | null = null;
  for (const c of cues) {
    const cs = cum[c.id] ?? 0;
    if (sec >= cs) last = c.id;
    if (sec < cs + (c.duration_s ?? 0)) return c.id;
  }
  return last ?? (cues[0]?.id ?? null);
}

/** A fresh insert placement for `asset` anchored at `cueId`, spanning that cue's duration. */
export function makeOverlay(asset: string, cueId: string, durationS: number): Overlay {
  return {
    asset,
    mode: "insert",
    anchor_cue: cueId,
    start_offset: 0,
    duration: Math.max(0.5, durationS || 3),
    position: "lower_third",
    scale: 1.0,
    opacity: 1.0,
    fade_in: 0.3,
    fade_out: 0.3,
  };
}

// ---- per-cue shots (computed even slices) ----

/** The absolute [start,end] window of shot `idx` of `n` within a cue. Shots have no
 * stored duration — each gets an even slice of the cue's screen time, mirroring stage 4
 * (`per = vo_dur / len(shots)`). Read-only geometry; dragging only changes membership/order. */
export function shotWindow(
  cue: Pick<Cue, "id" | "duration_s">,
  idx: number,
  n: number,
  cum: Record<string, number>,
): { start: number; end: number } {
  const base = cum[cue.id] ?? 0;
  const per = (cue.duration_s ?? 0) / Math.max(1, n);
  const start = base + idx * per;
  return { start, end: start + per };
}

/** Absolute [start,end] window of a cue's VO clip (read-only VO track). */
export function voWindow(
  cue: Pick<Cue, "id" | "duration_s">,
  cum: Record<string, number>,
): { start: number; end: number } {
  const start = cum[cue.id] ?? 0;
  return { start, end: start + (cue.duration_s ?? 0) };
}

// ---- music beds (cue-range spans) ----

/** Absolute [start,end] window of a bed = first cue start → last cue end. */
export function bedWindow(
  bed: MusicBed,
  cues: Pick<Cue, "id" | "duration_s">[],
  cum: Record<string, number>,
): { start: number; end: number } {
  const refs = Array.isArray(bed.cues) ? bed.cues : [];
  if (!refs.length) return { start: 0, end: 0 };
  const first = refs[0], last = refs[refs.length - 1];
  const start = cum[first] ?? 0;
  const lc = cues.find((c) => c.id === last);
  const end = (cum[last] ?? start) + (lc?.duration_s ?? 0);
  return { start, end };
}

/** The contiguous cue ids whose spans intersect [start,end] (for re-anchoring a bed on drag). */
export function cuesInRange(
  start: number,
  end: number,
  cues: Pick<Cue, "id" | "duration_s">[],
  cum: Record<string, number>,
): string[] {
  const out: string[] = [];
  for (const c of cues) {
    const cs = cum[c.id] ?? 0;
    const ce = cs + (c.duration_s ?? 0);
    if (cs < end - 0.01 && ce > start + 0.01) out.push(c.id);
  }
  return out;
}

/** A fresh music bed on `file` covering a single cue. */
export function makeBed(file: string, cueId: string, cueDur: number): MusicBed {
  return {
    name: file.replace(/\.[^.]+$/, ""),
    file,
    cues: [cueId],
    anchor: "start",
    max_seconds: Math.max(1, Math.round(cueDur || 8)),
    gain: 0.5,
    fade_in: 0.5,
    fade_out: 0.5,
  };
}

// ---- sfx one-shots (point clips pinned to a cue) ----

/** Absolute start-second of an sfx one-shot: cue start (+cue dur if at:end) + delay. */
export function sfxAnchorSec(
  e: SfxEntry,
  cues: Pick<Cue, "id" | "duration_s">[],
  cum: Record<string, number>,
): number {
  if (!e.cue) return 0;
  const base = cum[e.cue] ?? 0;
  const cueDur = e.at === "end" ? (cues.find((c) => c.id === e.cue)?.duration_s ?? 0) : 0;
  return base + cueDur + (e.delay ?? 0);
}

/** [start,end] visual window of a point sfx marker. */
export function sfxWindow(
  e: SfxEntry,
  cues: Pick<Cue, "id" | "duration_s">[],
  cum: Record<string, number>,
): { start: number; end: number } {
  const start = sfxAnchorSec(e, cues, cum);
  return { start, end: start + SFX_VIS_LEN };
}

/** Re-pin an sfx to the absolute second `sec`: nearest cue, at:start, delay = offset into it. */
export function repinSfx(
  e: SfxEntry,
  sec: number,
  cues: Pick<Cue, "id" | "duration_s">[],
  cum: Record<string, number>,
): SfxEntry {
  const cue = cueAtSecond(sec, cues, cum) ?? e.cue;
  const delay = cue ? Math.max(0, Math.round((sec - (cum[cue] ?? 0)) * 100) / 100) : 0;
  return { ...e, cue, at: "start", delay };
}
