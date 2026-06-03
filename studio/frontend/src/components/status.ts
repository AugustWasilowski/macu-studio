import { AssetStatus } from "../types";

export const statusColor: Record<AssetStatus | string, string> = {
  generated: "#33ff66",
  rendered: "#33ff66",
  exists: "#33ff66",
  done: "#33ff66",
  ok: "#33ff66",
  stale: "#f5a623",
  draft: "#f5a623",
  running: "#00e5ff",
  idle: "#5f5a51",
  missing: "#ff4d4d",
  failed: "#ff4d4d",
  shared: "#938d82",
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
