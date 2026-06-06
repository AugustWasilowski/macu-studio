import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { EpisodeSummary, UI_STAGES, UIStage } from "../types";
import { IBrace, IChevron, IList, ITerminal } from "./Icons";
import { useStore } from "../store";
import { Page, TopPage, TOP_PAGES } from "../route";
import { gitsyncApi } from "../api/gitsync";
import { api } from "../api";
import { SysStat } from "./SysStat";
import { JobStatus } from "./JobStatus";

interface Props {
  episodes: EpisodeSummary[];
  slug: string;
  page: Page;
  stage: UIStage;
  onPick: (slug: string) => void;
  onStage: (stage: UIStage) => void;
  onPage: (page: TopPage) => void;
  onHome: () => void;
}

const TOP_PAGE_LABELS: Record<TopPage, string> = { youtube: "YouTube", docs: "Docs" };

function nowClock() {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function Topbar({ episodes, slug, page, stage, onPick, onStage, onPage, onHome }: Props) {
  const [clock, setClock] = useState(nowClock);
  const [open, setOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [stopping, setStopping] = useState(false);
  const qc = useQueryClient();
  const toggleDrawer = useStore((s) => s.toggleDrawer);
  const toggleLog = useStore((s) => s.toggleLog);
  const toggleTerminal = useStore((s) => s.toggleTerminal);
  const pushToast = useStore((s) => s.pushToast);

  async function onSync() {
    if (!slug || syncing) return;
    setSyncing(true);
    try {
      const r = await gitsyncApi.sync(slug);
      if (!r.ok) pushToast(`git sync failed: ${r.log.split("\n").pop() || ""}`, "err");
      else if (r.committed) pushToast(`synced ${slug} → ${r.commit}`, "ok");
      else pushToast(`${slug} already in sync`, "info");
      // refresh the picker's sync dots
      qc.invalidateQueries({ queryKey: ["episodes"] });
    } catch (e) {
      pushToast(`git sync error: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally {
      setSyncing(false);
    }
  }

  async function onStop() {
    if (stopping) return;
    if (!window.confirm("EMERGENCY STOP — kill the active render, clear the ComfyUI queue, and free GPU memory?")) return;
    setStopping(true);
    pushToast("emergency stop — killing render + freeing GPU…", "run");
    try {
      const r = await api.emergencyStop();
      pushToast("emergency stop complete — render killed, queue cleared, GPU freed", "ok");
      // surface the per-step detail in the activity log
      Object.entries(r.report).forEach(([k, v]) => pushToast(`${k}: ${v}`, v.startsWith("err") ? "err" : "info"));
      qc.invalidateQueries({ queryKey: ["pipeline"] });
    } catch (e) {
      pushToast(`emergency stop failed: ${e instanceof Error ? e.message : String(e)}`, "err");
    } finally {
      setStopping(false);
    }
  }

  useEffect(() => {
    const t = setInterval(() => setClock(nowClock()), 1000);
    return () => clearInterval(t);
  }, []);

  const cur = episodes.find((e) => e.slug === slug);
  const curIdx = episodes.findIndex((e) => e.slug === slug);
  const prevEp = curIdx > 0 ? episodes[curIdx - 1] : null;
  const nextEp = curIdx >= 0 && curIdx < episodes.length - 1 ? episodes[curIdx + 1] : null;

  return (
    <header
      className="flex items-center gap-4 px-3 h-[54px] border-b hairline shrink-0"
      style={{ background: "linear-gradient(180deg, #161513 0%, #0c0c0b 100%)" }}
    >
      <div className="flex items-center gap-2">
        <span className="led-dot pulse" style={{ "--led-c": "#ff4d4d" } as React.CSSProperties} />
        <button
          className="panel-title hover:brightness-125 cursor-pointer"
          onClick={onHome}
          title="Home — current episode (Assembly)"
        >
          MACU STUDIO
        </button>
        <span className="label-tiny pl-1">CH·245</span>
      </div>
      <button
        className="btn p-0.5"
        disabled={!prevEp}
        onClick={() => prevEp && onPick(prevEp.slug)}
        title={prevEp ? `Previous episode (${prevEp.slug})` : "No previous episode"}
      >
        <IChevron size={14} style={{ transform: "rotate(90deg)" }} />
      </button>
      <div className="relative">
        <button className="btn btn-amber" onClick={() => setOpen((o) => !o)}>
          <span style={{ color: "var(--amber)", fontWeight: 700 }}>{slug || "—"}</span>
          {cur?.se_label && <span className="seg-readout cyan text-[10px]">{cur.se_label}</span>}
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
                <span
                  className="flex-none rounded-full"
                  style={{
                    width: 8, height: 8,
                    background: e.synced === false ? "var(--red)" : "var(--green)",
                    boxShadow: `0 0 5px ${e.synced === false ? "var(--red)" : "var(--green)"}`,
                  }}
                  title={e.synced === false ? "Pending changes — not synced to git" : "Synced to git"}
                />
                <span className="text-amber font-bold w-12">{e.slug}</span>
                <span className="seg-readout cyan text-[10px] w-[52px] text-center">{e.se_label ?? ""}</span>
                <span className="flex-1 truncate text-txt-dim">{e.title}</span>
                <span className="seg-readout">{e.done_stages}/5</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <button
        className="btn p-0.5"
        disabled={!nextEp}
        onClick={() => nextEp && onPick(nextEp.slug)}
        title={nextEp ? `Next episode (${nextEp.slug})` : "No next episode"}
      >
        <IChevron size={14} style={{ transform: "rotate(-90deg)" }} />
      </button>
      <nav className="flex gap-1 ml-3">
        {UI_STAGES.map((s) => {
          const active = page === "stage" && s.key === stage;
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
        <span className="w-px self-stretch my-1 bg-[var(--line-soft)] mx-1" />
        {TOP_PAGES.map((p) => {
          const active = page === p;
          return (
            <button
              key={p}
              onClick={() => onPage(p)}
              className={"tab flex items-center gap-2 px-3 h-[32px] hairline-soft rounded-[3px] " + (active ? "active" : "")}
              style={active ? { borderColor: "var(--cyan)", boxShadow: "var(--glow-cyan)", color: "var(--cyan)" } : {}}
            >
              <span className="font-semibold tracking-wider uppercase text-[11px]">{TOP_PAGE_LABELS[p]}</span>
            </button>
          );
        })}
      </nav>
      <div className="ml-auto flex items-center gap-3">
        <button
          className="btn"
          onClick={onStop}
          disabled={stopping}
          title="Emergency stop: kill the active render, clear the ComfyUI queue, and free GPU memory"
          style={{ borderColor: "var(--red)", color: "var(--red)", boxShadow: "0 0 6px rgba(255,77,77,.35)" }}
        >
          <span className="font-semibold tracking-wider uppercase text-[11px]">{stopping ? "Stopping…" : "■ Stop"}</span>
        </button>
        <JobStatus />
        <SysStat />
        <button
          className="btn"
          onClick={onSync}
          disabled={syncing || !slug}
          title="Sync script + manifest + youtube.txt to git"
        >
          <span className="font-semibold tracking-wider uppercase text-[11px]">
            {syncing ? "Syncing…" : "Git sync"}
          </span>
        </button>
        <span className="seg-readout cyan">{clock}</span>
        <button className="btn" onClick={toggleTerminal} title="Open terminal (tmux into Max)">
          <ITerminal />
        </button>
        <button className="btn" onClick={toggleLog} title="Open activity log">
          <IList />
        </button>
        <button className="btn" onClick={toggleDrawer} title="Open manifest drawer">
          <IBrace />
        </button>
      </div>
    </header>
  );
}
