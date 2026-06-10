import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "./Modal";
import { useStore } from "../store";
import { versionApi, UpdateState } from "../api/version";
import { useT } from "../i18n";

// Shared query key so the Topbar badge and this modal read the same cache.
export const VERSION_KEY = ["version"];

function shortIso(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

/* Self-update modal. Opened from the Topbar "Update" badge or the File menu's
   "Check for updates…". Drives:
     - POST /api/version/check  (manual re-check)
     - POST /api/version/update (pull + rebuild + restart) with a live log
   When the backend enters the "restarting" phase it exits and systemd relaunches it;
   we wait for /api/health to come back on the NEW process, then reload the page. */
export function UpdateModal() {
  const t = useT();
  const open = useStore((s) => s.updateOpen);
  const close = useStore((s) => s.closeUpdate);
  const qc = useQueryClient();
  const pushToast = useStore((s) => s.pushToast);

  const info = useQuery({
    queryKey: VERSION_KEY,
    queryFn: versionApi.get,
    enabled: open,
    refetchInterval: open ? false : 5 * 60_000,
  });

  const [checking, setChecking] = useState(false);
  // The running update — null until the user clicks Update. Polled separately.
  const [job, setJob] = useState<UpdateState | null>(null);
  const restartAt = useRef<number | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const cur = info.data?.current;
  const chk = info.data?.check;

  async function onCheck() {
    if (checking) return;
    setChecking(true);
    try {
      await versionApi.check();
      await qc.invalidateQueries({ queryKey: VERSION_KEY });
    } catch (e) {
      pushToast(t("toast.checkFailed", { msg: e instanceof Error ? e.message : String(e) }), "err");
    } finally {
      setChecking(false);
    }
  }

  async function onUpdate() {
    if (job) return;
    try {
      await versionApi.update();
      setJob({ phase: "pulling", log: [], error: null, started: Date.now() });
    } catch (e) {
      pushToast(t("toast.updateStartFailed", { msg: e instanceof Error ? e.message : String(e) }), "err");
    }
  }

  // Poll the running update's status. Tolerates the server going away during the
  // restart phase (fetch throws → we keep polling until /api/health returns).
  useEffect(() => {
    if (!job) return;
    if (job.phase === "restart-needed" || job.phase === "error") return;

    let alive = true;
    const tick = async () => {
      try {
        const s = await versionApi.status();
        if (!alive) return;
        if (s.phase === "restarting" && restartAt.current === null) restartAt.current = Date.now();
        setJob(s);
      } catch {
        // Server is down (restarting) — once it answers /api/health on the NEW
        // process (and the old one has had time to exit), reload onto the new build.
        if (restartAt.current === null) restartAt.current = Date.now();
        if (Date.now() - (restartAt.current ?? 0) > 3000) {
          try {
            const r = await fetch("/api/health", { cache: "no-store" });
            if (alive && r.ok) {
              window.location.reload();
              return;
            }
          } catch {
            /* still down — keep waiting */
          }
        }
      }
    };
    const timer = setInterval(tick, 1500);
    tick();
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [job?.phase, job !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the log scrolled to the bottom.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [job?.log.length]);

  // Reset transient state each time the modal is freshly opened, and kick off a
  // fresh check right away — opening the modal *is* the ask; don't make the user
  // click "Check for updates" to get past a stale cached result.
  useEffect(() => {
    if (open) {
      setJob(null);
      restartAt.current = null;
      onCheck();
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  const running = !!job && (job.phase === "pulling" || job.phase === "building" || job.phase === "restarting");
  const dirty = cur?.dirty;
  const upToDate = chk && !chk.update_available && !chk.error;

  return (
    <Modal
      open
      onClose={running ? () => {} : close}
      title={t("update.title")}
      width={560}
      footer={
        running ? undefined : job?.phase === "error" ? (
          <button className="btn btn-amber" onClick={() => setJob(null)}>{t("common.back")}</button>
        ) : job?.phase === "restart-needed" ? (
          <button className="btn btn-amber" onClick={close}>{t("common.close")}</button>
        ) : (
          <>
            <button className="btn" onClick={onCheck} disabled={checking}>
              {checking ? t("update.checking") : t("update.checkBtn")}
            </button>
            {chk?.update_available && !dirty && !chk?.requires_setup && (
              <button className="btn btn-amber" onClick={onUpdate}>{t("update.updateBtn")}</button>
            )}
            <button className="btn" onClick={close}>{t("common.close")}</button>
          </>
        )
      }
    >
      {/* ---- Live update progress ---- */}
      {job ? (
        <div className="flex flex-col gap-2">
          <div className="text-[13px]">
            {job.phase === "pulling" && <span className="text-amber">{t("update.phasePulling")}</span>}
            {job.phase === "building" && <span className="text-amber">{t("update.phaseBuilding")}</span>}
            {job.phase === "restarting" && <span className="text-amber">{t("update.phaseRestarting")}</span>}
            {job.phase === "restart-needed" && <span className="text-cyan">{t("update.phaseRestartNeeded")}</span>}
            {job.phase === "error" && <span className="text-err">{t("update.phaseFailed")}</span>}
          </div>
          {job.error && <div className="label-tiny text-err leading-relaxed">{job.error}</div>}
          <div
            ref={logRef}
            className="font-mono text-[11px] leading-relaxed bg-black/50 rounded p-2 max-h-[300px] overflow-y-auto whitespace-pre-wrap"
          >
            {job.log.length ? job.log.join("\n") : "…"}
          </div>
        </div>
      ) : (
        /* ---- Idle: current version + check result ---- */
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <div className="label-tiny">{t("update.installed")}</div>
            <div className="text-[13px]">
              {cur?.release && <span className="font-mono text-amber">{cur.release} </span>}
              <span className={`font-mono ${cur?.release ? "text-txt-dim" : "text-amber"}`}>{cur?.short ?? "…"}</span>
              <span className="text-txt-dim"> · {cur?.branch}</span>
            </div>
            {cur?.subject && <div className="label-tiny truncate">{cur.subject}</div>}
            {cur?.committed_iso && <div className="label-tiny opacity-70">{shortIso(cur.committed_iso)}</div>}
          </div>

          {dirty && (
            <p className="label-tiny text-err leading-relaxed">
              {t("update.dirtyWarning")}
            </p>
          )}

          {checking ? (
            <div className="text-[13px] text-txt-dim">{t("update.checking")}</div>
          ) : chk?.error ? (
            <p className="label-tiny text-err leading-relaxed">{t("update.checkError", { error: chk.error })}</p>
          ) : chk?.update_available ? (
            <div className="flex flex-col gap-1">
              <div className="text-[13px] text-cyan">
                {t("update.available", { count: chk.behind })}
                {chk.remote_short && <span className="font-mono text-txt-dim"> → {chk.remote_short}</span>}
              </div>
              <div className="bg-black/40 rounded p-2 max-h-[200px] overflow-y-auto flex flex-col gap-0.5">
                {chk.incoming.map((c) => (
                  <div key={c.short} className="text-[12px] flex gap-2">
                    <span className="font-mono text-amber flex-none">{c.short}</span>
                    <span className="text-txt-dim truncate">{c.subject}</span>
                  </div>
                ))}
              </div>
              {chk.setup.length > 0 && (
                <div className="flex flex-col gap-2 mt-1 rounded border border-amber/40 bg-amber/10 p-2">
                  <div className="text-[13px] text-amber">
                    {chk.requires_setup ? t("update.setupTitle") : t("update.noticeTitle")}
                  </div>
                  <p className="label-tiny leading-relaxed">
                    {chk.requires_setup ? t("update.setupIntro") : t("update.noticeIntro")}
                  </p>
                  <ul className="flex flex-col gap-1.5">
                    {chk.setup.map((s) => (
                      <li key={s.area} className="text-[12px] leading-relaxed">
                        <span className="text-txt-dim">{s.reason}</span>
                        {s.command && (
                          <div className="font-mono text-[11px] bg-black/50 rounded px-2 py-1 mt-0.5 select-all">
                            {s.command}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {!chk.requires_setup && (
                <p className="label-tiny opacity-70 leading-relaxed mt-1">
                  {t("update.updateHint")}
                </p>
              )}
            </div>
          ) : upToDate ? (
            <div className="text-[13px] text-green">{t("update.upToDate")}</div>
          ) : (
            <div className="label-tiny opacity-70">{t("update.idleHint")}</div>
          )}

          {chk?.ts && (
            <div className="label-tiny opacity-50">{t("update.lastChecked", { date: shortIso(new Date(chk.ts * 1000).toISOString()) })}</div>
          )}
        </div>
      )}
    </Modal>
  );
}
