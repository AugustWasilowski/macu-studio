import { useEffect, useRef, useState } from "react";
import { resolveMedia } from "../mediaCache";
import type { PlayItem } from "./AudioSfx";

/**
 * Shared continuous-playback engine — a queue of PlayItems (VO cues + interleaved
 * SFX) driven by a single `new window.Audio()` with onended chaining. Factored out
 * of Audio.tsx so the Graphics dope sheet and the Video timeline play cues the same
 * way. The Audio page passes its SFX-aware buildPlaylist + version-override single
 * resolver; simpler consumers pass a cue-only buildPlaylist.
 */
export function useCuePlayback(opts: {
  buildPlaylist: () => PlayItem[];
  resolveSingle?: (cueId: string) => PlayItem | null;
  onCueChange?: (cueId: string) => void;
  notify?: (msg: string, kind?: "ok" | "err" | "info" | "run") => void;
}) {
  const { buildPlaylist, resolveSingle, onCueChange, notify } = opts;
  const [queue, setQueue] = useState<PlayItem[]>([]);
  const [qpos, setQpos] = useState<number | null>(null);
  // Default on: a per-row play button plays continuously from that clip onward.
  const [continuous, setContinuous] = useState(true);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (qpos == null) return;
    const item = queue[qpos];
    if (!item) { setQpos(null); return; }
    const a = new window.Audio(resolveMedia(item.url));
    audioRef.current = a;
    const next = () => setQpos((p) => (p != null && p + 1 < queue.length ? p + 1 : null));
    a.onended = next;
    a.onerror = () => { notify?.(`audio failed: ${item.label}`, "err"); next(); };
    a.play().catch(() => next());
    return () => { a.pause(); audioRef.current = null; };
  }, [qpos, queue]); // eslint-disable-line react-hooks/exhaustive-deps

  // Follow the playing VO cue (so the inspector / selection tracks playback).
  useEffect(() => {
    if (qpos == null) return;
    const item = queue[qpos];
    if (item?.cueId) onCueChange?.(item.cueId);
  }, [qpos, queue]); // eslint-disable-line react-hooks/exhaustive-deps

  const curCueId = qpos != null ? queue[qpos]?.cueId : undefined;
  const sequentialPlaying = qpos != null;
  const stop = () => setQpos(null);

  const togglePlay = (cueId: string) => {
    if (curCueId === cueId) { setQpos(null); return; }
    if (continuous) {
      const pl = buildPlaylist();
      const idx = pl.findIndex((it) => it.cueId === cueId);
      if (idx < 0) { notify?.("no audio for this cue", "info"); return; }
      setQueue(pl); setQpos(idx);
    } else {
      const it = resolveSingle?.(cueId);
      if (!it) { notify?.("no audio for this cue", "info"); return; }
      setQueue([it]); setQpos(0);
    }
  };

  const playAll = () => {
    if (sequentialPlaying) { setQpos(null); return; } // toggle off
    const pl = buildPlaylist();
    if (!pl.length) { notify?.("No playable clips", "info"); return; }
    setQueue(pl); setQpos(0);
  };

  return { queue, qpos, continuous, setContinuous, curCueId, sequentialPlaying, togglePlay, playAll, stop };
}
