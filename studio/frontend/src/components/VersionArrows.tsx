import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { versionsApi } from "../api/assets";
import { useStore } from "../store";
import { IChevron } from "./Icons";

/* Compact ← idx/total → version browser for a single asset, sized to live in a
   table cell. The Graphics page reuses this with kind="ythumb" — keep the prop
   contract stable. `onView(null)` means "show the live/canonical asset". */
export function VersionArrows({
  slug, kind, vkey, onView, onChanged,
}: {
  slug: string;
  kind: "cue" | "shot" | "ythumb";
  vkey: string;
  onView?: (mediaUrl: string | null) => void;
  onChanged?: () => void;
}) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const [idx, setIdx] = useState(0);
  const [promoting, setPromoting] = useState(false);

  const q = useQuery({
    queryKey: ["versions", kind, slug, vkey],
    queryFn: () => versionsApi.summary(slug, kind, vkey),
  });

  const summary = q.data;
  const count = summary?.count ?? 0;
  // Browsable list: index 0 is the live/canonical asset, then history newest→oldest.
  const entries = summary?.history ?? [];
  const total = (summary?.current.exists ? 1 : 0) + entries.length;
  const disabled = count <= 1;
  const clamped = Math.min(idx, Math.max(0, total - 1));
  const viewingHistory = clamped > 0;

  const go = (next: number) => {
    if (disabled) return;
    const n = Math.max(0, Math.min(total - 1, next));
    setIdx(n);
    if (onView) {
      if (n === 0) onView(null);
      else {
        const e = entries[n - 1];
        onView(e ? versionsApi.mediaUrl(slug, kind, vkey, e.v) : null);
      }
    }
  };

  const promote = async () => {
    const e = entries[clamped - 1];
    if (!e) return;
    setPromoting(true);
    try {
      await versionsApi.promote(slug, kind, vkey, e.v);
      qc.invalidateQueries({ queryKey: ["versions", kind, slug, vkey] });
      setIdx(0);
      onView?.(null);
      onChanged?.();
      push(`promoted v${e.v} → live`, "ok");
    } catch (err: any) {
      push("promote failed: " + (err?.message ?? "error"), "err");
    }
    setPromoting(false);
  };

  const label = total <= 1 ? "live" : clamped === 0 ? "live" : `v${entries[clamped - 1]?.v}`;

  return (
    <div
      className={"inline-flex items-center gap-1 text-[11px] " + (disabled ? "opacity-40 pointer-events-none" : "")}
      title={disabled ? "Only one version" : "Browse versions"}
    >
      <button className="btn p-0.5" disabled={disabled} onClick={() => go(clamped + 1)} title="Older">
        <IChevron size={12} style={{ transform: "rotate(90deg)" }} />
      </button>
      <span className="font-mono whitespace-nowrap tabular-nums" style={{ minWidth: 52, textAlign: "center" }}>
        {label} <span className="text-txt-faint">{clamped + 1}/{Math.max(1, total)}</span>
      </span>
      <button className="btn p-0.5" disabled={disabled} onClick={() => go(clamped - 1)} title="Newer">
        <IChevron size={12} style={{ transform: "rotate(-90deg)" }} />
      </button>
      <button
        className="btn p-0.5 px-1"
        disabled={disabled || !viewingHistory || promoting}
        onClick={promote}
        title="Promote this version to live"
      >
        use
      </button>
    </div>
  );
}
