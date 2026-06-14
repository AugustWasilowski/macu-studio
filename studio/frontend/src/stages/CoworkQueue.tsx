import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { coworkApi } from "../api/cowork";
import type { CoworkJob, CoworkStatus } from "../api/cowork";
import { useStore } from "../store";
import { useT } from "../i18n";

// CoWork job-board panel (SSA-133): watch + lightly manage the free-web →
// local-harvest queue. CoWork drives it via MCP; this is the operator's window.
const STATUS_COLOR: Record<CoworkStatus, string> = {
  pending: "var(--txt-dim)",
  claimed: "var(--cyan)",
  in_progress: "var(--amber)",
  done: "var(--green)",
  failed: "var(--red)",
  skipped: "var(--txt-faint)",
};
const STATUS_FILTERS: Array<CoworkStatus | ""> = ["", "pending", "claimed", "in_progress", "done", "failed", "skipped"];

export function CoworkQueue() {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const activeSlug = useStore((s) => s.activeSlug);

  const [statusF, setStatusF] = useState<CoworkStatus | "">("");
  const [epOnly, setEpOnly] = useState(false); // scope to the active episode

  const episode = epOnly && activeSlug ? activeSlug : undefined;
  const jobs = useQuery({
    queryKey: ["cowork-jobs", episode ?? "", statusF],
    queryFn: () => coworkApi.list({ episode, status: statusF || undefined }),
    refetchInterval: 5000,
  });
  const stats = useQuery({
    queryKey: ["cowork-stats", episode ?? ""],
    queryFn: () => coworkApi.stats(episode),
    refetchInterval: 5000,
  });
  const refetch = () => {
    qc.invalidateQueries({ queryKey: ["cowork-jobs"] });
    qc.invalidateQueries({ queryKey: ["cowork-stats"] });
  };

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); push(ok, "ok"); refetch(); }
    catch (e) { push(String(e), "err"); }
  };

  const list = jobs.data?.jobs ?? [];
  const s = stats.data;

  return (
    <section className="panel flex flex-col min-h-0 overflow-hidden">
      <header className="flex items-center gap-3 px-3 py-2 border-b hairline">
        <div className="panel-title flex-1">{t("cowork.title")}</div>
        {activeSlug && (
          <label className="flex items-center gap-1.5 text-[12px] label-tiny cursor-pointer">
            <input type="checkbox" checked={epOnly} onChange={(e) => setEpOnly(e.target.checked)} />
            {t("cowork.thisEpisode", { slug: activeSlug })}
          </label>
        )}
        <button className="btn text-[11px]" onClick={refetch}>{t("cowork.refresh")}</button>
        <button className="btn text-[11px]" style={{ borderColor: "var(--red)", color: "var(--red)" }}
                onClick={() => { if (confirm(t("cowork.clearConfirm"))) act(() => coworkApi.clear(episode), t("cowork.cleared")); }}>
          {t("cowork.clear")}
        </button>
      </header>

      {/* stats */}
      <div className="flex flex-wrap gap-2 px-3 py-2 border-b hairline-soft">
        {s ? (["pending", "claimed", "in_progress", "done", "failed", "skipped"] as CoworkStatus[]).map((k) => (
          <span key={k} className="seg-readout text-[11px]" style={{ color: STATUS_COLOR[k] }}>
            {t(`cowork.status.${k}`)} {s[k]}
          </span>
        )) : <span className="label-tiny">{t("common.loading")}</span>}
        <span className="seg-readout text-[11px] ml-auto">{t("cowork.total", { n: s?.total ?? 0 })}</span>
      </div>

      {/* status filter */}
      <div className="flex gap-1 px-3 py-1.5 border-b hairline-soft">
        {STATUS_FILTERS.map((f) => (
          <button key={f || "all"} onClick={() => setStatusF(f)}
                  className={"tab px-2 h-[26px] hairline-soft rounded-[3px] text-[11px] " + (statusF === f ? "active" : "")}
                  style={statusF === f ? { borderColor: "var(--amber)", color: "var(--amber)" } : {}}>
            {f ? t(`cowork.status.${f}`) : t("cowork.all")}
          </button>
        ))}
      </div>

      {/* job list */}
      <div className="flex-1 overflow-y-auto">
        {jobs.isError && <div className="p-4 text-red text-[12px]">{String(jobs.error)}</div>}
        {!jobs.isLoading && list.length === 0 && (
          <div className="p-6 text-txt-faint text-[12px] text-center">{t("cowork.empty")}</div>
        )}
        {list.map((j) => <JobRow key={j.id} job={j} act={act} />)}
      </div>

      <p className="px-3 py-2 border-t hairline-soft label-tiny leading-relaxed">{t("cowork.help")}</p>
    </section>
  );
}

function JobRow({ job, act }: { job: CoworkJob; act: (fn: () => Promise<unknown>, ok: string) => void }) {
  const t = useT();
  return (
    <div className="group flex items-center gap-3 px-3 py-2 border-b border-[var(--line-soft)] text-[12px]">
      <span className="seg-readout text-[10px] w-[78px] flex-none text-center" style={{ color: STATUS_COLOR[job.status] }}>
        {t(`cowork.status.${job.status}`)}
      </span>
      <span className="label-tiny w-[64px] flex-none uppercase">{t(`cowork.kind.${job.kind}`)}</span>
      <span className="font-mono truncate flex-1" title={job.prompt || job.target}>{job.target}</span>
      <span className="label-tiny w-[88px] flex-none truncate" title={job.episode}>{job.episode}</span>
      <span className="label-tiny w-[96px] flex-none truncate" title={job.model}>{job.model || "—"}</span>
      {job.result_gen_ids.length > 0 && (
        <span className="seg-readout text-[10px] flex-none" title={job.result_gen_ids.join(", ")}>
          {t("cowork.gens", { n: job.result_gen_ids.length })}
        </span>
      )}
      {job.error && <span className="label-tiny text-red flex-none truncate max-w-[160px]" title={job.error}>{job.error}</span>}
      <div className="flex gap-1 flex-none opacity-0 group-hover:opacity-100 transition-opacity">
        {(job.status === "failed" || job.status === "skipped" || job.status === "claimed") && (
          <button className="btn p-1 text-[10px]" title={t("cowork.requeue")}
                  onClick={() => act(() => coworkApi.patch(job.id, { status: "pending" }), t("cowork.requeued"))}>↺</button>
        )}
        <button className="btn p-1 text-[10px]" title={t("common.delete")}
                onClick={() => act(() => coworkApi.remove(job.id), t("cowork.deleted"))}>🗑</button>
      </div>
    </div>
  );
}
