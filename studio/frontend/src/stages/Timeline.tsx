import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { graphicsApi } from "../api/graphics";
import { useStore } from "../store";
import { IX, IPlay, IPause } from "../components/Icons";
import { cueOffsets, overlayWindow, cueAtSecond, makeOverlay } from "./overlayTiming";
import type { Cue, Overlay, OverlayMode, OverlayPosition } from "../types";

const round2 = (n: number) => Math.round(n * 100) / 100;
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

const POSITIONS: OverlayPosition[] = ["lower_third", "bug_tl", "bug_tr", "center", "full"];

// Module-level drag payload for dropping a palette card onto the graphics track.
let paletteDrag: { asset: string } | null = null;

type DragState = { idx: number; kind: "move" | "l" | "r"; startX: number; origStart: number; origDur: number };

export function Timeline({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);

  const cues = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug), refetchInterval: 4000 });
  const manifest = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });
  const titles = useQuery({ queryKey: ["titles", slug], queryFn: () => api.titles(slug) });
  const finalQ = useQuery({ queryKey: ["final", slug], queryFn: () => api.final(slug) });

  const cueList = cues.data?.cues ?? [];
  const overlays: Overlay[] = useMemo(
    () => ((manifest.data as any)?.overlays as Overlay[]) ?? [],
    [manifest.data],
  );
  const beds: any[] = useMemo(() => ((manifest.data as any)?.music?.beds as any[]) ?? [], [manifest.data]);
  const { cum, total } = useMemo(() => cueOffsets(cueList), [cueList]);
  const cards = (titles.data?.titles ?? []).filter((t) => t.scope !== "hyperframes");

  const [pps, setPps] = useState(48); // px per second (zoom)
  const [selIdx, setSelIdx] = useState<number | null>(null);
  const [working, setWorking] = useState<Overlay[] | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // ---- preview monitor (the rendered final video) + playhead ----
  const finalExists = !!finalQ.data?.exists;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playT, setPlayT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const dur = finalQ.data?.duration_s ?? total;

  const seekTo = (sec: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = clamp(sec, 0, (v.duration || dur) - 0.05);
    v.play().catch(() => {});
  };
  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play().catch(() => {}); else v.pause();
  };

  // keep the playhead in view while playing
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !playing) return;
    const x = playT * pps;
    if (x < el.scrollLeft + 60 || x > el.scrollLeft + el.clientWidth - 60) {
      el.scrollLeft = Math.max(0, x - el.clientWidth / 3);
    }
  }, [playT, playing, pps]);

  const shown = working ?? overlays;

  const putOverlays = useMutation({
    mutationFn: (next: Overlay[]) => graphicsApi.putOverlays(slug, next),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }),
    onError: (e: Error) => push("overlays save failed: " + e.message, "err"),
  });
  const commit = (next: Overlay[]) => putOverlays.mutate(next);
  const patch = (idx: number, p: Partial<Overlay>) => commit(shown.map((o, i) => (i === idx ? { ...o, ...p } : o)));
  const remove = (idx: number) => { commit(shown.filter((_, i) => i !== idx)); setSelIdx(null); };

  // snap a second value to the nearest cue boundary if within ~7px
  const boundaries = useMemo(() => {
    const bs = cueList.map((c) => cum[c.id] ?? 0);
    bs.push(total);
    return bs;
  }, [cueList, cum, total]);
  const snap = (sec: number) => {
    const thr = 7 / pps;
    let best = sec, bestD = thr;
    for (const b of boundaries) { const d = Math.abs(sec - b); if (d < bestD) { best = b; bestD = d; } }
    return best;
  };

  const beginDrag = (e: React.PointerEvent, idx: number, kind: DragState["kind"]) => {
    e.stopPropagation();
    const ov = overlays[idx];
    const { start } = overlayWindow(ov, cum);
    dragRef.current = { idx, kind, startX: e.clientX, origStart: start, origDur: ov.duration ?? 0 };
    setWorking(overlays.map((o) => ({ ...o })));
    setSelIdx(idx);
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dxSec = (e.clientX - d.startX) / pps;
    setWorking((prev) => {
      const next = (prev ?? overlays).map((o) => ({ ...o }));
      const ov = next[d.idx];
      let start = d.origStart, dur2 = d.origDur;
      if (d.kind === "move") start = clamp(d.origStart + dxSec, 0, Math.max(0, total - dur2));
      else if (d.kind === "r") dur2 = Math.max(0.3, d.origDur + dxSec);
      else {
        const ns = clamp(d.origStart + dxSec, 0, d.origStart + d.origDur - 0.3);
        dur2 = d.origStart + d.origDur - ns;
        start = ns;
      }
      start = snap(start);
      const anchor = cueAtSecond(start, cueList, cum) ?? ov.anchor_cue;
      ov.anchor_cue = anchor;
      ov.start_offset = round2(start - (cum[anchor] ?? 0));
      ov.duration = round2(dur2);
      return next;
    });
  };
  const endDrag = () => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setWorking((w) => { if (w) commit(w); return null; });
  };

  const onTrackDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (!paletteDrag || !trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    const sec = clamp((e.clientX - rect.left) / pps, 0, Math.max(0, total));
    const anchor = cueAtSecond(sec, cueList, cum);
    if (!anchor) { push("no cues to anchor to", "err"); paletteDrag = null; return; }
    const ov = makeOverlay(paletteDrag.asset, anchor, 3);
    ov.start_offset = round2(sec - (cum[anchor] ?? 0));
    commit([...overlays, ov]);
    push(`${paletteDrag.asset} → graphic @ ${sec.toFixed(1)}s`, "ok");
    paletteDrag = null;
  };

  // first-shot thumbnail for a cue (filmstrip background). Only the animated shot
  // webps work as a CSS background-image — title cards are mp4 (skip them; the cue
  // just shows its label) so we don't fire doomed background-image requests.
  const cueThumb = (c: Cue): string | null => {
    for (const s of (c.shots || []) as any[]) {
      if ((s.kind === "character" || s.kind === "broll") && s.who) return mediaUrl.shotPreview(slug, s.who);
    }
    return null;
  };

  const width = Math.max(640, total * pps + 40);
  const sel = selIdx != null ? shown[selIdx] : null;

  const ticks: number[] = [];
  for (let t = 0; t <= total; t += 5) ticks.push(t);

  const secFromClientX = (clientX: number) => {
    const el = scrollRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    return clamp((clientX - rect.left + el.scrollLeft) / pps, 0, total);
  };

  return (
    <div className="flex flex-col gap-3 h-full min-h-0">
      {/* PREVIEW MONITOR — the rendered final video, click a cue to play from there */}
      <section className="panel flex items-stretch gap-3 p-2">
        <div className="bg-black hairline-soft rounded overflow-hidden grid place-items-center flex-none" style={{ width: 200, height: 200 }}>
          {finalExists ? (
            <video
              ref={videoRef}
              src={mediaUrl.finalVideo(slug)}
              className="w-full h-full object-contain"
              playsInline
              onTimeUpdate={(e) => setPlayT((e.currentTarget as HTMLVideoElement).currentTime)}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onEnded={() => setPlaying(false)}
            />
          ) : (
            <div className="text-txt-faint text-[11px] text-center px-2">No rendered video yet — run the episode to preview.</div>
          )}
        </div>
        <div className="flex flex-col justify-between flex-1 min-w-0">
          <div className="panel-title">PREVIEW <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ rendered output · click any cue to play from there</span></div>
          <div className="flex items-center gap-3">
            <button className="btn btn-cyan" disabled={!finalExists} onClick={togglePlay} title={playing ? "Pause" : "Play"}>
              {playing ? <IPause /> : <IPlay />} {playing ? "Pause" : "Play"}
            </button>
            <span className="font-mono tabular-nums text-[12px]">{fmt(playT)} <span className="text-txt-faint">/ {fmt(dur)}</span></span>
          </div>
          <div className="text-txt-faint text-[11px]">
            {finalExists
              ? "Preview is the last rendered cut — overlay edits show after a re-render."
              : "Render the episode (Assembly → Run) to enable the synced preview."}
          </div>
        </div>
      </section>

      <section className="panel flex flex-col min-h-0 flex-1">
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">TIMELINE <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ drag a card onto the graphics track · click a cue to play · drag/resize bars to retime</span></div>
          <div className="flex items-center gap-2 text-[11px]">
            <span className="seg-readout">{overlays.length} GFX · {total.toFixed(1)}s</span>
            <button className="btn p-1" title="zoom out" onClick={() => setPps((z) => Math.max(12, z - 12))}>−</button>
            <span className="text-txt-faint">{pps}px/s</span>
            <button className="btn p-1" title="zoom in" onClick={() => setPps((z) => Math.min(160, z + 12))}>+</button>
          </div>
        </header>

        <div
          ref={scrollRef}
          className="overflow-x-auto overflow-y-hidden flex-1"
          onPointerMove={onMove}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        >
          <div style={{ width }} className="select-none relative">
            {/* ruler (click to seek) */}
            <div
              className="relative h-5 border-b hairline-soft text-[10px] text-txt-faint cursor-pointer"
              onClick={(e) => seekTo(secFromClientX(e.clientX))}
              title="click to scrub"
            >
              {ticks.map((t) => (
                <div key={t} className="absolute top-0 h-full border-l border-[var(--line-soft)] pl-1" style={{ left: t * pps }}>{t}s</div>
              ))}
            </div>

            {/* cues track — filmstrip thumbnails, click to play */}
            <TrackLabelRow label="CUES" />
            <div className="relative h-16 border-b hairline-soft">
              {cueList.map((c) => {
                const left = (cum[c.id] ?? 0) * pps;
                const w = (c.duration_s ?? 0) * pps;
                const thumb = cueThumb(c);
                return (
                  <div
                    key={c.id}
                    onClick={() => seekTo(cum[c.id] ?? 0)}
                    className="absolute top-0.5 rounded-sm overflow-hidden cursor-pointer hairline-soft"
                    style={{
                      left, width: Math.max(2, w), height: "calc(100% - 4px)",
                      backgroundColor: "var(--bg-2)",
                      backgroundImage: thumb ? `url(${thumb})` : undefined,
                      backgroundRepeat: "repeat-x",
                      backgroundSize: "auto 100%",
                    }}
                    title={`${c.id} · ${c.speaker} — click to play from ${fmt(cum[c.id] ?? 0)}`}
                  >
                    <div className="absolute inset-x-0 bottom-0 px-1 text-[9px] leading-tight"
                      style={{ background: "linear-gradient(transparent, rgba(0,0,0,0.85))" }}>
                      <span className="text-amber font-bold">{c.id}</span> <span className="text-txt-dim">{c.speaker}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* graphics track (editable) */}
            <TrackLabelRow label="GRAPHICS" />
            <div
              ref={trackRef}
              className="relative h-12 border-b hairline-soft"
              onDragOver={(e) => e.preventDefault()}
              onDrop={onTrackDrop}
            >
              {shown.map((ov, idx) => {
                const { start } = overlayWindow(ov, cum);
                const left = start * pps;
                const w = Math.max(8, (ov.duration ?? 0) * pps);
                const active = selIdx === idx;
                return (
                  <div
                    key={ov.id ?? idx}
                    onPointerDown={(e) => beginDrag(e, idx, "move")}
                    onClick={() => setSelIdx(idx)}
                    className={"absolute top-1 h-10 rounded-sm overflow-hidden cursor-grab flex items-center gap-1 px-1 " + (ov.mode === "overlay" ? "bg-[#0c3b44]" : "bg-[#3b2e0c]")}
                    style={{ left, width: w, outline: active ? "1px solid var(--amber)" : "1px solid var(--line-soft)", boxShadow: active ? "var(--glow-amber)" : undefined }}
                    title={`${ov.asset} · ${ov.mode} · ${(ov.duration ?? 0).toFixed(1)}s`}
                  >
                    <span onPointerDown={(e) => beginDrag(e, idx, "l")} className="absolute left-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                    <video src={mediaUrl.titlePreview(slug, ov.asset)} muted loop autoPlay playsInline
                      className="bg-black rounded pointer-events-none flex-none" style={{ width: 26, height: 26, objectFit: "contain" }} />
                    <span className="font-mono text-[10px] truncate pointer-events-none">{ov.asset}</span>
                    <span onPointerDown={(e) => beginDrag(e, idx, "r")} className="absolute right-0 top-0 h-full w-1.5 cursor-ew-resize bg-[var(--amber)]/40" />
                  </div>
                );
              })}
              {shown.length === 0 && (
                <div className="absolute inset-0 grid place-items-center text-txt-faint text-[11px] pointer-events-none">
                  drag a title card here to place a graphic
                </div>
              )}
            </div>

            {/* music beds track (read-only context) */}
            {beds.length > 0 && (
              <>
                <TrackLabelRow label="MUSIC" />
                <div className="relative h-7">
                  {beds.map((b, i) => {
                    const refs: string[] = Array.isArray(b.cues) ? b.cues : [];
                    if (!refs.length) return null;
                    const first = refs[0], last = refs[refs.length - 1];
                    const start = cum[first] ?? 0;
                    const lc = cueList.find((c) => c.id === last);
                    const end = (cum[last] ?? start) + (lc?.duration_s ?? 0);
                    return (
                      <div key={i} className="absolute top-0.5 h-6 rounded-sm bg-[#2a1840] hairline-soft text-[10px] px-1 truncate"
                        style={{ left: start * pps, width: Math.max(4, (end - start) * pps) }} title={`${b.name} bed`}>
                        ♪ {b.name}
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* playhead */}
            {playT > 0 && (
              <div className="absolute top-0 bottom-0 pointer-events-none z-20"
                style={{ left: playT * pps, width: 2, background: "var(--cyan)", boxShadow: "0 0 6px var(--cyan)" }} />
            )}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-[1fr_320px] gap-3" style={{ minHeight: 120 }}>
        {/* palette strip */}
        <section className="panel flex flex-col min-h-0">
          <header className="px-3 py-2 border-b hairline panel-title">CARDS <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ drag onto the graphics track</span></header>
          <div className="p-2 flex gap-2 overflow-x-auto">
            {cards.map((t) => (
              <div key={t.key} draggable onDragStart={() => { paletteDrag = { asset: t.key }; }}
                className="flex-none hairline-soft rounded overflow-hidden cursor-grab" style={{ width: 90 }} title={`drag ${t.key} onto the track`}>
                <div className="bg-black grid place-items-center" style={{ aspectRatio: "1/1" }}>
                  {t.exists ? (
                    <video src={mediaUrl.titlePreview(slug, t.key)} muted loop autoPlay playsInline className="w-full h-full object-contain pointer-events-none" />
                  ) : <span className="label-tiny p-1 text-center">{t.key}</span>}
                </div>
                <div className="px-1 py-0.5 bg-bg-2 font-mono text-[10px] truncate">{t.key}</div>
              </div>
            ))}
            {cards.length === 0 && <div className="text-txt-faint text-[12px] p-2">No title cards yet — make them on the Graphics page.</div>}
          </div>
        </section>

        {/* selected-overlay inspector */}
        <section className="panel p-3 flex flex-col gap-2 overflow-y-auto">
          <div className="panel-title">GRAPHIC</div>
          {sel ? (
            <>
              <div className="flex items-center gap-2">
                <video src={mediaUrl.titlePreview(slug, sel.asset)} muted loop autoPlay playsInline className="bg-black rounded" style={{ width: 40, height: 40, objectFit: "contain" }} />
                <span className="font-mono text-[12px] flex-1 truncate">{sel.asset}</span>
                <button className="btn p-1" title="delete" onClick={() => remove(selIdx!)}><IX /></button>
              </div>
              <label className="flex items-center justify-between text-[12px]">
                <span className="label-tiny">mode</span>
                <select className="input text-[12px] py-0.5" value={sel.mode}
                  onChange={(e) => patch(selIdx!, { mode: e.target.value as OverlayMode })}>
                  <option value="insert">insert (full-frame)</option>
                  <option value="overlay">overlay (on footage)</option>
                </select>
              </label>
              {sel.mode === "overlay" && (
                <>
                  <label className="flex items-center justify-between text-[12px]">
                    <span className="label-tiny">position</span>
                    <select className="input text-[12px] py-0.5" value={sel.position ?? "lower_third"}
                      onChange={(e) => patch(selIdx!, { position: e.target.value as OverlayPosition })}>
                      {POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </label>
                  <NumRow label="scale" value={sel.scale ?? 1} step={0.05} onChange={(v) => patch(selIdx!, { scale: v })} />
                  <NumRow label="opacity" value={sel.opacity ?? 1} step={0.05} onChange={(v) => patch(selIdx!, { opacity: v })} />
                </>
              )}
              <NumRow label="fade in" value={sel.fade_in ?? 0} step={0.1} onChange={(v) => patch(selIdx!, { fade_in: v })} />
              <NumRow label="fade out" value={sel.fade_out ?? 0} step={0.1} onChange={(v) => patch(selIdx!, { fade_out: v })} />
              <div className="grid grid-cols-2 gap-1 text-[11px] text-txt-faint mt-1">
                <span>anchor</span><span className="text-amber font-mono">{sel.anchor_cue}</span>
                <span>start +s</span><span className="font-mono">{(sel.start_offset ?? 0).toFixed(2)}</span>
                <span>duration</span><span className="font-mono">{(sel.duration ?? 0).toFixed(2)}s</span>
              </div>
            </>
          ) : (
            <div className="text-txt-faint text-[12px]">Select a graphic bar to edit it.</div>
          )}
        </section>
      </div>
    </div>
  );
}

function TrackLabelRow({ label }: { label: string }) {
  return <div className="label-tiny px-2 pt-1 pb-0.5 text-txt-faint sticky left-0">{label}</div>;
}

function NumRow({ label, value, step, onChange }: { label: string; value: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="flex items-center justify-between text-[12px]">
      <span className="label-tiny">{label}</span>
      <input className="input w-24 text-[12px] py-0.5" type="number" step={step} value={value}
        onChange={(e) => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) onChange(Math.round(v * 100) / 100); }} />
    </label>
  );
}
