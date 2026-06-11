import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { graphicsApi } from "../api/graphics";
import { libraryApi } from "../api/library";
import type { MusicBed, SfxEntry } from "../api/library";
import { versionsApi } from "../api/assets";
import { useStore } from "../store";
import { IPlay, IPause } from "../components/Icons";
import { useT } from "../i18n";
import {
  cueOffsets, overlayWindow, cueAtSecond, makeOverlay,
  bedWindow, cuesInRange, makeBed, sfxWindow, repinSfx,
  shotWindow, voWindow,
} from "./overlayTiming";
import { drawerDrag } from "./trackEditor";
import type { Selection, TrackKind } from "./trackEditor";
import { MetadataPanel } from "./MetadataPanel";
import type { MetaCallbacks } from "./MetadataPanel";
import { AssetDrawer } from "./AssetDrawer";
import { Collapse } from "../components/Collapse";
import type { Cue, Overlay } from "../types";

const round2 = (n: number) => Math.round(n * 100) / 100;
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

type DragState = { track: TrackKind; idx: number; kind: "move" | "l" | "r"; startX: number; start: number; end: number };

export function Timeline({ slug }: { slug: string }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);

  const cues = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug), refetchInterval: 4000 });
  const manifest = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });
  const finalQ = useQuery({ queryKey: ["final", slug], queryFn: () => api.final(slug) });

  const cueList = cues.data?.cues ?? [];
  const m = manifest.data as any;
  const overlays: Overlay[] = useMemo(() => (m?.overlays as Overlay[]) ?? [], [m]);
  const beds: MusicBed[] = useMemo(() => (m?.music?.beds as MusicBed[]) ?? [], [m]);
  const sfxList: SfxEntry[] = useMemo(() => (Array.isArray(m?.sfx) ? (m.sfx as SfxEntry[]) : []), [m]);
  const { cum, total } = useMemo(() => cueOffsets(cueList), [cueList]);

  const [pps, setPps] = useState(48);
  const [timelineOpen, setTimelineOpen] = useState(() => localStorage.getItem("macu.tl.timeline") !== "0");
  const [bottomOpen, setBottomOpen] = useState(() => localStorage.getItem("macu.tl.bottom") !== "0");
  const toggleTimeline = () => setTimelineOpen((v) => { localStorage.setItem("macu.tl.timeline", v ? "0" : "1"); return !v; });
  const toggleBottom = () => setBottomOpen((v) => { localStorage.setItem("macu.tl.bottom", v ? "0" : "1"); return !v; });
  const [selection, setSelection] = useState<Selection | null>(null);
  const [working, setWorking] = useState<null | { track: TrackKind; items: any[] }>(null);
  const [overDrawer, setOverDrawer] = useState(false);
  const [shotDragging, setShotDragging] = useState(false); // HTML5 shot-move in flight
  const dragRef = useRef<DragState | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const trashRef = useRef<HTMLDivElement | null>(null);

  // ---- preview monitor ----
  const finalExists = !!finalQ.data?.exists;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playT, setPlayT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const dur = finalQ.data?.duration_s ?? total;
  const seekTo = (sec: number) => { const v = videoRef.current; if (!v) return; v.currentTime = clamp(sec, 0, (v.duration || dur) - 0.05); v.play().catch(() => {}); };
  const togglePlay = () => { const v = videoRef.current; if (!v) return; if (v.paused) v.play().catch(() => {}); else v.pause(); };
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !playing) return;
    const x = playT * pps;
    if (x < el.scrollLeft + 60 || x > el.scrollLeft + el.clientWidth - 60) el.scrollLeft = Math.max(0, x - el.clientWidth / 3);
  }, [playT, playing, pps]);

  // ---- persistence ----
  const putOverlays = useMutation({ mutationFn: (next: Overlay[]) => graphicsApi.putOverlays(slug, next), onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }), onError: (e: Error) => push(t("toast.saveFailed", { msg: e.message }), "err") });
  const putBeds = useMutation({ mutationFn: (next: MusicBed[]) => libraryApi.putBeds(slug, next), onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }), onError: (e: Error) => push(t("toast.saveFailed", { msg: e.message }), "err") });
  const putSfx = useMutation({ mutationFn: (next: SfxEntry[]) => libraryApi.putSfx(slug, next), onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }), onError: (e: Error) => push(t("toast.saveFailed", { msg: e.message }), "err") });
  const commitTrack = (track: TrackKind, items: any[]) => {
    if (track === "graphics") putOverlays.mutate(items);
    else if (track === "music") putBeds.mutate(items);
    else if (track === "sfx") putSfx.mutate(items);
  };

  // ---- shots track (per-cue cue.shots[]; move/reorder/add/remove — no resize) ----
  const putShots = useMutation({
    mutationFn: (cuesMap: Record<string, any[]>) => versionsApi.putCueShots(slug, cuesMap),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["cues", slug] }); qc.invalidateQueries({ queryKey: ["manifest", slug] }); },
    onError: (e: Error) => push(t("toast.shotsSaveFailed", { msg: e.message }), "err"),
  });
  const cueById = (id: string) => cueList.find((c) => c.id === id);
  // Shot ids encode their cue + position (e.g. c12_s1); re-mint after any membership/order change.
  const remintShots = (cueId: string, shots: any[]) => shots.map((s, i) => ({ ...s, id: `${cueId}_s${i + 1}` }));
  // Where in a cue's shot list an absolute second lands (0..len).
  const shotInsertIdx = (sec: number, cue: Cue, len: number) => {
    const base = cum[cue.id] ?? 0; const d = cue.duration_s ?? 0;
    if (d <= 0 || len <= 0) return len;
    return clamp(Math.round(clamp((sec - base) / d, 0, 1) * len), 0, len);
  };
  const onDropShots = async (e: React.DragEvent) => {
    e.preventDefault();
    const d = drawerDrag.get();
    drawerDrag.clear();
    if (!d) return;
    const sec = secFromClientX(e.clientX);
    const targetId = cueAtSecond(sec, cueList, cum);
    const tcue = targetId ? cueById(targetId) : null;
    if (!targetId || !tcue) return;
    const tshots = (tcue.shots ?? []) as any[];
    if (d.kind === "shot") {
      try {
        if (d.version != null && d.slug) {
          // A non-live take → copy that generation's frame in + pin its seed.
          await versionsApi.importShotVersion(slug, d.slug, d.key, d.shotKind, d.version);
          push(`pulled ${d.key} take v${d.version}${d.slug !== slug ? ` from ${d.slug}` : ""} — re-render to apply`, "ok");
        } else if (d.slug && d.slug !== slug) {
          // Cross-episode live shot → copy its definition (core+seed); master too if rendered.
          const r = await versionsApi.importShot(slug, d.slug, d.key, d.shotKind);
          push(r.master_copied ? `pulled ${d.key} from ${d.slug} — ready, no render needed`
               : r.already ? `${d.key} already in this episode`
               : `imported ${d.key} from ${d.slug} — render it on the Video tab`, "ok");
        } else {
          push(`${d.key} → ${targetId}`, "ok");
        }
      } catch (err: any) { push(t("toast.importFailed", { msg: err?.message ?? "error" }), "err"); return; }
      const next = [...tshots];
      next.splice(shotInsertIdx(sec, tcue, next.length), 0, { id: "", kind: d.shotKind, who: d.key });
      putShots.mutate({ [targetId]: remintShots(targetId, next) });
    } else if (d.kind === "shot-move") {
      const src = cueById(d.cueId);
      const moving = (src?.shots ?? []).find((s: any) => s.id === d.shotId);
      if (!src || !moving) { drawerDrag.clear(); return; }
      if (d.cueId === targetId) {
        const without = (src.shots as any[]).filter((s: any) => s.id !== d.shotId);
        without.splice(shotInsertIdx(sec, tcue, without.length), 0, moving);
        putShots.mutate({ [targetId]: remintShots(targetId, without) });
      } else {
        const srcNext = (src.shots as any[]).filter((s: any) => s.id !== d.shotId);
        const tgtNext = [...tshots];
        tgtNext.splice(shotInsertIdx(sec, tcue, tgtNext.length), 0, moving);
        putShots.mutate({ [d.cueId]: remintShots(d.cueId, srcNext), [targetId]: remintShots(targetId, tgtNext) });
        push(t("toast.shotMovedTo", { targetId }), "ok");
      }
    }
    drawerDrag.clear();
  };
  // Remove a shot from its cue — used by the ✕ button, the drawer drop, and the
  // trash zone. Undoable: the toast's UNDO restores the exact previous array.
  const removeShot = (cueId: string, shotId: string) => {
    const src = cueById(cueId);
    if (!src) return;
    const prev = ((src.shots ?? []) as any[]).map((s) => ({ ...s }));
    const next = prev.filter((s) => s.id !== shotId);
    putShots.mutate({ [cueId]: remintShots(cueId, next) });
    push(t("toast.shotRemoved"), "ok", {
      action: { label: t("common.undo"), fn: () => putShots.mutate({ [cueId]: prev }) },
    });
  };
  // Drop an existing shot bar onto the drawer / trash zone to remove it.
  const onShotDropRemove = (e: React.DragEvent) => {
    const d = drawerDrag.get();
    if (d?.kind !== "shot-move") return;
    e.preventDefault();
    removeShot(d.cueId, d.shotId);
    drawerDrag.clear();
  };

  // ---- VO audition (read-only VO track) ----
  const voAudioRef = useRef<HTMLAudioElement | null>(null);
  const playVo = (c: Cue) => {
    const a = voAudioRef.current; if (!a) return;
    a.src = mediaUrl.cueAudio(slug, c.id, c.wav_mtime);
    a.play().catch(() => {});
  };

  // shown arrays (override the active track with the in-flight working copy)
  const shownOverlays: Overlay[] = working?.track === "graphics" ? working.items : overlays;
  const shownBeds: MusicBed[] = working?.track === "music" ? working.items : beds;
  const shownSfx: SfxEntry[] = working?.track === "sfx" ? working.items : sfxList;

  // Remove a clip from an array-backed track (graphics/music/sfx) with undo.
  // Single chokepoint for the ✕ buttons, Delete key, metadata panel, and
  // drag-to-remove so every path gets the same toast + UNDO behavior.
  const removeFromTrack = (track: Exclude<TrackKind, "shots">, idx: number, prevOverride?: any[]) => {
    const src = track === "graphics" ? overlays : track === "music" ? beds : sfxList;
    const prev = prevOverride ?? src.map((x: any) => ({ ...x }));
    if (idx < 0 || idx >= prev.length) return;
    commitTrack(track, prev.filter((_: any, i: number) => i !== idx));
    setSelection(null);
    push(t("toast.removedFromTimeline"), "ok", {
      action: { label: t("common.undo"), fn: () => commitTrack(track, prev) },
    });
  };

  // Delete/Backspace removes the selected clip (unless focus is in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable)) return;
      if (!selection) return;
      if (selection.t === "overlay") { e.preventDefault(); removeFromTrack("graphics", selection.idx); }
      else if (selection.t === "bed") { e.preventDefault(); removeFromTrack("music", selection.idx); }
      else if (selection.t === "sfx") { e.preventDefault(); removeFromTrack("sfx", selection.idx); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection, overlays, beds, sfxList]);

  // ---- metadata-panel edit callbacks ----
  const cb: MetaCallbacks = {
    slug,
    patchOverlay: (idx, p) => commitTrack("graphics", overlays.map((o, i) => i === idx ? { ...o, ...p } : o)),
    removeOverlay: (idx) => removeFromTrack("graphics", idx),
    patchSfx: (idx, p) => commitTrack("sfx", sfxList.map((e, i) => i === idx ? { ...e, ...p } : e)),
    removeSfx: (idx) => removeFromTrack("sfx", idx),
    patchBed: (idx, p) => commitTrack("music", beds.map((b, i) => i === idx ? { ...b, ...p } : b)),
    removeBed: (idx) => removeFromTrack("music", idx),
  };

  // ---- snap to cue boundaries ----
  const boundaries = useMemo(() => { const bs = cueList.map((c) => cum[c.id] ?? 0); bs.push(total); return bs; }, [cueList, cum, total]);
  const snap = (sec: number) => { const thr = 7 / pps; let best = sec, bestD = thr; for (const b of boundaries) { const d = Math.abs(sec - b); if (d < bestD) { best = b; bestD = d; } } return best; };
  const cueDurOf = (id: string) => cueList.find((c) => c.id === id)?.duration_s ?? 0;

  // ---- pointer drag (move / resize) ----
  const beginDrag = (e: React.PointerEvent, track: TrackKind, idx: number, kind: DragState["kind"], win: { start: number; end: number }, select: Selection) => {
    e.stopPropagation();
    dragRef.current = { track, idx, kind, startX: e.clientX, start: win.start, end: win.end };
    const src = track === "graphics" ? overlays : track === "music" ? beds : sfxList;
    setWorking({ track, items: src.map((x) => ({ ...x })) });
    setSelection(select);
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  };

  const onMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    // drag-to-remove hover check (move drags only — resizes can't delete):
    // the floating trash zone always counts; the asset drawer area counts
    // too when it's open.
    if (d.kind === "move") {
      const tz = trashRef.current?.getBoundingClientRect();
      const dr = drawerRef.current?.getBoundingClientRect();
      const overTrash = !!tz && e.clientY >= tz.top - 8 && e.clientY <= tz.bottom + 8 && e.clientX >= tz.left - 8 && e.clientX <= tz.right + 8;
      setOverDrawer(overTrash || (!!dr && bottomOpen && e.clientY >= dr.top));
    }
    const dxSec = (e.clientX - d.startX) / pps;
    setWorking((prev) => {
      if (!prev) return prev;
      const items = prev.items.map((x) => ({ ...x }));
      const it = items[d.idx];
      const len = d.end - d.start;
      if (d.track === "graphics") {
        let s = d.start, du = len;
        if (d.kind === "move") s = snap(clamp(d.start + dxSec, 0, Math.max(0, total - len)));
        else if (d.kind === "r") du = snap(clamp(d.end + dxSec, d.start + 0.3, total)) - d.start;
        else { s = snap(clamp(d.start + dxSec, 0, d.end - 0.3)); du = d.end - s; }
        const anchor = cueAtSecond(s, cueList, cum) ?? it.anchor_cue;
        it.anchor_cue = anchor; it.start_offset = round2(s - (cum[anchor] ?? 0)); it.duration = round2(du);
      } else if (d.track === "music") {
        let ns = d.start, ne = d.end;
        if (d.kind === "move") { ns = snap(clamp(d.start + dxSec, 0, Math.max(0, total - len))); ne = ns + len; }
        else if (d.kind === "r") ne = snap(clamp(d.end + dxSec, d.start + 0.3, total));
        else ns = snap(clamp(d.start + dxSec, 0, d.end - 0.3));
        const cuesR = cuesInRange(ns, ne, cueList, cum);
        if (cuesR.length) { it.cues = cuesR; it.max_seconds = Math.max(1, Math.round(ne - ns)); }
      } else { // sfx — move only
        if (d.kind === "move") { const s = snap(clamp(d.start + dxSec, 0, total)); Object.assign(it, repinSfx(it, s, cueList, cum)); }
      }
      return { ...prev, items };
    });
  };

  const endDrag = () => {
    const d = dragRef.current;
    if (!d || !working) { dragRef.current = null; return; }
    const removed = overDrawer;
    dragRef.current = null;
    setOverDrawer(false);
    if (removed && d.track !== "shots") {
      // Undo restores the pre-drag arrays (query data is still untouched here).
      const srcOrig = d.track === "graphics" ? overlays : d.track === "music" ? beds : sfxList;
      removeFromTrack(d.track, d.idx, srcOrig.map((x: any) => ({ ...x })));
    } else {
      commitTrack(d.track, working.items);
    }
    setWorking(null);
  };

  // ---- drawer → track drops ----
  const secFromClientX = (clientX: number) => { const el = scrollRef.current; if (!el) return 0; const r = el.getBoundingClientRect(); return clamp((clientX - r.left + el.scrollLeft) / pps, 0, total); };
  const onDropGraphics = async (e: React.DragEvent) => {
    e.preventDefault();
    const d = drawerDrag.get();
    drawerDrag.clear();
    if (d?.kind !== "card") return;
    const sec = secFromClientX(e.clientX);
    const anchor = cueAtSecond(sec, cueList, cum);
    if (!anchor) return;
    if (d.slug && d.slug !== slug) {
      try {
        const r = await versionsApi.importTitle(slug, d.slug, d.asset);
        push(r.master_copied ? `pulled ${d.asset} from ${d.slug} — ready`
             : r.already ? `${d.asset} already in this episode`
             : `imported ${d.asset} from ${d.slug} — render it on the Graphics tab`, "ok");
      } catch (err: any) { push(t("toast.importFailed", { msg: err?.message ?? "error" }), "err"); return; }
    }
    const ov = makeOverlay(d.asset, anchor, 3);
    ov.start_offset = round2(sec - (cum[anchor] ?? 0));
    commitTrack("graphics", [...overlays, ov]);
    if (!d.slug || d.slug === slug) push(t("toast.graphicAdded", { asset: d.asset, cueId: anchor }), "ok");
  };
  const onDropMusic = (e: React.DragEvent) => { e.preventDefault(); const d = drawerDrag.get(); if (d?.kind !== "music") return; const sec = secFromClientX(e.clientX); const anchor = cueAtSecond(sec, cueList, cum); if (!anchor) return; commitTrack("music", [...beds, makeBed(d.file, anchor, cueDurOf(anchor))]); push(t("toast.musicBedAdded", { file: d.file }), "ok"); drawerDrag.clear(); };
  const onDropSfx = (e: React.DragEvent) => { e.preventDefault(); const d = drawerDrag.get(); if (d?.kind !== "sfx") return; const sec = secFromClientX(e.clientX); const cue = cueAtSecond(sec, cueList, cum); if (!cue) return; const entry = repinSfx({ file: d.file, cue, at: "start", gain: 0.4, source: "library" } as SfxEntry, sec, cueList, cum); commitTrack("sfx", [...sfxList, entry]); push(t("toast.sfxAdded", { file: d.file, cue }), "ok"); drawerDrag.clear(); };

  const cueThumb = (c: Cue): string | null => { for (const s of (c.shots || []) as any[]) { if ((s.kind === "character" || s.kind === "broll") && s.who) return mediaUrl.shotPreview(slug, s.who); } return null; };

  const width = Math.max(640, total * pps + 40);
  const ticks: number[] = []; for (let t = 0; t <= total; t += 5) ticks.push(t);

  return (
    <div className="flex flex-col gap-3 h-full min-h-0 min-w-0">
      {/* PREVIEW */}
      <section className="panel flex flex-col min-h-0 flex-1 p-2 gap-2">
        <div className="flex items-center justify-between">
          <div className="panel-title">{t("timeline.previewTitle")} <span className="text-txt-faint normal-case tracking-normal text-[11px]">{t("timeline.previewSubtitle")}</span></div>
          <div className="flex items-center gap-3">
            <button className="btn btn-cyan" disabled={!finalExists} onClick={togglePlay} title={playing ? t("timeline.pause") : t("timeline.play")}>{playing ? <IPause /> : <IPlay />} {playing ? t("timeline.pause") : t("timeline.play")}</button>
            <span className="font-mono tabular-nums text-[12px]">{fmt(playT)} <span className="text-txt-faint">/ {fmt(dur)}</span></span>
          </div>
        </div>
        <div className="flex-1 min-h-0 bg-black hairline-soft rounded grid place-items-center overflow-hidden">
          {finalExists ? (
            <video ref={videoRef} src={mediaUrl.finalVideo(slug)} className="max-h-full max-w-full object-contain" playsInline
              onTimeUpdate={(e) => setPlayT((e.currentTarget as HTMLVideoElement).currentTime)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
          ) : <div className="text-txt-faint text-[12px] text-center px-3">{t("timeline.noVideoYet")}</div>}
        </div>
      </section>

      {/* TIMELINE */}
      <section className="panel flex flex-col flex-none relative">
        <CollapseTab open={timelineOpen} onToggle={toggleTimeline} label={t("timeline.sectionLabel")} />
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">{t("timeline.timelineTitle")} <span className="text-txt-faint normal-case tracking-normal text-[11px]">{t("timeline.timelineSubtitle")}</span></div>
          <div className="flex items-center gap-2 text-[11px]">
            <span className="seg-readout">{cueList.reduce((a, c) => a + ((c.shots ?? []).length), 0)} ▦ · {shownOverlays.length} GFX · {shownBeds.length} ♫ · {shownSfx.length} ♪ · {total.toFixed(1)}s</span>
            <button className="btn p-1" title={t("timeline.zoomOut")} onClick={() => setPps((z) => Math.max(12, z - 12))}>−</button>
            <span className="text-txt-faint">{pps}px/s</span>
            <button className="btn p-1" title={t("timeline.zoomIn")} onClick={() => setPps((z) => Math.min(160, z + 12))}>+</button>
          </div>
        </header>
        <Collapse open={timelineOpen}>
        <div ref={scrollRef} className="overflow-x-auto overflow-y-hidden" onPointerMove={onMove} onPointerUp={endDrag} onPointerLeave={endDrag}>
          <div style={{ width }} className="select-none relative">
            {/* ruler — the only scrub surface */}
            <div className="relative h-5 border-b hairline-soft text-[10px] text-txt-faint cursor-pointer" onClick={(e) => seekTo(secFromClientX(e.clientX))} title={t("timeline.rulerScrub")}>
              {ticks.map((t) => <div key={t} className="absolute top-0 h-full border-l border-[var(--line-soft)] pl-1" style={{ left: t * pps }}>{t}s</div>)}
            </div>

            {/* CUES — filmstrip, click to select */}
            <TrackLabel label={t("timeline.trackCues")} />
            <div className="relative h-16 border-b hairline-soft">
              {cueList.map((c) => {
                const left = (cum[c.id] ?? 0) * pps; const w = (c.duration_s ?? 0) * pps; const thumb = cueThumb(c);
                const active = selection?.t === "cue" && selection.cue.id === c.id;
                return (
                  <div key={c.id} onClick={() => setSelection({ t: "cue", cue: c })}
                    className="absolute top-0.5 rounded-sm overflow-hidden cursor-pointer hairline-soft"
                    style={{ left, width: Math.max(2, w), height: "calc(100% - 4px)", backgroundColor: "var(--bg-2)", backgroundImage: thumb ? `url(${thumb})` : undefined, backgroundRepeat: "repeat-x", backgroundSize: "auto 100%", outline: active ? "1px solid var(--amber)" : undefined }}
                    title={`${c.id} · ${c.speaker} — ${t("timeline.cueMetaTip")}`}>
                    <div className="absolute inset-x-0 bottom-0 px-1 text-[9px] leading-tight" style={{ background: "linear-gradient(transparent, rgba(0,0,0,0.85))" }}>
                      <span className="text-amber font-bold">{c.id}</span> <span className="text-txt-dim">{c.speaker}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* VO — read-only: each cue's narration clip; click to audition */}
            <TrackLabel label={t("timeline.trackVo")} />
            <div className="relative h-7 border-b hairline-soft">
              {cueList.map((c) => {
                if ((c.duration_s ?? 0) <= 0) return null;
                const { start, end } = voWindow(c, cum); const left = start * pps; const w = Math.max(4, (end - start) * pps);
                return (
                  <div key={c.id} onClick={() => playVo(c)} title={`${c.id} VO${c.wav_exists ? ` — ${t("timeline.voAuditionTip")}` : ` (${t("timeline.voNoWavTip")})`}`}
                    className="absolute top-0.5 h-6 rounded-sm overflow-hidden cursor-pointer flex items-center px-1 bg-[#23303a]"
                    style={{ left, width: w, outline: "1px solid var(--line-soft)", opacity: c.wav_exists ? 1 : 0.45 }}>
                    <span className="font-mono text-[10px] truncate pointer-events-none text-[#9ad6ff]">{c.id}</span>
                  </div>
                );
              })}
              {cueList.length === 0 && <Empty label={t("timeline.emptyVo")} />}
            </div>

            {/* SHOTS — per-cue, move/reorder/add/remove (no resize); width is the computed slice */}
            <TrackLabel label={t("timeline.trackShots")} />
            <div className="relative h-12 border-b hairline-soft" onDragOver={(e) => e.preventDefault()} onDrop={onDropShots}>
              {cueList.map((c) => {
                const shots = (c.shots ?? []) as any[];
                const n = shots.length;
                return shots.map((s, idx) => {
                  const { start, end } = shotWindow(c, idx, n, cum); const left = start * pps; const w = Math.max(8, (end - start) * pps);
                  const key = s.who ?? s.asset ?? "?"; const thumb = (s.who || s.asset) ? mediaUrl.shotPreview(slug, s.who ?? s.asset) : null;
                  return (
                    <div key={s.id ?? `${c.id}_${idx}`} draggable
                      onDragStart={() => { drawerDrag.set({ kind: "shot-move", cueId: c.id, shotId: s.id }); setShotDragging(true); }}
                      onDragEnd={() => { drawerDrag.clear(); setShotDragging(false); setOverDrawer(false); }}
                      onClick={() => setSelection({ t: "cue", cue: c })}
                      className="group-clip absolute top-1 h-10 rounded-sm overflow-hidden cursor-grab flex items-center px-1 bg-[#1c2b1c]"
                      style={{ left, width: w, outline: "1px solid var(--line-soft)", backgroundImage: thumb ? `url(${thumb})` : undefined, backgroundRepeat: "repeat-x", backgroundSize: "auto 100%" }}
                      title={`${key} (${c.id}) — ${t("timeline.shotMoveTip")}`}>
                      <span className="font-mono text-[9px] truncate pointer-events-none px-1 rounded" style={{ background: "rgba(0,0,0,0.6)" }}>{key}</span>
                      <ClipX title={t("timeline.removeClip")} onRemove={() => removeShot(c.id, s.id)} />
                    </div>
                  );
                });
              })}
              {cueList.every((c) => !((c.shots ?? []) as any[]).length) && <Empty label={t("timeline.emptyShots")} />}
            </div>

            {/* GRAPHICS — editable overlay bars */}
            <TrackLabel label={t("timeline.trackGraphics")} />
            <div className="relative h-12 border-b hairline-soft" onDragOver={(e) => e.preventDefault()} onDrop={onDropGraphics}>
              {shownOverlays.map((ov, idx) => {
                const { start, end } = overlayWindow(ov, cum); const left = start * pps; const w = Math.max(8, (end - start) * pps);
                const active = selection?.t === "overlay" && selection.idx === idx;
                return (
                  <div key={ov.id ?? idx} onPointerDown={(e) => beginDrag(e, "graphics", idx, "move", { start, end }, { t: "overlay", idx, ov })}
                    className={"group-clip absolute top-1 h-10 rounded-sm overflow-hidden cursor-grab flex items-center gap-1 px-1 " + (ov.mode === "overlay" ? "bg-[#0c3b44]" : "bg-[#3b2e0c]")}
                    style={{ left, width: w, outline: active ? "1px solid var(--amber)" : "1px solid var(--line-soft)", boxShadow: active ? "var(--glow-amber)" : undefined }} title={`${ov.asset} · ${ov.mode}`}>
                    <span onPointerDown={(e) => beginDrag(e, "graphics", idx, "l", { start, end }, { t: "overlay", idx, ov })} className="absolute left-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                    <video src={mediaUrl.titlePreview(slug, ov.asset)} muted loop autoPlay playsInline className="bg-black rounded pointer-events-none flex-none" style={{ width: 26, height: 26, objectFit: "contain" }} />
                    <span className="font-mono text-[10px] truncate pointer-events-none">{ov.asset}</span>
                    <span onPointerDown={(e) => beginDrag(e, "graphics", idx, "r", { start, end }, { t: "overlay", idx, ov })} className="absolute right-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                    <ClipX title={t("timeline.removeClip")} right={9} onRemove={() => removeFromTrack("graphics", idx)} />
                  </div>
                );
              })}
              {shownOverlays.length === 0 && <Empty label={t("timeline.emptyGraphics")} />}
            </div>

            {/* MUSIC — editable beds */}
            <TrackLabel label={t("timeline.trackMusic")} />
            <div className="relative h-8 border-b hairline-soft" onDragOver={(e) => e.preventDefault()} onDrop={onDropMusic}>
              {shownBeds.map((b, idx) => {
                const { start, end } = bedWindow(b, cueList, cum); const left = start * pps; const w = Math.max(8, (end - start) * pps);
                const active = selection?.t === "bed" && selection.idx === idx;
                return (
                  <div key={idx} onPointerDown={(e) => beginDrag(e, "music", idx, "move", { start, end }, { t: "bed", idx, b })}
                    className="group-clip absolute top-0.5 h-7 rounded-sm overflow-hidden cursor-grab flex items-center gap-1 px-1 bg-[#2a1840]"
                    style={{ left, width: w, outline: active ? "1px solid var(--amber)" : "1px solid var(--line-soft)", boxShadow: active ? "var(--glow-amber)" : undefined }} title={`${b.name || b.file} bed`}>
                    <span onPointerDown={(e) => beginDrag(e, "music", idx, "l", { start, end }, { t: "bed", idx, b })} className="absolute left-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                    <span className="font-mono text-[10px] truncate pointer-events-none text-[#c7a3ff]">♫ {b.name || b.file}</span>
                    <span onPointerDown={(e) => beginDrag(e, "music", idx, "r", { start, end }, { t: "bed", idx, b })} className="absolute right-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                    <ClipX title={t("timeline.removeClip")} right={9} onRemove={() => removeFromTrack("music", idx)} />
                  </div>
                );
              })}
              {shownBeds.length === 0 && <Empty label={t("timeline.emptyMusic")} />}
            </div>

            {/* SFX — point markers, move only */}
            <TrackLabel label={t("timeline.trackSfx")} />
            <div className="relative h-7" onDragOver={(e) => e.preventDefault()} onDrop={onDropSfx}>
              {shownSfx.map((e2, idx) => {
                const { start, end } = sfxWindow(e2, cueList, cum); const left = start * pps; const w = Math.max(10, (end - start) * pps);
                const active = selection?.t === "sfx" && selection.idx === idx;
                return (
                  <div key={idx} onPointerDown={(ev) => beginDrag(ev, "sfx", idx, "move", { start, end }, { t: "sfx", idx, e: e2 })}
                    className="group-clip absolute top-0.5 h-6 rounded-sm overflow-hidden cursor-grab flex items-center px-1 bg-[#0c3a3a]"
                    style={{ left, width: w, outline: active ? "1px solid var(--amber)" : "1px solid var(--line-soft)", boxShadow: active ? "var(--glow-amber)" : undefined }} title={`${e2.file} @ ${e2.cue}`}>
                    <span className="font-mono text-[10px] truncate pointer-events-none text-[#6fe0e0]">♪ {e2.file}</span>
                    <ClipX title={t("timeline.removeClip")} onRemove={() => removeFromTrack("sfx", idx)} />
                  </div>
                );
              })}
              {shownSfx.length === 0 && <Empty label={t("timeline.emptySfx")} />}
            </div>

            {/* playhead */}
            {playT > 0 && <div className="absolute top-0 bottom-0 pointer-events-none z-20" style={{ left: playT * pps, width: 2, background: "var(--cyan)", boxShadow: "0 0 6px var(--cyan)" }} />}
          </div>
        </div>
        </Collapse>
      </section>

      {/* DRAWER + METADATA (collapse together) — definite height so the drawer scrolls
          internally (instead of bleeding off-page) and the preview's flex-1 gets correct
          leftover space above it. Content stays mounted through a collapse (Collapse
          animates height) so drawer tab/filter state and queries survive. */}
      <div className="relative flex-none" style={{ minHeight: 16 }}>
        <CollapseTab open={bottomOpen} onToggle={toggleBottom} label={t("timeline.drawerLabel")} />
        <Collapse open={bottomOpen}>
          <div className="grid grid-cols-[1fr_320px] grid-rows-[minmax(0,1fr)] gap-3 min-h-0" style={{ height: 240 }}>
            <div ref={drawerRef} className="min-h-0 min-w-0"
              onDragOver={(e) => { if (drawerDrag.get()?.kind === "shot-move") e.preventDefault(); }}
              onDrop={onShotDropRemove}><AssetDrawer slug={slug} onSelect={setSelection} removeActive={overDrawer} /></div>
            <MetadataPanel sel={selection} cb={cb} overlays={overlays} beds={beds} sfx={sfxList} />
          </div>
        </Collapse>
      </div>
      {/* Floating trash dock — appears during any clip drag so removal works even
          with the bottom drawer collapsed. Pointer drags hit-test its rect in
          onMove; HTML5 shot drags use the native dragover/drop handlers. */}
      {((working !== null && dragRef.current?.kind === "move") || shotDragging) && (
        <div
          ref={trashRef}
          className={"remove-zone" + (overDrawer ? " hot" : "")}
          onDragOver={(e) => { if (drawerDrag.get()?.kind === "shot-move") { e.preventDefault(); setOverDrawer(true); } }}
          onDragLeave={() => setOverDrawer(false)}
          onDrop={(e) => { onShotDropRemove(e); setOverDrawer(false); setShotDragging(false); }}
        >
          ✕ {t("asset.dropToRemove")}
        </div>
      )}
      <audio ref={voAudioRef} hidden />
    </div>
  );
}

/** Hover ✕ on a timeline clip. Stops pointer/mouse-down so it never starts a
    drag on the clip underneath. `right` clears resize handles where present. */
function ClipX({ onRemove, title, right = 2 }: { onRemove: () => void; title: string; right?: number }) {
  return (
    <button
      className="clip-x"
      style={{ right }}
      title={title}
      draggable={false}
      onPointerDown={(e) => { e.stopPropagation(); e.preventDefault(); }}
      onMouseDown={(e) => { e.stopPropagation(); e.preventDefault(); }}
      onClick={(e) => { e.stopPropagation(); onRemove(); }}
    >
      ✕
    </button>
  );
}

function CollapseTab({ open, onToggle, label }: { open: boolean; onToggle: () => void; label: string }) {
  const t = useT();
  return (
    <button
      onClick={onToggle}
      title={open ? t("timeline.collapseTitle", { label }) : t("timeline.expandTitle", { label })}
      className="absolute left-1/2 z-30 flex items-center justify-center"
      style={{
        transform: "translateX(-50%)", top: -8, width: 56, height: 15,
        background: "var(--amber)", color: "#1a1206", borderRadius: 5,
        fontSize: 11, fontWeight: 700, lineHeight: 1, boxShadow: "var(--glow-amber)",
      }}
    >
      <span style={{ display: "inline-block", transition: "transform 0.25s ease", transform: open ? "none" : "rotate(180deg)" }}>▼</span>
    </button>
  );
}

function TrackLabel({ label }: { label: string }) {
  return <div className="label-tiny px-2 pt-1 pb-0.5 text-txt-faint sticky left-0">{label}</div>;
}

function Empty({ label }: { label: string }) {
  return <div className="absolute inset-0 grid place-items-center text-txt-faint text-[11px] pointer-events-none">{label}</div>;
}
