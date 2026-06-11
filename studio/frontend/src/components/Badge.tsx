import { statusColor, statusLabel } from "./status";
import { AssetStatus } from "../types";

export function Badge({ status, children }: { status: AssetStatus | string; children?: React.ReactNode }) {
  const c = statusColor[status] ?? "var(--txt-dim)";
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-[2px] text-[10px] font-semibold tracking-[1px] uppercase border rounded-[2px]"
      style={{
        color: c,
        borderColor: `color-mix(in srgb, ${c} 33%, transparent)`,
        background: `color-mix(in srgb, ${c} 7%, transparent)`,
        textShadow: `0 0 6px color-mix(in srgb, ${c} 50%, transparent)`,
      }}
    >
      <span className="led-dot" style={{ "--led-c": c } as React.CSSProperties} />
      {children ?? statusLabel(status)}
    </span>
  );
}

export function Dot({ status, pulse }: { status: AssetStatus | string; pulse?: boolean }) {
  const c = statusColor[status] ?? "var(--txt-dim)";
  return <span className={"led-dot " + (pulse ? "pulse" : "")} style={{ "--led-c": c } as React.CSSProperties} />;
}
