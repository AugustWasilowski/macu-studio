import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, mediaUrl } from "../api";
import { graphicsApi } from "../api/graphics";
import { useStore } from "../store";
import { PlayBtn } from "../components/PlayBtn";
import { IPlay, IPause, IX } from "../components/Icons";
import { useSfx, type PlayItem } from "./AudioSfx";
import { useCuePlayback } from "./useCuePlayback";
import { cueOffsets, coveredCues, makeOverlay } from "./overlayTiming";
import { drawerDrag } from "./trackEditor";
import { versionsApi } from "../api/assets";
import type { Overlay } from "../types";
import { useT } from "../i18n";

/** The dope sheet — a cue table where graphics/title cards are dropped onto a cue to
 * place an overlay. Lives on the Assembly tab (left column). Its drag SOURCE is the
 * co-mounted timeline AssetDrawer's GRAPHICS CARDS tab (shared `drawerDrag` payload).
 * Self-contained: owns its own cues/manifest queries, overlay state, and playback. */
export function DopeSheet({ slug }: { slug: string }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);

  const cues = useQuery({ queryKey: ["cues", slug], queryFn: () => api.cues(slug), refetchInterval: 4000 });
  const manifest = useQuery({ queryKey: ["manifest", slug], queryFn: () => api.manifest(slug) });

  const cueList = cues.data?.cues ?? [];
  const overlays: Overlay[] = useMemo(
    () => ((manifest.data as any)?.overlays as Overlay[]) ?? [],
    [manifest.data],
  );
  const { cum } = useMemo(() => cueOffsets(cueList), [cueList]);

  const sfx = useSfx(slug);
  const playback = useCuePlayback({
    buildPlaylist: () => sfx.buildPlaylist(),
    resolveSingle: (cueId): PlayItem => {
      const c = cueList.find((x) => x.id === cueId);
      return { url: mediaUrl.cueAudio(slug, cueId, c?.wav_mtime), cueId, label: cueId };
    },
    notify: push,
  });
  const { continuous, setContinuous, curCueId, sequentialPlaying, togglePlay, playAll } = playback;

  const putOverlays = useMutation({
    mutationFn: (next: Overlay[]) => graphicsApi.putOverlays(slug, next),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["manifest", slug] }),
    onError: (e: Error) => push(t("dopesheet.overlaysSaveFailed", { msg: e.message }), "err"),
  });
  const commitOverlays = (next: Overlay[]) => putOverlays.mutate(next);
  const addOverlay = (cueId: string, asset: string) => {
    const c = cueList.find((x) => x.id === cueId);
    commitOverlays([...overlays, makeOverlay(asset, cueId, c?.duration_s ?? 3)]);
    push(t("toast.graphicAdded", { asset, cueId }), "ok");
  };
  const removeOverlay = (idx: number) => commitOverlays(overlays.filter((_, i) => i !== idx));
  // Card drop source is the timeline's GRAPHICS CARDS drawer tab (drawerDrag, kind "card").
  const onDropCue = async (cueId: string) => {
    const d = drawerDrag.get();
    drawerDrag.clear();
    if (d?.kind !== "card") return;
    if (d.slug && d.slug !== slug) {
      try {
        const r = await versionsApi.importTitle(slug, d.slug, d.asset);
        push(r.master_copied ? t("toast.graphicPulled", { asset: d.asset, slug: d.slug })
             : r.already ? t("toast.graphicAlreadyPresent", { asset: d.asset })
             : t("toast.graphicImported", { asset: d.asset, slug: d.slug }), "ok");
      } catch (err: any) { push(t("dopesheet.importFailed", { msg: err?.message ?? "error" }), "err"); return; }
    }
    addOverlay(cueId, d.asset);
  };

  // overlays grouped by their anchor cue (rendered under that cue row)
  const overlaysByAnchor = useMemo(() => {
    const m = new Map<string, { ov: Overlay; idx: number }[]>();
    overlays.forEach((ov, idx) => {
      const k = ov.anchor_cue;
      (m.get(k) ?? m.set(k, []).get(k)!).push({ ov, idx });
    });
    return m;
  }, [overlays]);

  return (
    <section className="panel flex flex-col min-h-0">
      <header className="flex items-center justify-between px-3 py-2 border-b hairline">
        <div className="panel-title">{t("dopesheet.title")} <span className="text-txt-faint normal-case tracking-normal text-[11px]">{t("dopesheet.dragHint")}</span></div>
        <div className="flex items-center gap-2">
          <span className="seg-readout">{t("dopesheet.gfxCount", { count: overlays.length })}</span>
          <button className="btn btn-cyan" onClick={playAll} title={sequentialPlaying ? t("dopesheet.stopPlaybackTitle") : t("dopesheet.playAllTitle")}>
            {sequentialPlaying ? <IPause /> : <IPlay />} {sequentialPlaying ? t("dopesheet.stop") : t("dopesheet.playAll")}
          </button>
          <label className="flex items-center gap-1 text-[11px] text-txt-dim cursor-pointer select-none" title={t("dopesheet.continuousTitle")}>
            <input type="checkbox" checked={continuous} onChange={(e) => setContinuous(e.target.checked)} />
            {t("dopesheet.continuous")}
          </label>
        </div>
      </header>
      <div className="overflow-y-auto flex-1">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-bg-1">
            <tr className="label-tiny text-left border-b hairline-soft">
              <th className="px-2 py-1">{t("dopesheet.colCue")}</th>
              <th className="px-2 py-1">{t("dopesheet.colSpeaker")}</th>
              <th className="px-2 py-1">{t("dopesheet.colVoText")}</th>
              <th className="px-2 py-1">{t("dopesheet.colDur")}</th>
              <th className="px-2 py-1"></th>
            </tr>
          </thead>
          <tbody>
            {cueList.map((c) => {
              const isPlaying = curCueId === c.id;
              const anchored = overlaysByAnchor.get(c.id) ?? [];
              return (
                <CueRow
                  key={c.id}
                  slug={slug}
                  cueId={c.id}
                  speaker={c.speaker}
                  text={c.is_hold ? `[HOLD ${c.hold_seconds}s]` : c.text}
                  durationS={c.duration_s}
                  wavExists={c.wav_exists}
                  isPlaying={isPlaying}
                  onPlay={() => togglePlay(c.id)}
                  onDropCard={() => onDropCue(c.id)}
                  anchored={anchored}
                  cueList={cueList}
                  cum={cum}
                  onRemoveOverlay={removeOverlay}
                />
              );
            })}
          </tbody>
        </table>
        {cueList.length === 0 && <div className="p-4 text-txt-faint">{t("dopesheet.noCues")}</div>}
      </div>
    </section>
  );
}

/* One dope-sheet row: the cue + a drop target + any graphics anchored to it. */
function CueRow({
  slug, cueId, speaker, text, durationS, wavExists, isPlaying,
  onPlay, onDropCard, anchored, cueList, cum, onRemoveOverlay,
}: {
  slug: string;
  cueId: string;
  speaker: string;
  text: string;
  durationS: number | null;
  wavExists: boolean;
  isPlaying: boolean;
  onPlay: () => void;
  onDropCard: () => void;
  anchored: { ov: Overlay; idx: number }[];
  cueList: { id: string; duration_s: number | null }[];
  cum: Record<string, number>;
  onRemoveOverlay: (idx: number) => void;
}) {
  const t = useT();
  const [over, setOver] = useState(false);
  return (
    <>
      <tr
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={() => { setOver(false); onDropCard(); }}
        className={"border-b border-[var(--line-soft)] hover:bg-bg-3 " + (over ? "outline outline-1 outline-[var(--cyan)] bg-bg-3" : "")}
      >
        <td className="px-2 py-1.5 text-amber font-bold">{cueId}</td>
        <td className="px-2 py-1.5 whitespace-nowrap">{speaker}</td>
        <td className="px-2 py-1.5 max-w-[360px] truncate" title={text}>{text}</td>
        <td className="px-2 py-1.5 text-cyan whitespace-nowrap">{durationS != null ? `${durationS.toFixed(1)}s` : "—"}</td>
        <td className="px-2 py-1.5">
          <PlayBtn playing={isPlaying} onClick={onPlay} title={wavExists ? t("dopesheet.playTitle") : t("dopesheet.noWavYet")} />
        </td>
      </tr>
      {anchored.length > 0 && (
        <tr>
          <td colSpan={5} className="p-0">
            <div className="pl-9 pr-2 pb-1 flex flex-col gap-1">
              {anchored.map(({ ov, idx }) => {
                const span = coveredCues(ov, cueList, cum);
                const spanLabel = span.length <= 1 ? (span[0] ?? cueId) : `${span[0]}–${span[span.length - 1]}`;
                return (
                  <div key={ov.id ?? idx} className="flex items-center gap-2 text-[11px] hairline-soft rounded px-2 py-0.5 bg-bg-2">
                    <span className="text-cyan">▦</span>
                    <video
                      src={mediaUrl.titlePreview(slug, ov.asset)}
                      muted loop autoPlay playsInline
                      className="bg-black rounded pointer-events-none"
                      style={{ width: 28, height: 28, objectFit: "contain" }}
                    />
                    <span className="font-mono flex-1 truncate" title={ov.asset}>{ov.asset}</span>
                    <span className={"px-1 rounded text-[10px] " + (ov.mode === "overlay" ? "text-cyan" : "text-amber")}>{ov.mode}</span>
                    <span className="text-txt-faint">{spanLabel} · {(ov.duration ?? 0).toFixed(1)}s</span>
                    <button className="btn p-0.5" title={t("dopesheet.removeGraphic")} onClick={() => onRemoveOverlay(idx)}><IX /></button>
                  </div>
                );
              })}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
