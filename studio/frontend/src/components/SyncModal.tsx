import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Modal } from "./Modal";
import { syncApi } from "../api/sync";
import type { SyncPlan, SyncReport } from "../api/sync";
import { useStore } from "../store";
import { useT } from "../i18n";

// Studio↔Studio sync: working text (scripts, manifests, docs, character
// records) reconciled through the show's macu-web repo. Opens with a live
// plan; one click applies it. Binaries travel via Import/Export instead.
export function SyncModal({ show, open, onClose }: {
  show: string; open: boolean; onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const [plan, setPlan] = useState<SyncPlan | null>(null);
  const [report, setReport] = useState<SyncReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadPlan = () => {
    setPlan(null); setReport(null); setError(null); setBusy(true);
    syncApi.plan(show)
      .then(setPlan)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };
  useEffect(() => { if (open) loadPlan(); }, [open, show]); // eslint-disable-line react-hooks/exhaustive-deps

  const apply = async () => {
    setBusy(true);
    try {
      const r = await syncApi.apply(show);
      setReport(r);
      if (r.ok) push(t("sync.done", { pushed: r.pushed.length, pulled: r.pulled.length }), "ok");
      else push(t("sync.doneErrors", { n: r.errors.length }), "err");
      // Pulled text can change anything text-derived — refresh broadly.
      ["episodes", "cues", "manifest", "shots", "characters", "docs"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const Section = ({ title, items, tone }: { title: string; items: { path: string; note?: string }[]; tone: string }) =>
    items.length === 0 ? null : (
      <div className="flex flex-col gap-0.5">
        <div className="label-tiny" style={{ color: tone }}>{title} ({items.length})</div>
        <div className="max-h-[140px] overflow-y-auto hairline-soft rounded">
          {items.map((it) => (
            <div key={it.path} className="flex items-center gap-2 px-2 py-0.5 text-[11px] border-b border-[var(--line-soft)]">
              <span className="font-mono flex-1 truncate">{it.path}</span>
              {it.note && <span className="label-tiny flex-none">{it.note}</span>}
            </div>
          ))}
        </div>
      </div>
    );

  return (
    <Modal open={open} onClose={onClose} title={t("sync.title", { show })} width={560}
      footer={
        <>
          <button className="btn" onClick={onClose}>{t("common.close")}</button>
          {!report && (
            <button className="btn" disabled={busy} onClick={loadPlan}>{t("sync.refresh")}</button>
          )}
          {!report && plan && !plan.clean && (
            <button className="btn btn-amber" disabled={busy} onClick={apply}>
              {busy ? t("sync.applying") : t("sync.apply")}
            </button>
          )}
          {report && (
            <button className="btn btn-cyan" onClick={loadPlan}>{t("sync.again")}</button>
          )}
        </>
      }>
      <div className="flex flex-col gap-2 text-[12px]">
        <p className="label-tiny leading-relaxed">{t("sync.help")}</p>
        {busy && !plan && !report && <div className="text-txt-dim">{t("sync.planning")}</div>}
        {error && (
          <div className="text-red text-[12px]">
            {error.includes("409") || error.toLowerCase().includes("not connected")
              ? t("sync.notConnected")
              : error}
          </div>
        )}
        {plan && !report && (
          plan.clean ? (
            <div className="flex items-center gap-2 px-3 py-3 rounded hairline-soft">
              <span className="rounded-full" style={{ width: 10, height: 10, background: "var(--green, #0c6)" }} />
              {t("sync.clean", { n: plan.in_sync })}
            </div>
          ) : (
            <>
              <Section title={t("sync.pushTitle")} tone="var(--cyan)"
                items={plan.push.map((x) => ({ path: x.path, note: x.reason }))} />
              <Section title={t("sync.pullTitle")} tone="var(--green, #0c6)"
                items={plan.pull.map((x) => ({ path: x.path, note: x.reason }))} />
              <Section title={t("sync.conflictTitle")} tone="var(--amber)"
                items={plan.conflicts.map((c) => ({
                  path: c.path,
                  note: c.winner === "local" ? t("sync.localWins") : t("sync.remoteWins"),
                }))} />
              {plan.conflicts.length > 0 && (
                <p className="label-tiny leading-relaxed">{t("sync.conflictHelp")}</p>
              )}
            </>
          )
        )}
        {report && (
          <div className="flex flex-col gap-1">
            <Section title={t("sync.pushedTitle")} tone="var(--cyan)" items={report.pushed.map((p) => ({ path: p }))} />
            <Section title={t("sync.pulledTitle")} tone="var(--green, #0c6)" items={report.pulled.map((p) => ({ path: p }))} />
            {report.backed_up.length > 0 && (
              <p className="label-tiny">{t("sync.backups", { n: report.backed_up.length })}</p>
            )}
            {report.errors.length > 0 && (
              <div className="text-red text-[11px] whitespace-pre-wrap">{report.errors.join("\n")}</div>
            )}
            {report.ok && report.pushed.length === 0 && report.pulled.length === 0 && (
              <div className="text-txt-dim">{t("sync.nothingDone")}</div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
