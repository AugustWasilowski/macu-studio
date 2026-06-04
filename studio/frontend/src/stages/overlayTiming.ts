import type { Cue, Overlay } from "../types";

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
