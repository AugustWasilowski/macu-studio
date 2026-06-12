import { useT } from "../i18n";
import { mediaUrl } from "../api";
import type { MusicBed, SfxEntry } from "../api/library";
import { IX } from "../components/Icons";
import type { Cue, Overlay, OverlayMode, OverlayPosition } from "../types";
import type { Selection } from "./trackEditor";

const POSITIONS: OverlayPosition[] = ["lower_third", "bug_tl", "bug_tr", "center", "full"];

type CueShot = Cue["shots"][number];

export interface MetaCallbacks {
  slug: string;
  patchOverlay: (idx: number, p: Partial<Overlay>) => void;
  removeOverlay: (idx: number) => void;
  patchSfx: (idx: number, p: Partial<SfxEntry>) => void;
  removeSfx: (idx: number) => void;
  patchBed: (idx: number, p: Partial<MusicBed>) => void;
  removeBed: (idx: number) => void;
  patchShot: (cueId: string, shotId: string, p: Partial<CueShot>) => void;
  removeShot: (cueId: string, shotId: string) => void;
}

export function MetadataPanel({ sel, cb, overlays, beds, sfx, cues = [] }: {
  sel: Selection | null;
  cb: MetaCallbacks;
  overlays: Overlay[];
  beds: MusicBed[];
  sfx: SfxEntry[];
  cues?: Cue[];
}) {
  const t = useT();
  // Read the live item by index so edit inputs reflect the current manifest, not
  // the (possibly stale) snapshot captured when the clip was selected.
  if (sel?.t === "overlay") sel = { ...sel, ov: overlays[sel.idx] ?? sel.ov };
  if (sel?.t === "bed") sel = { ...sel, b: beds[sel.idx] ?? sel.b };
  if (sel?.t === "sfx") sel = { ...sel, e: sfx[sel.idx] ?? sel.e };
  if (sel?.t === "shot") {
    const liveCue = cues.find((c) => c.id === (sel as any).cueId);
    const live = liveCue?.shots.find((s) => s.id === (sel as any).shot.id);
    if (live) sel = { ...sel, shot: live };
  }
  return (
    <section className="panel p-3 flex flex-col gap-2 overflow-y-auto">
      <div className="panel-title">{t("metadata.title")}</div>
      {!sel && <div className="text-txt-faint text-[12px]">{t("metadata.emptyHint")}</div>}

      {sel?.t === "cue" && <Rows rows={[
        [t("metadata.rowKind"), t("metadata.kindCue")],
        [t("metadata.rowId"), sel.cue.id],
        [t("metadata.rowSpeaker"), sel.cue.speaker || "—"],
        [t("metadata.rowDuration"), sel.cue.duration_s != null ? `${sel.cue.duration_s.toFixed(2)}s` : "—"],
        [t("metadata.rowSegment"), sel.cue.segment ?? "—"],
        [t("metadata.rowShots"), String(sel.cue.shots?.length ?? 0)],
        [t("metadata.rowFile"), `vo/${sel.cue.id}.wav`],
      ]} note={sel.cue.text} />}

      {sel?.t === "shot" && (() => {
        const s = sel.shot;
        const cueId = sel.cueId;
        const lipsync = s.kind === "lipsync";
        const crop = s.crop ?? {};
        const trim = s.trim ?? {};
        const patchCrop = (p: Partial<NonNullable<CueShot["crop"]>>) =>
          cb.patchShot(cueId, s.id, { crop: { x: 0.5, y: 0.5, zoom: 1, ...crop, ...p } });
        return (
          <>
            <div className="flex items-center gap-2">
              <span>{lipsync ? "👄" : "☁"}</span>
              <span className="font-mono text-[12px] flex-1 truncate">{s.id}</span>
              <button className="btn p-1" title={t("metadata.removeFromTimeline")} onClick={() => cb.removeShot(cueId, s.id)}><IX /></button>
            </div>
            <div className="label-tiny">{t("metadata.shotCropTitle")}</div>
            <SliderRow label={t("metadata.rowCropX")} value={crop.x ?? 0.5} min={0} max={1} step={0.01} onChange={(v) => patchCrop({ x: v })} />
            <SliderRow label={t("metadata.rowCropY")} value={crop.y ?? 0.5} min={0} max={1} step={0.01} onChange={(v) => patchCrop({ y: v })} />
            <SliderRow label={t("metadata.rowZoom")} value={crop.zoom ?? 1} min={1} max={2} step={0.01} onChange={(v) => patchCrop({ zoom: v })} />
            {!lipsync && (
              <>
                <div className="label-tiny">{t("metadata.shotTrimTitle")}</div>
                <NumRow label={t("metadata.rowTrimIn")} value={trim.in ?? 0} step={0.1}
                  onChange={(v) => cb.patchShot(cueId, s.id, { trim: { ...trim, in: Math.max(0, v) } })} />
                <NumRow label={t("metadata.rowTrimOut")} value={trim.out ?? 0} step={0.1}
                  onChange={(v) => cb.patchShot(cueId, s.id, { trim: v > 0 ? { ...trim, out: v } : { ...trim, out: undefined } })} />
              </>
            )}
            <label className="flex items-center justify-between text-[12px]">
              <span className="label-tiny">{t("metadata.rowJank")}</span>
              <input type="checkbox" checked={s.jank !== false}
                onChange={(e) => cb.patchShot(cueId, s.id, { jank: e.target.checked })} />
            </label>
            <Rows rows={[
              [t("metadata.rowKind"), s.kind],
              [t("metadata.rowCue"), cueId],
              [t("metadata.rowModel"), s.model ?? t("metadata.episodeDefault")],
              [t("metadata.rowFile"), `clips/hf_${s.id}.mp4`],
            ]} dim note={s.prompt} />
            <div className="text-txt-faint text-[11px]">{t("metadata.shotEditHint")}</div>
          </>
        );
      })()}

      {sel?.t === "overlay" && (
        <>
          <Head asset={sel.ov.asset} slug={cb.slug} onDelete={() => cb.removeOverlay(sel.idx)} />
          <SelectRow label={t("metadata.rowMode")} value={sel.ov.mode}
            options={[["insert", t("metadata.modeInsert")], ["overlay", t("metadata.modeOverlay")]]}
            onChange={(v) => cb.patchOverlay(sel.idx, { mode: v as OverlayMode })} />
          {sel.ov.mode === "overlay" && (
            <>
              <SelectRow label={t("metadata.rowPosition")} value={sel.ov.position ?? "lower_third"}
                options={POSITIONS.map((p) => [p, p] as [string, string])}
                onChange={(v) => cb.patchOverlay(sel.idx, { position: v as OverlayPosition })} />
              <NumRow label={t("metadata.rowScale")} value={sel.ov.scale ?? 1} step={0.05} onChange={(v) => cb.patchOverlay(sel.idx, { scale: v })} />
              <NumRow label={t("metadata.rowOpacity")} value={sel.ov.opacity ?? 1} step={0.05} onChange={(v) => cb.patchOverlay(sel.idx, { opacity: v })} />
            </>
          )}
          <NumRow label={t("metadata.rowFadeIn")} value={sel.ov.fade_in ?? 0} step={0.1} onChange={(v) => cb.patchOverlay(sel.idx, { fade_in: v })} />
          <NumRow label={t("metadata.rowFadeOut")} value={sel.ov.fade_out ?? 0} step={0.1} onChange={(v) => cb.patchOverlay(sel.idx, { fade_out: v })} />
          <Rows rows={[
            [t("metadata.rowAnchor"), sel.ov.anchor_cue],
            [t("metadata.rowStartOffset"), (sel.ov.start_offset ?? 0).toFixed(2)],
            [t("metadata.rowDuration"), `${(sel.ov.duration ?? 0).toFixed(2)}s`],
          ]} dim />
        </>
      )}

      {sel?.t === "sfx" && (
        <>
          <div className="flex items-center gap-2">
            <span className="text-cyan">♪</span>
            <span className="font-mono text-[12px] flex-1 truncate">{sel.e.file}</span>
            <button className="btn p-1" title={t("metadata.removeFromTimeline")} onClick={() => cb.removeSfx(sel.idx)}><IX /></button>
          </div>
          <NumRow label={t("metadata.rowGain")} value={sel.e.gain ?? 0.4} step={0.05} onChange={(v) => cb.patchSfx(sel.idx, { gain: v })} />
          <NumRow label={t("metadata.rowDelay")} value={sel.e.delay ?? 0} step={0.1} onChange={(v) => cb.patchSfx(sel.idx, { delay: v })} />
          <Rows rows={[
            [t("metadata.rowCue"), sel.e.cue ?? "—"],
            [t("metadata.rowAt"), sel.e.at],
            [t("metadata.rowSource"), sel.e.source ?? "—"],
          ]} dim />
        </>
      )}

      {sel?.t === "bed" && (
        <>
          <div className="flex items-center gap-2">
            <span className="text-[#b48bff]">♫</span>
            <span className="font-mono text-[12px] flex-1 truncate">{sel.b.name || sel.b.file || t("metadata.bedFallback")}</span>
            <button className="btn p-1" title={t("metadata.removeFromTimeline")} onClick={() => cb.removeBed(sel.idx)}><IX /></button>
          </div>
          <NumRow label={t("metadata.rowMaxSeconds")} value={sel.b.max_seconds ?? 0} step={1} onChange={(v) => cb.patchBed(sel.idx, { max_seconds: v })} />
          <NumRow label={t("metadata.rowGain")} value={sel.b.gain ?? 0.5} step={0.05} onChange={(v) => cb.patchBed(sel.idx, { gain: v })} />
          <NumRow label={t("metadata.rowFadeIn")} value={sel.b.fade_in ?? 0} step={0.1} onChange={(v) => cb.patchBed(sel.idx, { fade_in: v })} />
          <NumRow label={t("metadata.rowFadeOut")} value={sel.b.fade_out ?? 0} step={0.1} onChange={(v) => cb.patchBed(sel.idx, { fade_out: v })} />
          <Rows rows={[
            [t("metadata.rowFile"), sel.b.file ?? t("metadata.bedTheme")],
            [t("metadata.rowCues"), (sel.b.cues || []).join(", ") || "—"],
            [t("metadata.rowAnchor"), sel.b.anchor ?? "start"],
          ]} dim />
        </>
      )}

      {sel?.t === "lib" && (
        <>
          <div className="flex items-center gap-2">
            {sel.kind === "card" ? (
              <video src={mediaUrl.titlePreview(cb.slug, sel.item.file)} muted loop autoPlay playsInline className="bg-black rounded" style={{ width: 40, height: 40, objectFit: "contain" }} />
            ) : <span className="text-cyan">{sel.kind === "music" ? "♫" : "♪"}</span>}
            <span className="font-mono text-[12px] flex-1 truncate">{sel.item.file}</span>
          </div>
          <Rows rows={[
            [t("metadata.rowKind"), sel.kind === "card" ? t("metadata.kindGraphicsCard") : sel.kind],
            [t("metadata.rowDuration"), sel.item.duration_s != null ? `${sel.item.duration_s}s` : "—"],
            [t("metadata.rowSource"), sel.item.source ?? "—"],
            [t("metadata.rowLicense"), sel.item.license ?? "—"],
          ]} />
          {sel.item.notes && <div className="text-txt-faint text-[11px] whitespace-pre-wrap">{sel.item.notes}</div>}
          <div className="text-txt-faint text-[11px]">
            {t("metadata.libDragHint", {
              track: sel.kind === "card"
                ? t("metadata.trackGraphics")
                : sel.kind === "music"
                  ? t("metadata.trackMusic")
                  : t("metadata.trackSfx"),
            })}
          </div>
        </>
      )}
    </section>
  );
}

function Head({ asset, slug, onDelete }: { asset: string; slug: string; onDelete: () => void }) {
  const t = useT();
  return (
    <div className="flex items-center gap-2">
      <video src={mediaUrl.titlePreview(slug, asset)} muted loop autoPlay playsInline className="bg-black rounded" style={{ width: 40, height: 40, objectFit: "contain" }} />
      <span className="font-mono text-[12px] flex-1 truncate">{asset}</span>
      <button className="btn p-1" title={t("metadata.removeFromTimeline")} onClick={onDelete}><IX /></button>
    </div>
  );
}

function Rows({ rows, note, dim }: { rows: [string, string][]; note?: string; dim?: boolean }) {
  return (
    <>
      <div className={"grid grid-cols-2 gap-1 text-[11px] " + (dim ? "text-txt-faint" : "")}>
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <span className="label-tiny">{k}</span>
            <span className="font-mono truncate" title={v}>{v}</span>
          </div>
        ))}
      </div>
      {note && <div className="text-txt-dim text-[12px] whitespace-pre-wrap mt-1">{note}</div>}
    </>
  );
}

function SliderRow({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-2 text-[12px]">
      <span className="label-tiny w-16 flex-none">{label}</span>
      <input className="flex-1" type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Math.round(parseFloat(e.target.value) * 100) / 100)} />
      <span className="font-mono w-10 text-right">{value.toFixed(2)}</span>
    </label>
  );
}

function NumRow({ label, value, step, onChange }: { label: string; value: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="flex items-center justify-between text-[12px]">
      <span className="label-tiny">{label}</span>
      <input className="input w-24 text-[12px] py-0.5" type="number" step={step} value={value}
        onChange={(e) => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) onChange(Math.round(v * 100) / 100); }} />
    </label>
  );
}

function SelectRow({ label, value, options, onChange }: { label: string; value: string | undefined; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center justify-between text-[12px]">
      <span className="label-tiny">{label}</span>
      <select className="input text-[12px] py-0.5" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}
