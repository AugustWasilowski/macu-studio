import { AssetStatus } from "../types";

// var() references so badges/dots follow the active theme's palette.
export const statusColor: Record<AssetStatus | string, string> = {
  generated: "var(--green)",
  rendered: "var(--green)",
  exists: "var(--green)",
  done: "var(--green)",
  ok: "var(--green)",
  stale: "var(--amber)",
  draft: "var(--amber)",
  running: "var(--cyan)",
  idle: "var(--txt-faint)",
  missing: "var(--red)",
  failed: "var(--red)",
  shared: "var(--txt-dim)",
};

export const statusLabel = (s: AssetStatus | string): string => {
  switch (s) {
    case "generated": return "GEN";
    case "rendered": return "RDY";
    case "exists": return "OK";
    case "ok": return "OK";
    case "done": return "DONE";
    case "stale": return "STALE";
    case "draft": return "DRAFT";
    case "running": return "RUN";
    case "idle": return "IDLE";
    case "missing": return "MISS";
    case "failed": return "FAIL";
    case "shared": return "REUSE";
    default: return String(s).toUpperCase();
  }
};
