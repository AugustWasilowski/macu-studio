import { useT } from "../i18n";
import { mediaUrl } from "../api";
import type { MusicBed, SfxEntry } from "../api/library";
import { IX } from "../components/Icons";
import type { Overlay, OverlayMode, OverlayPosition } from "../types";
import type { Selection } from "./trackEditor";

const POSITIONS: OverlayPosition[] = ["lower_third", "bug_tl", "bug_tr", "center", "full"];

export interface MetaCallbacks {
  slug: string;
  patchOverlay: (idx: number, p: Partial<Overlay>) => void;
  removeOverlay: (idx: number) => void;
  patchSfx: (idx: number, p: Partial<SfxEntry>) => void;
  removeSfx: (idx: number) => void;
  patchBed: (idx: number, p: Partial<MusicBed>) => void;
  removeBed: (idx: number) => void;
}

export function MetadataPanel({ sel, cb, overlays, beds, sfx }: {
  sel: Selection | null;
  cb: MetaCallbacks;
  overlays: Overlay[];
  beds: MusicBed[];
  sfx: SfxEntry[];
}) {
  const t = useT();
  // Read the live item by index so edit inputs reflect the current manifest, not
  // the (possibly stale) snapshot captured when the clip was selected.
  if (sel?.t === "overlay") sel = { ...sel, ov: overlays[sel.idx] ?? sel.ov };
  if (sel?.t === "bed") sel = { ...sel, b: beds[sel.idx] ?? sel.b };
  if (sel?.t === "sfx") sel = { ...sel, e: sfx[sel.idx] ?? sel.e };
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
