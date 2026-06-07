import { useCallback, useEffect, useState } from "react";
import { Modal } from "./Modal";
import { useStore } from "../store";
import { diagnosticsApi, DiagnosticsResult } from "../api/diagnostics";

/* Host preflight on demand — runs deploy/doctor.sh server-side and shows the report
   (git/ffmpeg/python/node, Docker + nvidia runtime, GPU/VRAM, optional chat/terminal
   deps). Auto-runs when opened; "Re-run" repeats it after the user fixes something. */
export function DiagnosticsModal() {
  const open = useStore((s) => s.diagnosticsOpen);
  const close = useStore((s) => s.closeDiagnostics);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DiagnosticsResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(await diagnosticsApi.run());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, []);

  // Auto-run on open; clear stale output when closed.
  useEffect(() => {
    if (open) {
      setResult(null);
      run();
    }
  }, [open, run]);

  if (!open) return null;

  const banner = running
    ? { text: "Running diagnostics…", cls: "text-amber" }
    : error
    ? { text: "Couldn't run diagnostics.", cls: "text-err" }
    : result
    ? result.ok
      ? { text: "All required checks passed.", cls: "text-green" }
      : { text: "Some required checks failed — see below.", cls: "text-err" }
    : { text: "", cls: "" };

  return (
    <Modal
      open
      onClose={close}
      title="System diagnostics"
      width={620}
      footer={
        <>
          <button className="btn" onClick={run} disabled={running}>
            {running ? "Running…" : "Re-run"}
          </button>
          <button className="btn btn-amber" onClick={close}>Close</button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-[13px]">
          <span className={banner.cls}>{banner.text}</span>
        </div>
        {error && <div className="label-tiny text-err leading-relaxed">{error}</div>}
        <div className="font-mono text-[11px] leading-relaxed bg-black/50 rounded p-2 max-h-[400px] overflow-y-auto whitespace-pre-wrap">
          {running && !result ? "…" : result ? result.output || "(no output)" : ""}
        </div>
        <p className="label-tiny opacity-70 leading-relaxed">
          This runs the installer preflight (<span className="font-mono">deploy/doctor.sh</span>)
          on the host. It only checks — it never installs anything.
        </p>
      </div>
    </Modal>
  );
}
