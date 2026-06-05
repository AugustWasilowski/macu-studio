import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { graphicsApi } from "../api/graphics";
import { libraryApi } from "../api/library";
import type { MusicBed, SfxEntry } from "../api/library";
import { useStore } from "../store";
import { IPlay, IPause } from "../components/Icons";
import {
  cueOffsets, overlayWindow, cueAtSecond, makeOverlay,
  bedWindow, cuesInRange, makeBed, sfxWindow, repinSfx,
} from "./overlayTiming";
import { drawerDrag } from "./trackEditor";
import type { Selection, TrackKind } from "./trackEditor";
import { MetadataPanel } from "./MetadataPanel";
import type { MetaCallbacks } from "./MetadataPanel";
import { AssetDrawer } from "./AssetDrawer";
import type { Cue, Overlay } from "../types";

const round2 = (n: number) => Math.round(n * 100) / 100;
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

type DragState = { track: TrackKind; idx: number; kind: "move" | "l" | "r"; startX: number; start: number; end: number };

export function Timeline({ slug }: { slug: string }) {
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
  const dragRef = useRef<DragState | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const drawerRef = useRef<HTMLDivElement | null>(null);

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
  const putOverlays = useMutation({ mutationFn: (next: Overlay[]) => graphicsApi.putOverlays(slug, next), onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }), onError: (e: Error) => push("save failed: " + e.message, "err") });
  const putBeds = useMutation({ mutationFn: (next: MusicBed[]) => libraryApi.putBeds(slug, next), onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }), onError: (e: Error) => push("save failed: " + e.message, "err") });
  const putSfx = useMutation({ mutationFn: (next: SfxEntry[]) => libraryApi.putSfx(slug, next), onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }), onError: (e: Error) => push("save failed: " + e.message, "err") });
  const commitTrack = (track: TrackKind, items: any[]) => {
    if (track === "graphics") putOverlays.mutate(items);
    else if (track === "music") putBeds.mutate(items);
    else putSfx.mutate(items);
  };

  // shown arrays (override the active track with the in-flight working copy)
  const shownOverlays: Overlay[] = working?.track === "graphics" ? working.items : overlays;
  const shownBeds: MusicBed[] = working?.track === "music" ? working.items : beds;
  const shownSfx: SfxEntry[] = working?.track === "sfx" ? working.items : sfxList;

  // ---- metadata-panel edit callbacks ----
  const cb: MetaCallbacks = {
    slug,
    patchOverlay: (idx, p) => commitTrack("graphics", overlays.map((o, i) => i === idx ? { ...o, ...p } : o)),
    removeOverlay: (idx) => { commitTrack("graphics", overlays.filter((_, i) => i !== idx)); setSelection(null); },
    patchSfx: (idx, p) => commitTrack("sfx", sfxList.map((e, i) => i === idx ? { ...e, ...p } : e)),
    removeSfx: (idx) => { commitTrack("sfx", sfxList.filter((_, i) => i !== idx)); setSelection(null); },
    patchBed: (idx, p) => commitTrack("music", beds.map((b, i) => i === idx ? { ...b, ...p } : b)),
    removeBed: (idx) => { commitTrack("music", beds.filter((_, i) => i !== idx)); setSelection(null); },
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
    // drag-to-remove hover check
    const dr = drawerRef.current;
    setOverDrawer(!!dr && e.clientY >= dr.getBoundingClientRect().top);
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
    const dr = drawerRef.current;
    const removed = overDrawer && !!dr;
    dragRef.current = null;
    setOverDrawer(false);
    if (removed) {
      const next = working.items.filter((_, i) => i !== d.idx);
      commitTrack(d.track, next);
      setSelection(null);
      push("removed from timeline", "ok");
    } else {
      commitTrack(d.track, working.items);
    }
    setWorking(null);
  };

  // ---- drawer → track drops ----
  const secFromClientX = (clientX: number) => { const el = scrollRef.current; if (!el) return 0; const r = el.getBoundingClientRect(); return clamp((clientX - r.left + el.scrollLeft) / pps, 0, total); };
  const onDropGraphics = (e: React.DragEvent) => { e.preventDefault(); const d = drawerDrag.get(); if (d?.kind !== "card") return; const sec = secFromClientX(e.clientX); const anchor = cueAtSecond(sec, cueList, cum); if (!anchor) return; const ov = makeOverlay(d.asset, anchor, 3); ov.start_offset = round2(sec - (cum[anchor] ?? 0)); commitTrack("graphics", [...overlays, ov]); push(`${d.asset} → graphic`, "ok"); drawerDrag.clear(); };
  const onDropMusic = (e: React.DragEvent) => { e.preventDefault(); const d = drawerDrag.get(); if (d?.kind !== "music") return; const sec = secFromClientX(e.clientX); const anchor = cueAtSecond(sec, cueList, cum); if (!anchor) return; commitTrack("music", [...beds, makeBed(d.file, anchor, cueDurOf(anchor))]); push(`${d.file} → music bed`, "ok"); drawerDrag.clear(); };
  const onDropSfx = (e: React.DragEvent) => { e.preventDefault(); const d = drawerDrag.get(); if (d?.kind !== "sfx") return; const sec = secFromClientX(e.clientX); const cue = cueAtSecond(sec, cueList, cum); if (!cue) return; const entry = repinSfx({ file: d.file, cue, at: "start", gain: 0.4, source: "library" } as SfxEntry, sec, cueList, cum); commitTrack("sfx", [...sfxList, entry]); push(`${d.file} → sfx @ ${cue}`, "ok"); drawerDrag.clear(); };

  const cueThumb = (c: Cue): string | null => { for (const s of (c.shots || []) as any[]) { if ((s.kind === "character" || s.kind === "broll") && s.who) return mediaUrl.shotPreview(slug, s.who); } return null; };

  const width = Math.max(640, total * pps + 40);
  const ticks: number[] = []; for (let t = 0; t <= total; t += 5) ticks.push(t);

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      {/* PREVIEW */}
      <section className="panel flex flex-col min-h-0 flex-1 p-2 gap-2">
        <div className="flex items-center justify-between">
          <div className="panel-title">PREVIEW <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ rendered output · click a cue to play · audio/graphic edits show after a re-render</span></div>
          <div className="flex items-center gap-3">
            <button className="btn btn-cyan" disabled={!finalExists} onClick={togglePlay} title={playing ? "Pause" : "Play"}>{playing ? <IPause /> : <IPlay />} {playing ? "Pause" : "Play"}</button>
            <span className="font-mono tabular-nums text-[12px]">{fmt(playT)} <span className="text-txt-faint">/ {fmt(dur)}</span></span>
          </div>
        </div>
        <div className="flex-1 min-h-0 bg-black hairline-soft rounded grid place-items-center overflow-hidden">
          {finalExists ? (
            <video ref={videoRef} src={mediaUrl.finalVideo(slug)} className="max-w-full object-contain" style={{ height: "100%" }} playsInline
              onTimeUpdate={(e) => setPlayT((e.currentTarget as HTMLVideoElement).currentTime)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
          ) : <div className="text-txt-faint text-[12px] text-center px-3">No rendered video yet — run the episode (Assembly → Run) to enable the synced preview.</div>}
        </div>
      </section>

      {/* TIMELINE */}
      <section className="panel flex flex-col flex-none relative">
        <CollapseTab open={timelineOpen} onToggle={toggleTimeline} label="timeline" />
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">TIMELINE <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ drag assets from the drawer onto a track · scrub on the ruler · drag clips to move, edges to trim</span></div>
          <div className="flex items-center gap-2 text-[11px]">
            <span className="seg-readout">{shownOverlays.length} GFX · {shownBeds.length} ♫ · {shownSfx.length} ♪ · {total.toFixed(1)}s</span>
            <button className="btn p-1" title="zoom out" onClick={() => setPps((z) => Math.max(12, z - 12))}>−</button>
            <span className="text-txt-faint">{pps}px/s</span>
            <button className="btn p-1" title="zoom in" onClick={() => setPps((z) => Math.min(160, z + 12))}>+</button>
          </div>
        </header>
        {timelineOpen && (
        <div ref={scrollRef} className="overflow-x-auto overflow-y-hidden" onPointerMove={onMove} onPointerUp={endDrag} onPointerLeave={endDrag}>
          <div style={{ width }} className="select-none relative">
            {/* ruler — the only scrub surface */}
            <div className="relative h-5 border-b hairline-soft text-[10px] text-txt-faint cursor-pointer" onClick={(e) => seekTo(secFromClientX(e.clientX))} title="click to scrub">
              {ticks.map((t) => <div key={t} className="absolute top-0 h-full border-l border-[var(--line-soft)] pl-1" style={{ left: t * pps }}>{t}s</div>)}
            </div>

            {/* CUES — filmstrip, click to select */}
            <TrackLabel label="CUES" />
            <div className="relative h-16 border-b hairline-soft">
              {cueList.map((c) => {
                const left = (cum[c.id] ?? 0) * pps; const w = (c.duration_s ?? 0) * pps; const thumb = cueThumb(c);
                const active = selection?.t === "cue" && selection.cue.id === c.id;
                return (
                  <div key={c.id} onClick={() => setSelection({ t: "cue", cue: c })}
                    className="absolute top-0.5 rounded-sm overflow-hidden cursor-pointer hairline-soft"
                    style={{ left, width: Math.max(2, w), height: "calc(100% - 4px)", backgroundColor: "var(--bg-2)", backgroundImage: thumb ? `url(${thumb})` : undefined, backgroundRepeat: "repeat-x", backgroundSize: "auto 100%", outline: active ? "1px solid var(--amber)" : undefined }}
                    title={`${c.id} · ${c.speaker} — click for metadata`}>
                    <div className="absolute inset-x-0 bottom-0 px-1 text-[9px] leading-tight" style={{ background: "linear-gradient(transparent, rgba(0,0,0,0.85))" }}>
                      <span className="text-amber font-bold">{c.id}</span> <span className="text-txt-dim">{c.speaker}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* GRAPHICS — editable overlay bars */}
            <TrackLabel label="GRAPHICS" />
            <div className="relative h-12 border-b hairline-soft" onDragOver={(e) => e.preventDefault()} onDrop={onDropGraphics}>
              {shownOverlays.map((ov, idx) => {
                const { start, end } = overlayWindow(ov, cum); const left = start * pps; const w = Math.max(8, (end - start) * pps);
                const active = selection?.t === "overlay" && selection.idx === idx;
                return (
                  <div key={ov.id ?? idx} onPointerDown={(e) => beginDrag(e, "graphics", idx, "move", { start, end }, { t: "overlay", idx, ov })}
                    className={"absolute top-1 h-10 rounded-sm overflow-hidden cursor-grab flex items-center gap-1 px-1 " + (ov.mode === "overlay" ? "bg-[#0c3b44]" : "bg-[#3b2e0c]")}
                    style={{ left, width: w, outline: active ? "1px solid var(--amber)" : "1px solid var(--line-soft)", boxShadow: active ? "var(--glow-amber)" : undefined }} title={`${ov.asset} · ${ov.mode}`}>
                    <span onPointerDown={(e) => beginDrag(e, "graphics", idx, "l", { start, end }, { t: "overlay", idx, ov })} className="absolute left-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                    <video src={mediaUrl.titlePreview(slug, ov.asset)} muted loop autoPlay playsInline className="bg-black rounded pointer-events-none flex-none" style={{ width: 26, height: 26, objectFit: "contain" }} />
                    <span className="font-mono text-[10px] truncate pointer-events-none">{ov.asset}</span>
                    <span onPointerDown={(e) => beginDrag(e, "graphics", idx, "r", { start, end }, { t: "overlay", idx, ov })} className="absolute right-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                  </div>
                );
              })}
              {shownOverlays.length === 0 && <Empty label="drag a graphics card here" />}
            </div>

            {/* MUSIC — editable beds */}
            <TrackLabel label="MUSIC" />
            <div className="relative h-8 border-b hairline-soft" onDragOver={(e) => e.preventDefault()} onDrop={onDropMusic}>
              {shownBeds.map((b, idx) => {
                const { start, end } = bedWindow(b, cueList, cum); const left = start * pps; const w = Math.max(8, (end - start) * pps);
                const active = selection?.t === "bed" && selection.idx === idx;
                return (
                  <div key={idx} onPointerDown={(e) => beginDrag(e, "music", idx, "move", { start, end }, { t: "bed", idx, b })}
                    className="absolute top-0.5 h-7 rounded-sm overflow-hidden cursor-grab flex items-center gap-1 px-1 bg-[#2a1840]"
                    style={{ left, width: w, outline: active ? "1px solid var(--amber)" : "1px solid var(--line-soft)", boxShadow: active ? "var(--glow-amber)" : undefined }} title={`${b.name || b.file} bed`}>
                    <span onPointerDown={(e) => beginDrag(e, "music", idx, "l", { start, end }, { t: "bed", idx, b })} className="absolute left-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                    <span className="font-mono text-[10px] truncate pointer-events-none text-[#c7a3ff]">♫ {b.name || b.file}</span>
                    <span onPointerDown={(e) => beginDrag(e, "music", idx, "r", { start, end }, { t: "bed", idx, b })} className="absolute right-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                  </div>
                );
              })}
              {shownBeds.length === 0 && <Empty label="drag a music clip here" />}
            </div>

            {/* SFX — point markers, move only */}
            <TrackLabel label="SFX" />
            <div className="relative h-7" onDragOver={(e) => e.preventDefault()} onDrop={onDropSfx}>
              {shownSfx.map((e2, idx) => {
                const { start, end } = sfxWindow(e2, cueList, cum); const left = start * pps; const w = Math.max(10, (end - start) * pps);
                const active = selection?.t === "sfx" && selection.idx === idx;
                return (
                  <div key={idx} onPointerDown={(ev) => beginDrag(ev, "sfx", idx, "move", { start, end }, { t: "sfx", idx, e: e2 })}
                    className="absolute top-0.5 h-6 rounded-sm overflow-hidden cursor-grab flex items-center px-1 bg-[#0c3a3a]"
                    style={{ left, width: w, outline: active ? "1px solid var(--amber)" : "1px solid var(--line-soft)", boxShadow: active ? "var(--glow-amber)" : undefined }} title={`${e2.file} @ ${e2.cue}`}>
                    <span className="font-mono text-[10px] truncate pointer-events-none text-[#6fe0e0]">♪ {e2.file}</span>
                  </div>
                );
              })}
              {shownSfx.length === 0 && <Empty label="drag a sound effect here" />}
            </div>

            {/* playhead */}
            {playT > 0 && <div className="absolute top-0 bottom-0 pointer-events-none z-20" style={{ left: playT * pps, width: 2, background: "var(--cyan)", boxShadow: "0 0 6px var(--cyan)" }} />}
          </div>
        </div>
        )}
      </section>

      {/* DRAWER + METADATA (collapse together) */}
      <div className="relative flex-none" style={{ minHeight: bottomOpen ? 150 : 16 }}>
        <CollapseTab open={bottomOpen} onToggle={toggleBottom} label="drawer" />
        {bottomOpen && (
          <div className="grid grid-cols-[1fr_320px] gap-3 h-full" style={{ minHeight: 150, maxHeight: 220 }}>
            <div ref={drawerRef} className="min-h-0"><AssetDrawer slug={slug} onSelect={setSelection} removeActive={overDrawer} /></div>
            <MetadataPanel sel={selection} cb={cb} overlays={overlays} beds={beds} sfx={sfxList} />
          </div>
        )}
      </div>
    </div>
  );
}

function CollapseTab({ open, onToggle, label }: { open: boolean; onToggle: () => void; label: string }) {
  return (
    <button
      onClick={onToggle}
      title={(open ? "Collapse " : "Expand ") + label}
      className="absolute left-1/2 z-30 flex items-center justify-center"
      style={{
        transform: "translateX(-50%)", top: -8, width: 56, height: 15,
        background: "var(--amber)", color: "#1a1206", borderRadius: 5,
        fontSize: 11, fontWeight: 700, lineHeight: 1, boxShadow: "var(--glow-amber)",
      }}
    >
      {open ? "▼" : "▲"}
    </button>
  );
}

function TrackLabel({ label }: { label: string }) {
  return <div className="label-tiny px-2 pt-1 pb-0.5 text-txt-faint sticky left-0">{label}</div>;
}

function Empty({ label }: { label: string }) {
  return <div className="absolute inset-0 grid place-items-center text-txt-faint text-[11px] pointer-events-none">{label}</div>;
}
