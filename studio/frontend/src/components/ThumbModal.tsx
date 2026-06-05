import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { versionsApi } from "../api/assets";
import { graphicsApi } from "../api/graphics";
import { useStore } from "../store";
import { Modal } from "./Modal";
import { IChevron } from "./Icons";

/* Enlarged YouTube-thumbnail viewer: big image + version browser (newer/older +
   "Use this version") + the composition/fields metadata that produced each
   version. Live params come from manifest.youtube_thumb; history params from the
   archived version's stamped meta. */
export function ThumbModal({
  open, onClose, slug, liveParams, livePreviewUrl, onChanged,
}: {
  open: boolean;
  onClose: () => void;
  slug: string;
  liveParams: { composition?: string; fields?: Record<string, unknown> } | null;
  livePreviewUrl: string;          // already cache-busted
  onChanged: () => void;           // invalidate manifest/preview after a promote
}) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const [idx, setIdx] = useState(0); // 0 = live, 1..n = history newest→oldest
  const [promoting, setPromoting] = useState(false);

  const q = useQuery({
    queryKey: ["versions", "ythumb", slug, slug],
    queryFn: () => versionsApi.summary(slug, "ythumb", slug),
    enabled: open,
  });
  const entries = q.data?.history ?? [];
  const total = (q.data?.current.exists ? 1 : 0) + entries.length;
  const clamped = Math.min(idx, Math.max(0, total - 1));
  const viewingHistory = clamped > 0;
  const entry = viewingHistory ? entries[clamped - 1] : null;

  const imgUrl = viewingHistory && entry
    ? versionsApi.mediaUrl(slug, "ythumb", slug, entry.v)
    : livePreviewUrl;

  const meta = useMemo(() => {
    if (viewingHistory) {
      const m = (entry?.meta ?? {}) as { composition?: string; fields?: Record<string, unknown> };
      return { composition: m.composition, fields: m.fields };
    }
    return { composition: liveParams?.composition, fields: liveParams?.fields };
  }, [viewingHistory, entry, liveParams]);

  const label = total <= 1 ? "live" : clamped === 0 ? "live" : `v${entry?.v}`;
  const go = (n: number) => setIdx(Math.max(0, Math.min(total - 1, n)));

  const promote = async () => {
    if (!entry) return;
    setPromoting(true);
    try {
      await versionsApi.promote(slug, "ythumb", slug, entry.v);
      qc.invalidateQueries({ queryKey: ["versions", "ythumb", slug, slug] });
      setIdx(0);
      onChanged();
      push(`promoted v${entry.v} → live thumbnail`, "ok");
    } catch (e: any) {
      push("promote failed: " + (e?.message ?? "error"), "err");
    }
    setPromoting(false);
  };

  return (
    <Modal open={open} onClose={onClose} width={760} title="YOUTUBE THUMBNAIL">
      <div className="flex flex-col gap-3">
        <div className="bg-black hairline-soft rounded overflow-hidden grid place-items-center" style={{ aspectRatio: "16/9" }}>
          <img key={imgUrl} src={imgUrl} alt="youtube thumbnail" className="w-full h-full object-contain" />
        </div>

        <div className="flex items-center justify-between gap-2">
          <div className="inline-flex items-center gap-1 text-[12px]">
            <button className="btn p-1" disabled={total <= 1} onClick={() => go(clamped - 1)} title="Newer">
              <IChevron size={13} style={{ transform: "rotate(90deg)" }} />
            </button>
            <span className="font-mono tabular-nums px-1" style={{ minWidth: 70, textAlign: "center" }}>
              {label} <span className="text-txt-faint">{clamped + 1}/{Math.max(1, total)}</span>
            </span>
            <button className="btn p-1" disabled={total <= 1} onClick={() => go(clamped + 1)} title="Older">
              <IChevron size={13} style={{ transform: "rotate(-90deg)" }} />
            </button>
          </div>
          <button
            className="btn btn-amber"
            disabled={!viewingHistory || promoting}
            onClick={promote}
            title={viewingHistory ? "Make this version the live thumbnail" : "Browse to an older version to select it"}
          >
            {promoting ? "Selecting…" : "Use this version"}
          </button>
        </div>

        <div className="hairline-soft rounded p-2 flex flex-col gap-2">
          <div className="grid grid-cols-[90px_1fr] gap-1 text-[12px]">
            <span className="label-tiny">version</span><span className="font-mono">{label}{!viewingHistory && total > 1 ? " (current)" : ""}</span>
            <span className="label-tiny">template</span><span className="font-mono">{meta.composition ?? <span className="text-txt-faint">— not recorded</span>}</span>
          </div>
          <div>
            <span className="label-tiny">fields (JSON)</span>
            <pre className="logtail mt-1" style={{ maxHeight: 200 }}>
              {meta.fields && Object.keys(meta.fields).length
                ? JSON.stringify(meta.fields, null, 2)
                : "— not recorded (rendered before metadata tracking, or no fields)"}
            </pre>
          </div>
        </div>
      </div>
    </Modal>
  );
}
