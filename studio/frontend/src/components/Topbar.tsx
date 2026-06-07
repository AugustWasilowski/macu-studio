import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { EpisodeSummary, UI_STAGES, UIStage } from "../types";
import { IBrace, IChevron, IList, ITerminal } from "./Icons";
import { useStore } from "../store";
import { Page, TopPage, TOP_PAGES } from "../route";
import { gitsyncApi } from "../api/gitsync";
import { versionApi } from "../api/version";
import { VERSION_KEY } from "./UpdateModal";
import { api } from "../api";
import { SysStat } from "./SysStat";
import { JobStatus } from "./JobStatus";
import { FileMenu } from "./FileMenu";
import type { Route } from "../route";
import { useT } from "../i18n";

interface Props {
  episodes: EpisodeSummary[];
  slug: string;
  page: Page;
  stage: UIStage;
  activeShow: string;
  go: (r: Partial<Route>) => void;
  onPick: (slug: string) => void;
  onStage: (stage: UIStage) => void;
  onPage: (page: TopPage) => void;
  onHome: () => void;
  onOpenSettings: () => void;
  onStartTutorial: () => void;
}

function nowClock() {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function Topbar({ episodes, slug, page, stage, activeShow, go, onPick, onStage, onPage, onHome, onOpenSettings, onStartTutorial }: Props) {
  const t = useT();
  const [clock, setClock] = useState(nowClock);
  const [open, setOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [stopping, setStopping] = useState(false);
  const qc = useQueryClient();
  const toggleDrawer = useStore((s) => s.toggleDrawer);
  const toggleLog = useStore((s) => s.toggleLog);
  const toggleTerminal = useStore((s) => s.toggleTerminal);
  const openUpdate = useStore((s) => s.openUpdate);
  const pushToast = useStore((s) => s.pushToast);

  // Background poll for a newer build → shows the "Update" badge. The backend also
  // checks once at startup, so this is usually populated by first paint.
  const version = useQuery({ queryKey: VERSION_KEY, queryFn: versionApi.get, refetchInterval: 5 * 60_000 });
  const updateAvailable = !!version.data?.check?.update_available;

  async function onSync() {
    if (!slug || syncing) return;
    setSyncing(true);
    try {
      const r = await gitsyncApi.sync(slug);
      if (!r.ok) pushToast(t("toast.gitSyncFailed", { msg: r.log.split("\n").pop() || "" }), "err");
      else if (r.committed) pushToast(t("toast.gitSynced", { slug, commit: r.commit }), "ok");
      else pushToast(t("toast.gitSyncAlready", { slug }), "info");
      // refresh the picker's sync dots
      qc.invalidateQueries({ queryKey: ["episodes"] });
    } catch (e) {
      pushToast(t("toast.gitSyncError", { msg: e instanceof Error ? e.message : String(e) }), "err");
    } finally {
      setSyncing(false);
    }
  }

  async function onStop() {
    if (stopping) return;
    if (!window.confirm(t("topbar.stopConfirm"))) return;
    setStopping(true);
    pushToast(t("toast.emergencyStopStart"), "run");
    try {
      const r = await api.emergencyStop();
      pushToast(t("toast.emergencyStopDone"), "ok");
      // surface the per-step detail in the activity log
      Object.entries(r.report).forEach(([k, v]) => pushToast(`${k}: ${v}`, v.startsWith("err") ? "err" : "info"));
      qc.invalidateQueries({ queryKey: ["pipeline"] });
    } catch (e) {
      pushToast(t("toast.emergencyStopFailed", { msg: e instanceof Error ? e.message : String(e) }), "err");
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
        <FileMenu
          activeShow={activeShow}
          slug={slug}
          go={go}
          onOpenSettings={onOpenSettings}
          onStartTutorial={onStartTutorial}
          onGoAssembly={onHome}
        />
      </div>
      <button
        className="btn p-0.5"
        disabled={!prevEp}
        onClick={() => prevEp && onPick(prevEp.slug)}
        title={prevEp ? t("topbar.prevEp", { slug: prevEp.slug }) : t("topbar.noPrevEp")}
      >
        <IChevron size={14} style={{ transform: "rotate(90deg)" }} />
      </button>
      <div className="relative" data-tour="episode-picker">
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
                  title={e.synced === false ? t("topbar.syncDotPending") : t("topbar.syncDotSynced")}
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
        title={nextEp ? t("topbar.nextEp", { slug: nextEp.slug }) : t("topbar.noNextEp")}
      >
        <IChevron size={14} style={{ transform: "rotate(-90deg)" }} />
      </button>
      <nav className="flex gap-1 ml-3" data-tour="tabs">
        {UI_STAGES.map((s) => {
          const active = page === "stage" && s.key === stage;
          const done = cur ? cur.done_stages >= s.n : false;
          return (
            <button
              key={s.key}
              data-tour={`tab-${s.key}`}
              onClick={() => onStage(s.key)}
              className={"tab flex items-center gap-2 px-3 h-[32px] hairline-soft rounded-[3px] " + (active ? "active" : "")}
              style={active ? { borderColor: "var(--amber)", boxShadow: "var(--glow-amber)", color: "var(--amber)" } : {}}
            >
              <span className={`tab-num ${done ? "done" : ""}`}>{done ? "✓" : s.n}</span>
              <span className="font-semibold tracking-wider uppercase text-[11px]">{t("stage." + s.key)}</span>
            </button>
          );
        })}
        <span className="w-px self-stretch my-1 bg-[var(--line-soft)] mx-1" />
        {TOP_PAGES.map((p) => {
          const active = page === p;
          return (
            <button
              key={p}
              data-tour={`tab-${p}`}
              onClick={() => onPage(p)}
              className={"tab flex items-center gap-2 px-3 h-[32px] hairline-soft rounded-[3px] " + (active ? "active" : "")}
              style={active ? { borderColor: "var(--cyan)", boxShadow: "var(--glow-cyan)", color: "var(--cyan)" } : {}}
            >
              <span className="font-semibold tracking-wider uppercase text-[11px]">{t("toppage." + p)}</span>
            </button>
          );
        })}
      </nav>
      <div className="ml-auto flex items-center gap-3">
        <button
          className="btn"
          data-tour="stop"
          onClick={onStop}
          disabled={stopping}
          title={t("topbar.stopTitle")}
          style={{ borderColor: "var(--red)", color: "var(--red)", boxShadow: "0 0 6px rgba(255,77,77,.35)" }}
        >
          <span className="font-semibold tracking-wider uppercase text-[11px]">{stopping ? t("topbar.stopping") : t("topbar.stop")}</span>
        </button>
        <JobStatus />
        <SysStat />
        <button
          className="btn"
          data-tour="git-sync"
          onClick={onSync}
          disabled={syncing || !slug}
          title={t("topbar.gitSyncTitle")}
        >
          <span className="font-semibold tracking-wider uppercase text-[11px]">
            {syncing ? t("topbar.syncing") : t("topbar.gitSync")}
          </span>
        </button>
        {updateAvailable && (
          <button
            className="btn btn-cyan"
            onClick={openUpdate}
            title={t("topbar.updateTitle", { behind: version.data?.check.behind })}
            style={{ borderColor: "var(--cyan)", color: "var(--cyan)", boxShadow: "var(--glow-cyan)" }}
          >
            <span className="led-dot pulse" style={{ "--led-c": "#33ddff", marginRight: 6 } as React.CSSProperties} />
            <span className="font-semibold tracking-wider uppercase text-[11px]">{t("topbar.update")}</span>
          </button>
        )}
        <span className="seg-readout cyan">{clock}</span>
        <button className="btn" data-tour="drawers" onClick={toggleTerminal} title={t("topbar.terminalTitle")}>
          <ITerminal />
        </button>
        <button className="btn" onClick={toggleLog} title={t("topbar.logTitle")}>
          <IList />
        </button>
        <button className="btn" onClick={toggleDrawer} title={t("topbar.drawerTitle")}>
          <IBrace />
        </button>
      </div>
    </header>
  );
}
