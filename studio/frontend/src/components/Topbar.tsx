import { useEffect, useState } from "react";
import { EpisodeSummary, UI_STAGES, UIStage } from "../types";
import { IBrace, IChevron } from "./Icons";
import { useStore } from "../store";

interface Props {
  episodes: EpisodeSummary[];
  slug: string;
  stage: UIStage;
  onPick: (slug: string) => void;
  onStage: (stage: UIStage) => void;
}

function nowClock() {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function Topbar({ episodes, slug, stage, onPick, onStage }: Props) {
  const [clock, setClock] = useState(nowClock);
  const [open, setOpen] = useState(false);
  const toggleDrawer = useStore((s) => s.toggleDrawer);

  useEffect(() => {
    const t = setInterval(() => setClock(nowClock()), 1000);
    return () => clearInterval(t);
  }, []);

  const cur = episodes.find((e) => e.slug === slug);

  return (
    <header
      className="flex items-center gap-4 px-3 h-[54px] border-b hairline shrink-0"
      style={{ background: "linear-gradient(180deg, #161513 0%, #0c0c0b 100%)" }}
    >
      <div className="flex items-center gap-2">
        <span className="led-dot pulse" style={{ "--led-c": "#ff4d4d" } as React.CSSProperties} />
        <span className="panel-title">MACU STUDIO</span>
        <span className="label-tiny pl-1">CH·245</span>
      </div>
      <div className="relative">
        <button className="btn btn-amber" onClick={() => setOpen((o) => !o)}>
          <span style={{ color: "var(--amber)", fontWeight: 700 }}>{slug || "—"}</span>
          <span className="text-txt-dim">{cur ? cur.title.replace(/^The MACU Report\s*—\s*/, "") : ""}</span>
          <IChevron />
        </button>
        {open && (
          <div className="absolute top-[36px] left-0 z-50 panel w-[420px] max-h-[400px] overflow-y-auto">
            {episodes.map((e) => (
              <button
                key={e.slug}
                className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-bg-3"
                onClick={() => { setOpen(false); onPick(e.slug); }}
              >
                <span className="text-amber font-bold w-12">{e.slug}</span>
                <span className="flex-1 truncate text-txt-dim">{e.title}</span>
                <span className="seg-readout">{e.done_stages}/5</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <nav className="flex gap-1 ml-3">
        {UI_STAGES.map((s) => {
          const active = s.key === stage;
          const done = cur ? cur.done_stages >= s.n : false;
          return (
            <button
              key={s.key}
              onClick={() => onStage(s.key)}
              className={"tab flex items-center gap-2 px-3 h-[32px] hairline-soft rounded-[3px] " + (active ? "active" : "")}
              style={active ? { borderColor: "var(--amber)", boxShadow: "var(--glow-amber)", color: "var(--amber)" } : {}}
            >
              <span className={`tab-num ${done ? "done" : ""}`}>{done ? "✓" : s.n}</span>
              <span className="font-semibold tracking-wider uppercase text-[11px]">{s.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="ml-auto flex items-center gap-3">
        <span className="seg-readout cyan">{clock}</span>
        <button className="btn" onClick={toggleDrawer} title="Open manifest drawer">
          <IBrace />
        </button>
      </div>
    </header>
  );
}
