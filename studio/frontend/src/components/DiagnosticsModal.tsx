import { useCallback, useEffect, useState } from "react";
import { Modal } from "./Modal";
import { useStore } from "../store";
import { diagnosticsApi, DiagnosticsResult } from "../api/diagnostics";
import { useT } from "../i18n";
import { Trans } from "../i18n/Trans";

/* Host preflight on demand — runs deploy/doctor.sh server-side and shows the report
   (git/ffmpeg/python/node, Docker + nvidia runtime, GPU/VRAM, optional chat/terminal
   deps). Auto-runs when opened; "Re-run" repeats it after the user fixes something. */
export function DiagnosticsModal() {
  const t = useT();
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
    ? { text: t("diagnostics.bannerRunning"), cls: "text-amber" }
    : error
    ? { text: t("diagnostics.bannerError"), cls: "text-err" }
    : result
    ? result.ok
      ? { text: t("diagnostics.bannerOk"), cls: "text-green" }
      : { text: t("diagnostics.bannerFailed"), cls: "text-err" }
    : { text: "", cls: "" };

  return (
    <Modal
      open
      onClose={close}
      title={t("diagnostics.title")}
      width={620}
      footer={
        <>
          <button className="btn" onClick={run} disabled={running}>
            {running ? t("diagnostics.btnRunning") : t("diagnostics.btnRerun")}
          </button>
          <button className="btn btn-amber" onClick={close}>{t("common.close")}</button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-[13px]">
          <span className={banner.cls}>{banner.text}</span>
        </div>
        {error && <div className="label-tiny text-err leading-relaxed">{error}</div>}
        <div className="font-mono text-[11px] leading-relaxed bg-black/50 rounded p-2 max-h-[400px] overflow-y-auto whitespace-pre-wrap">
          {running && !result ? "…" : result ? result.output || t("diagnostics.noOutput") : ""}
        </div>
        <p className="label-tiny opacity-70 leading-relaxed">
          <Trans
            k="diagnostics.preflightNote"
            vars={{ cmd: "deploy/doctor.sh" }}
            tags={[(c) => <span className="font-mono">{c}</span>]}
          />
        </p>
      </div>
    </Modal>
  );
}
