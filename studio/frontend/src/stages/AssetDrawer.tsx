import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { libraryApi } from "../api/library";
import { PlayBtn } from "../components/PlayBtn";
import { usePreview } from "./AudioSfx";
import { drawerDrag } from "./trackEditor";
import type { Selection } from "./trackEditor";

type Tab = "music" | "sfx" | "card";
const TABS: [Tab, string][] = [["music", "MUSIC"], ["sfx", "SFX"], ["card", "GRAPHICS CARDS"]];

/** The bottom asset drawer: tabbed Music / SFX / Graphics-card lists. Rows are
 * draggable onto their matching timeline track (sets the module-level drawerDrag),
 * and clicking a row selects it (drives the metadata panel). `removeActive` shows a
 * "remove from timeline" overlay while a timeline clip is being dragged down here. */
export function AssetDrawer({ slug, onSelect, removeActive }: {
  slug: string;
  onSelect: (s: Selection) => void;
  removeActive?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("music");
  const [filter, setFilter] = useState("");
  const preview = usePreview();

  const music = useQuery({ queryKey: ["assets", "music"], queryFn: () => libraryApi.list("music"), enabled: tab === "music" });
  const sfx = useQuery({ queryKey: ["assets", "sfx"], queryFn: () => libraryApi.list("sfx"), enabled: tab === "sfx" });
  const titles = useQuery({ queryKey: ["titles", slug], queryFn: () => api.titles(slug), enabled: tab === "card" });

  const fq = filter.trim().toLowerCase();
  const audioItems = (tab === "music" ? music.data : sfx.data) ?? [];
  const shownAudio = fq ? audioItems.filter((a) => a.file.toLowerCase().includes(fq) || (a.notes ?? "").toLowerCase().includes(fq)) : audioItems;
  const cards = (titles.data?.titles ?? []).filter((t) => t.scope !== "hyperframes");
  const shownCards = fq ? cards.filter((c) => c.key.toLowerCase().includes(fq)) : cards;

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
        <input className="input text-[11px] w-40" placeholder="filter…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </header>

      <div className="overflow-y-auto flex-1 p-2">
        {tab === "card" ? (
          <div className="flex gap-2 flex-wrap">
            {shownCards.map((t) => (
              <div key={t.key} draggable
                onDragStart={() => drawerDrag.set({ kind: "card", asset: t.key })}
                onDragEnd={() => drawerDrag.clear()}
                onClick={() => onSelect({ t: "lib", kind: "card", item: { file: t.key, duration_s: null } })}
                className="flex-none hairline-soft rounded overflow-hidden cursor-grab" style={{ width: 84 }} title={`drag ${t.key} onto the GRAPHICS track`}>
                <div className="bg-black grid place-items-center" style={{ aspectRatio: "1/1" }}>
                  {t.exists ? (
                    <video src={mediaUrl.titlePreview(slug, t.key)} muted loop autoPlay playsInline className="w-full h-full object-contain pointer-events-none" />
                  ) : <span className="label-tiny p-1 text-center">{t.key}</span>}
                </div>
                <div className="px-1 py-0.5 bg-bg-2 font-mono text-[10px] truncate">{t.key}</div>
              </div>
            ))}
            {shownCards.length === 0 && <div className="text-txt-faint text-[12px] p-1">No title cards.</div>}
          </div>
        ) : (
          <div className="flex flex-col gap-0.5 text-[12px]">
            {shownAudio.map((a) => {
              const url = libraryApi.audioUrl(tab as "music" | "sfx", a.file);
              return (
                <div key={a.file} draggable
                  onDragStart={() => drawerDrag.set(tab === "music" ? { kind: "music", file: a.file } : { kind: "sfx", file: a.file })}
                  onDragEnd={() => drawerDrag.clear()}
                  onClick={() => onSelect({ t: "lib", kind: tab as "music" | "sfx", item: a })}
                  className="flex items-center gap-1.5 py-0.5 px-1 hover:bg-bg-3 rounded cursor-grab"
                  title={`drag ${a.file} onto the ${tab === "music" ? "MUSIC" : "SFX"} track`}>
                  <span onClick={(e) => e.stopPropagation()}><PlayBtn playing={preview.previewUrl === url} onClick={() => preview.toggle(url)} /></span>
                  <span className="font-mono flex-1 truncate" title={a.file}>{a.file}</span>
                  <span className="text-txt-faint text-[10px]">{a.duration_s != null ? `${a.duration_s}s` : ""}</span>
                  <span className="text-txt-faint text-[10px]">⠿</span>
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
