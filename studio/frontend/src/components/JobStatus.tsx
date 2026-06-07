import { useQuery } from "@tanstack/react-query";
import { useT } from "../i18n";

interface Activity { state: "idle" | "running" | "error"; label: string }

/* Topbar job indicator (left of CPU). Gray IDLE, green while something is
   processing (with a label), red on a recent error — auto-reverts to idle. */
export function JobStatus() {
  const t = useT();
  const q = useQuery<Activity>({
    queryKey: ["activity"],
    queryFn: () => fetch("/api/activity").then((r) => r.json()),
    refetchInterval: 1500,
    staleTime: 0,
  });
  const a = q.data ?? { state: "idle", label: "" };
  const color = a.state === "running" ? "var(--green)" : a.state === "error" ? "var(--red)" : "var(--txt-faint)";
  const text = a.state === "idle" ? "IDLE" : (a.label || (a.state === "error" ? "ERROR" : "WORKING"));
  return (
    <span className="seg-readout inline-flex items-center gap-1.5" style={{ color }} title={a.state === "idle" ? t("jobstatus.idleTitle") : a.label}>
      <span
        className={a.state === "running" ? "led-dot heartbeat" : ""}
        style={{ width: 8, height: 8, borderRadius: "50%", background: color, boxShadow: a.state !== "idle" ? `0 0 5px ${color}` : "none", "--led-c": color } as React.CSSProperties}
      />
      <span className="whitespace-nowrap uppercase text-[11px] tracking-wider">{text}</span>
    </span>
  );
}
