import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { libraryApi } from "../api/library";
import { versionsApi } from "../api/assets";
import { PlayBtn } from "../components/PlayBtn";
import { usePreview } from "./AudioSfx";
import { drawerDrag } from "./trackEditor";
import type { Selection } from "./trackEditor";

type Tab = "shots" | "vo" | "music" | "sfx" | "card";
const TABS: [Tab, string][] = [
  ["shots", "SHOTS"], ["vo", "VO"], ["music", "MUSIC"], ["sfx", "SFX"], ["card", "GRAPHICS CARDS"],
];

/** The bottom asset drawer: tabbed Music / SFX / Graphics-card lists. Rows are
 * draggable onto their matching timeline track (sets the module-level drawerDrag),
 * and clicking a row selects it (drives the metadata panel). `removeActive` shows a
 * "remove from timeline" overlay while a timeline clip is being dragged down here. */
export function AssetDrawer({ slug, onSelect, removeActive }: {
  slug: string;
  onSelect: (s: Selection) => void;
  removeActive?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("shots");
  const [filter, setFilter] = useState("");
  // "All episodes" pulls shots/VO/cards from the whole corpus (SFX/music are already
  // shared, so the toggle doesn't affect them). Persisted per-device.
  const [allEp, setAllEp] = useState(() => localStorage.getItem("macu.drawer.allEp") === "1");
  const toggleAllEp = () => setAllEp((v) => { localStorage.setItem("macu.drawer.allEp", v ? "0" : "1"); return !v; });
  // "Alternates" adds the non-live archived takes of each shot (SHOTS tab only).
  const [altOn, setAltOn] = useState(() => localStorage.getItem("macu.drawer.alt") === "1");
  const toggleAlt = () => setAltOn((v) => { localStorage.setItem("macu.drawer.alt", v ? "0" : "1"); return !v; });
  // Asset-tile size (px), persisted; +/- in the header (mirrors the script-page text size).
  const [tileW, setTileW] = useState(() => {
    const v = Number(localStorage.getItem("macu.drawer.tileW"));
    return v >= 56 && v <= 200 ? v : 84;
  });
  const bumpTile = (d: number) => setTileW((p) => {
    const n = Math.max(56, Math.min(200, p + d));
    localStorage.setItem("macu.drawer.tileW", String(n));
    return n;
  });
  const preview = usePreview();

  const music = useQuery({ queryKey: ["assets", "music"], queryFn: () => libraryApi.list("music"), enabled: tab === "music" });
  const sfx = useQuery({ queryKey: ["assets", "sfx"], queryFn: () => libraryApi.list("sfx"), enabled: tab === "sfx" });
  // Per-episode (default) vs. whole-corpus sources for the episode-scoped tabs.
  const titles = useQuery({ queryKey: ["titles", slug], queryFn: () => api.titles(slug), enabled: tab === "card" && !allEp });
  const shotsQ = useQuery({ queryKey: ["shots", slug], queryFn: () => api.shots(slug), enabled: tab === "shots" && !allEp });
  const cuesQ = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug), enabled: tab === "vo" && !allEp });
  const corpusShots = useQuery({ queryKey: ["corpus", "shots"], queryFn: () => versionsApi.corpus("shots"), enabled: tab === "shots" && allEp });
  const corpusTitles = useQuery({ queryKey: ["corpus", "titles"], queryFn: () => versionsApi.corpus("titles"), enabled: tab === "card" && allEp });
  const corpusCues = useQuery({ queryKey: ["corpus", "cues"], queryFn: () => versionsApi.corpus("cues"), enabled: tab === "vo" && allEp });
  const altQ = useQuery({
    queryKey: ["corpus", "alternates", allEp ? "*" : slug],
    queryFn: () => versionsApi.corpusAlternates(allEp ? undefined : slug),
    enabled: tab === "shots" && altOn,
  });

  const fq = filter.trim().toLowerCase();
  const audioItems = (tab === "music" ? music.data : sfx.data) ?? [];
  const shownAudio = fq ? audioItems.filter((a) => a.file.toLowerCase().includes(fq) || (a.notes ?? "").toLowerCase().includes(fq)) : audioItems;
  const cards = ((allEp ? corpusTitles.data?.titles : titles.data?.titles) ?? []).filter((t: any) => t.scope !== "hyperframes");
  const shownCards = fq ? cards.filter((c: any) => c.key.toLowerCase().includes(fq) || (c.slug ?? "").toLowerCase().includes(fq)) : cards;
  const shots = ((allEp ? corpusShots.data?.shots : shotsQ.data?.shots) ?? []) as any[];
  const shownShots = fq ? shots.filter((s) => s.key.toLowerCase().includes(fq) || (s.prompt ?? "").toLowerCase().includes(fq) || (s.slug ?? "").toLowerCase().includes(fq)) : shots;
  const alts = (altOn ? (altQ.data?.alternates ?? []) : []) as any[];
  const shownAlts = fq ? alts.filter((a) => a.key.toLowerCase().includes(fq) || (a.slug ?? "").toLowerCase().includes(fq)) : alts;
  const voCues = ((allEp ? corpusCues.data?.cues : cuesQ.data?.cues) ?? []) as any[];
  const shownVo = fq ? voCues.filter((c) => c.id.toLowerCase().includes(fq) || (c.speaker ?? "").toLowerCase().includes(fq) || (c.slug ?? "").toLowerCase().includes(fq)) : voCues;

  return (
    <section className="panel flex flex-col min-h-0 relative">
      <header className="flex items-center justify-between px-3 py-2 border-b hairline">
        <div className="flex gap-1">
          {TABS.map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              className={"tab px-2 h-[24px] hairline-soft rounded-[3px] text-[10px] uppercase tracking-wider " + (tab === k ? "active" : "")}
              style={tab === k ? { borderColor: "var(--cyan)", boxShadow: "var(--glow-cyan)", color: "var(--cyan)" } : {}}>
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-0.5 mr-1" title="Asset tile size">
            <button className="btn px-1.5 py-0.5" onClick={() => bumpTile(-12)}>−</button>
            <span className="text-txt-faint text-[10px] w-6 text-center tabular-nums">{tileW}</span>
            <button className="btn px-1.5 py-0.5" onClick={() => bumpTile(12)}>+</button>
          </span>
          <label className="flex items-center gap-1 text-[10px] text-txt-dim cursor-pointer select-none uppercase tracking-wider"
            title="Shots / VO / cards: show assets from EVERY episode (not just this one). SFX & music are always shared.">
            <input type="checkbox" checked={allEp} onChange={toggleAllEp} />
            All eps
          </label>
          <label className="flex items-center gap-1 text-[10px] text-txt-dim cursor-pointer select-none uppercase tracking-wider"
            title="SHOTS tab: also list the non-live takes (earlier generations) of each shot. Drag one in to use that take.">
            <input type="checkbox" checked={altOn} onChange={toggleAlt} />
            Alts
          </label>
          <input className="input text-[11px] w-40" placeholder="filter…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
      </header>

      <div className="overflow-y-auto flex-1 p-2">
        {tab === "shots" ? (
          <div className="flex gap-2 flex-wrap">
            {shownShots.map((s) => {
              const shotKind = s.kind === "broll" ? "broll" : "character";
              const src = s.slug ?? slug;
              const foreign = !!s.slug && s.slug !== slug;
              return (
                <div key={`${src}/${s.kind}/${s.key}`} draggable
                  onDragStart={() => drawerDrag.set({ kind: "shot", key: s.key, shotKind, slug: s.slug })}
                  onDragEnd={() => drawerDrag.clear()}
                  className="flex-none hairline-soft rounded overflow-hidden cursor-grab" style={{ width: tileW }}
                  title={`drag ${s.key} onto a cue in the SHOTS track${foreign ? ` (imports from ${s.slug})` : ""}`}>
                  <div className="bg-black grid place-items-center relative" style={{ aspectRatio: "1/1" }}>
                    {s.webp_exists ? (
                      <img src={mediaUrl.shotPreview(src, s.key, s.webp_mtime)} alt={s.key} className="w-full h-full object-contain pointer-events-none" />
                    ) : <span className="label-tiny p-1 text-center">{s.key}</span>}
                    {foreign && <span className="absolute top-0.5 left-0.5 text-[9px] font-mono px-1 rounded bg-amber text-black">{s.slug}</span>}
                  </div>
                  <div className="px-1 py-0.5 bg-bg-2 font-mono text-[10px] truncate" title={s.key}>{s.key}</div>
                </div>
              );
            })}
            {shownAlts.map((a) => {
              const shotKind = a.kind === "broll" ? "broll" : "character";
              const foreign = a.slug !== slug;
              return (
                <div key={`alt/${a.slug}/${a.kind}/${a.key}/v${a.v}`} draggable
                  onDragStart={() => drawerDrag.set({ kind: "shot", key: a.key, shotKind, slug: a.slug, version: a.v })}
                  onDragEnd={() => drawerDrag.clear()}
                  className="flex-none hairline-soft rounded overflow-hidden cursor-grab" style={{ width: tileW }}
                  title={`${a.key} — take v${a.v}${foreign ? ` from ${a.slug}` : ""}${a.seed != null ? ` (seed ${a.seed})` : ""} · drag onto a cue to use this take`}>
                  <div className="bg-black grid place-items-center relative" style={{ aspectRatio: "1/1" }}>
                    <img src={versionsApi.mediaUrl(a.slug, "shot", a.key, a.v)} alt={a.key} className="w-full h-full object-contain pointer-events-none" />
                    <span className="absolute top-0.5 right-0.5 text-[9px] font-mono px-1 rounded bg-cyan text-black">v{a.v}</span>
                    {foreign && <span className="absolute top-0.5 left-0.5 text-[9px] font-mono px-1 rounded bg-amber text-black">{a.slug}</span>}
                  </div>
                  <div className="px-1 py-0.5 bg-bg-2 font-mono text-[10px] truncate" title={a.key}>{a.key}</div>
                </div>
              );
            })}
            {shownShots.length === 0 && shownAlts.length === 0 && <div className="text-txt-faint text-[12px] p-1">No shots — add them on the Video tab.</div>}
          </div>
        ) : tab === "vo" ? (
          <div className="flex gap-2 flex-wrap">
            {shownVo.map((c) => {
              const src = c.slug ?? slug;
              const foreign = !!c.slug && c.slug !== slug;
              const url = mediaUrl.cueAudio(src, c.id, c.wav_mtime);
              const playing = preview.previewUrl === url;
              return (
                <div key={`${src}/${c.id}`}
                  onClick={() => c.wav_exists && preview.toggle(url)}
                  className={"flex-none hairline-soft rounded overflow-hidden " + (c.wav_exists ? "cursor-pointer hover:border-cyan" : "")}
                  style={{ width: tileW, opacity: c.wav_exists ? 1 : 0.45 }}
                  title={`${c.id} · ${c.speaker}${foreign ? ` · ${c.slug}` : ""}\n${c.text || "(no script text)"}${c.wav_exists ? "" : "\n(no VO wav yet)"}`}>
                  <div className="bg-black grid place-items-center relative" style={{ aspectRatio: "1/1" }}>
                    <span className="font-mono text-cyan text-[14px]">{c.id}</span>
                    <span className="absolute bottom-1 right-1 pointer-events-none"><PlayBtn playing={playing} onClick={() => {}} /></span>
                    {foreign && <span className="absolute top-0.5 left-0.5 text-[9px] font-mono px-1 rounded bg-amber text-black">{c.slug}</span>}
                  </div>
                  <div className="px-1 py-0.5 bg-bg-2 flex items-center justify-between gap-1">
                    <span className="text-[10px] truncate" title={c.speaker}>{c.speaker}</span>
                    <span className="text-txt-faint text-[10px] flex-none">{c.duration_s != null ? `${c.duration_s.toFixed(1)}s` : ""}</span>
                  </div>
                </div>
              );
            })}
            {shownVo.length === 0 && <div className="text-txt-faint text-[12px] p-1">No cues yet.</div>}
          </div>
        ) : tab === "card" ? (
          <div className="flex gap-2 flex-wrap">
            {shownCards.map((t: any) => {
              const src = t.slug ?? slug;
              const foreign = !!t.slug && t.slug !== slug;
              return (
                <div key={`${src}/${t.key}`} draggable
                  onDragStart={() => drawerDrag.set({ kind: "card", asset: t.key, slug: t.slug })}
                  onDragEnd={() => drawerDrag.clear()}
                  onClick={() => onSelect({ t: "lib", kind: "card", item: { file: t.key, duration_s: null } })}
                  className="flex-none hairline-soft rounded overflow-hidden cursor-grab" style={{ width: tileW }}
                  title={`drag ${t.key} onto the GRAPHICS track${foreign ? ` (imports from ${t.slug})` : ""}`}>
                  <div className="bg-black grid place-items-center relative" style={{ aspectRatio: "1/1" }}>
                    {t.exists ? (
                      <video src={mediaUrl.titlePreview(src, t.key)} muted loop autoPlay playsInline className="w-full h-full object-contain pointer-events-none" />
                    ) : <span className="label-tiny p-1 text-center">{t.key}</span>}
                    {foreign && <span className="absolute top-0.5 left-0.5 text-[9px] font-mono px-1 rounded bg-amber text-black">{t.slug}</span>}
                  </div>
                  <div className="px-1 py-0.5 bg-bg-2 font-mono text-[10px] truncate">{t.key}</div>
                </div>
              );
            })}
            {shownCards.length === 0 && <div className="text-txt-faint text-[12px] p-1">No title cards.</div>}
          </div>
        ) : (
          <div className="flex gap-2 flex-wrap">
            {shownAudio.map((a) => {
              const url = libraryApi.audioUrl(tab as "music" | "sfx", a.file);
              const isMusic = tab === "music";
              return (
                <div key={a.file} draggable
                  onDragStart={() => drawerDrag.set(isMusic ? { kind: "music", file: a.file } : { kind: "sfx", file: a.file })}
                  onDragEnd={() => drawerDrag.clear()}
                  onClick={() => onSelect({ t: "lib", kind: tab as "music" | "sfx", item: a })}
                  className="flex-none hairline-soft rounded overflow-hidden cursor-grab hover:border-cyan" style={{ width: tileW }}
                  title={`drag ${a.file} onto the ${isMusic ? "MUSIC" : "SFX"} track · click for info`}>
                  <div className="bg-black grid place-items-center relative" style={{ aspectRatio: "1/1" }}>
                    <span className="text-2xl" style={{ color: isMusic ? "#c7a3ff" : "#6fe0e0" }}>{isMusic ? "♫" : "♪"}</span>
                    <span className="absolute bottom-1 right-1" onClick={(e) => e.stopPropagation()}>
                      <PlayBtn playing={preview.previewUrl === url} onClick={() => preview.toggle(url)} />
                    </span>
                  </div>
                  <div className="px-1 py-0.5 bg-bg-2 flex items-center justify-between gap-1">
                    <span className="font-mono text-[10px] truncate" title={a.file}>{a.file}</span>
                    <span className="text-txt-faint text-[10px] flex-none">{a.duration_s != null ? `${a.duration_s}s` : ""}</span>
                  </div>
                </div>
              );
            })}
            {shownAudio.length === 0 && <div className="text-txt-faint text-[12px] p-1">No {tab} assets.</div>}
          </div>
        )}
      </div>

      {removeActive && (
        <div className="absolute inset-0 z-30 grid place-items-center pointer-events-none"
          style={{ background: "rgba(255,77,77,0.12)", outline: "2px dashed var(--red)", outlineOffset: -4 }}>
          <span className="text-[13px] font-semibold tracking-wider uppercase" style={{ color: "var(--red)" }}>Drop to remove from timeline</span>
        </div>
      )}
    </section>
  );
}
