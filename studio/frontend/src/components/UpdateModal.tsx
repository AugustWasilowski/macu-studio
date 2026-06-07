import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Modal } from "./Modal";
import { useStore } from "../store";
import { versionApi, UpdateState } from "../api/version";

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
      pushToast(`check failed: ${e instanceof Error ? e.message : String(e)}`, "err");
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
      pushToast(`update failed to start: ${e instanceof Error ? e.message : String(e)}`, "err");
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
    const t = setInterval(tick, 1500);
    tick();
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [job?.phase, job !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the log scrolled to the bottom.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [job?.log.length]);

  // Reset transient state each time the modal is freshly opened.
  useEffect(() => {
    if (open) {
      setJob(null);
      restartAt.current = null;
    }
  }, [open]);

  if (!open) return null;

  const running = !!job && (job.phase === "pulling" || job.phase === "building" || job.phase === "restarting");
  const dirty = cur?.dirty;
  const upToDate = chk && !chk.update_available && !chk.error;

  return (
    <Modal
      open
      onClose={running ? () => {} : close}
      title="Software update"
      width={560}
      footer={
        running ? undefined : job?.phase === "error" ? (
          <button className="btn btn-amber" onClick={() => setJob(null)}>Back</button>
        ) : job?.phase === "restart-needed" ? (
          <button className="btn btn-amber" onClick={close}>Close</button>
        ) : (
          <>
            <button className="btn" onClick={onCheck} disabled={checking}>
              {checking ? "Checking…" : "Check for updates"}
            </button>
            {chk?.update_available && !dirty && (
              <button className="btn btn-amber" onClick={onUpdate}>Update &amp; restart</button>
            )}
            <button className="btn" onClick={close}>Close</button>
          </>
        )
      }
    >
      {/* ---- Live update progress ---- */}
      {job ? (
        <div className="flex flex-col gap-2">
          <div className="text-[13px]">
            {job.phase === "pulling" && <span className="text-amber">Pulling latest code…</span>}
            {job.phase === "building" && <span className="text-amber">Rebuilding (deps + UI)… this can take a minute.</span>}
            {job.phase === "restarting" && <span className="text-amber">Restarting — the page will reload automatically.</span>}
            {job.phase === "restart-needed" && <span className="text-cyan">Update built. Restart the server manually to load it.</span>}
            {job.phase === "error" && <span className="text-err">Update failed.</span>}
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
            <div className="label-tiny">Installed</div>
            <div className="text-[13px]">
              <span className="font-mono text-amber">{cur?.short ?? "…"}</span>
              <span className="text-txt-dim"> · {cur?.branch}</span>
            </div>
            {cur?.subject && <div className="label-tiny truncate">{cur.subject}</div>}
            {cur?.committed_iso && <div className="label-tiny opacity-70">{shortIso(cur.committed_iso)}</div>}
          </div>

          {dirty && (
            <p className="label-tiny text-err leading-relaxed">
              This checkout has uncommitted local changes — auto-update is disabled to avoid
              clobbering them. Commit or discard them (or update from a terminal) first.
            </p>
          )}

          {chk?.error ? (
            <p className="label-tiny text-err leading-relaxed">Couldn't check: {chk.error}</p>
          ) : chk?.update_available ? (
            <div className="flex flex-col gap-1">
              <div className="text-[13px] text-cyan">
                Update available — {chk.behind} new commit{chk.behind === 1 ? "" : "s"}
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
              <p className="label-tiny opacity-70 leading-relaxed mt-1">
                "Update &amp; restart" pulls, rebuilds the UI, and relaunches the service
                (~1 min). The page reloads itself when it's back.
              </p>
            </div>
          ) : upToDate ? (
            <div className="text-[13px] text-green">You're on the latest version.</div>
          ) : (
            <div className="label-tiny opacity-70">Click "Check for updates" to look for a newer build.</div>
          )}

          {chk?.ts && (
            <div className="label-tiny opacity-50">Last checked {shortIso(new Date(chk.ts * 1000).toISOString())}</div>
          )}
        </div>
      )}
    </Modal>
  );
}
