import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { jobStreamUrl } from "./api";
import { useStore } from "./store";
import type { PipelineEvent } from "./types";

/** Tail a job's SSE; on stage.done / job.done invalidate the listed queries.
 *  Returns when stream ends. Pass null to skip.
 */
export function useJobStream(
  jobId: string | null,
  slug: string,
  invalidateKeys: string[] = [],
  onEvent?: (ev: PipelineEvent) => void,
) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  useEffect(() => {
    if (!jobId) return;
    const es = new EventSource(jobStreamUrl(jobId));
    es.onmessage = (m) => {
      let ev: PipelineEvent;
      try { ev = JSON.parse(m.data); } catch { return; }
      onEvent?.(ev);
      if (ev.kind === "stage.done") {
        invalidateKeys.forEach((k) => qc.invalidateQueries({ queryKey: [k, slug] }));
      } else if (ev.kind === "job.done") {
        invalidateKeys.forEach((k) => qc.invalidateQueries({ queryKey: [k, slug] }));
      } else if (ev.kind === "job.error" || ev.kind === "stage.error") {
        push(`pipeline error: ${ev.error}`, "err");
      }
    };
    es.addEventListener("end", () => es.close());
    return () => es.close();
  }, [jobId, slug, invalidateKeys.join(","), qc, push, onEvent]);
}

/** Auto-dismissing busy flag. */
export function useBusy() {
  const busy = useStore((s) => s.busy);
  const setBusy = useStore((s) => s.setBusy);
  return { busy, setBusy };
}

interface ServerEvent { seq: number; ts: number; kind: string; level: string; label: string }

const LEVEL_TO_KIND: Record<string, "info" | "ok" | "run" | "err"> = {
  info: "info", running: "run", success: "ok", error: "err",
};

/** Subscribe once to the global server-event feed (/api/events/stream) and toast
 *  everything the box does — including work kicked off by MCP/API calls that no
 *  browser initiated. EventSource auto-reconnects; only post-connect events arrive. */
export function useServerEvents() {
  const push = useStore((s) => s.pushToast);
  useEffect(() => {
    const es = new EventSource("/api/events/stream");
    es.onmessage = (m) => {
      let ev: ServerEvent;
      try { ev = JSON.parse(m.data); } catch { return; }
      if (!ev.label) return;
      push(ev.label, LEVEL_TO_KIND[ev.level] ?? "info");
    };
    return () => es.close();
  }, [push]);
}
