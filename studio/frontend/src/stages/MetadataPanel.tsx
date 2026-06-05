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
  // Read the live item by index so edit inputs reflect the current manifest, not
  // the (possibly stale) snapshot captured when the clip was selected.
  if (sel?.t === "overlay") sel = { ...sel, ov: overlays[sel.idx] ?? sel.ov };
  if (sel?.t === "bed") sel = { ...sel, b: beds[sel.idx] ?? sel.b };
  if (sel?.t === "sfx") sel = { ...sel, e: sfx[sel.idx] ?? sel.e };
  return (
    <section className="panel p-3 flex flex-col gap-2 overflow-y-auto">
      <div className="panel-title">METADATA</div>
      {!sel && <div className="text-txt-faint text-[12px]">Select a clip on the timeline or an asset in the drawer.</div>}

      {sel?.t === "cue" && <Rows rows={[
        ["kind", "cue / video clip"],
        ["id", sel.cue.id],
        ["speaker", sel.cue.speaker || "—"],
        ["duration", sel.cue.duration_s != null ? `${sel.cue.duration_s.toFixed(2)}s` : "—"],
        ["segment", sel.cue.segment ?? "—"],
        ["shots", String(sel.cue.shots?.length ?? 0)],
        ["file", `vo/${sel.cue.id}.wav`],
      ]} note={sel.cue.text} />}

      {sel?.t === "overlay" && (
        <>
          <Head asset={sel.ov.asset} slug={cb.slug} onDelete={() => cb.removeOverlay(sel.idx)} />
          <SelectRow label="mode" value={sel.ov.mode}
            options={[["insert", "insert (full-frame)"], ["overlay", "overlay (on footage)"]]}
            onChange={(v) => cb.patchOverlay(sel.idx, { mode: v as OverlayMode })} />
          {sel.ov.mode === "overlay" && (
            <>
              <SelectRow label="position" value={sel.ov.position ?? "lower_third"}
                options={POSITIONS.map((p) => [p, p] as [string, string])}
                onChange={(v) => cb.patchOverlay(sel.idx, { position: v as OverlayPosition })} />
              <NumRow label="scale" value={sel.ov.scale ?? 1} step={0.05} onChange={(v) => cb.patchOverlay(sel.idx, { scale: v })} />
              <NumRow label="opacity" value={sel.ov.opacity ?? 1} step={0.05} onChange={(v) => cb.patchOverlay(sel.idx, { opacity: v })} />
            </>
          )}
          <NumRow label="fade in" value={sel.ov.fade_in ?? 0} step={0.1} onChange={(v) => cb.patchOverlay(sel.idx, { fade_in: v })} />
          <NumRow label="fade out" value={sel.ov.fade_out ?? 0} step={0.1} onChange={(v) => cb.patchOverlay(sel.idx, { fade_out: v })} />
          <Rows rows={[
            ["anchor", sel.ov.anchor_cue],
            ["start +s", (sel.ov.start_offset ?? 0).toFixed(2)],
            ["duration", `${(sel.ov.duration ?? 0).toFixed(2)}s`],
          ]} dim />
        </>
      )}

      {sel?.t === "sfx" && (
        <>
          <div className="flex items-center gap-2">
            <span className="text-cyan">♪</span>
            <span className="font-mono text-[12px] flex-1 truncate">{sel.e.file}</span>
            <button className="btn p-1" title="remove from timeline" onClick={() => cb.removeSfx(sel.idx)}><IX /></button>
          </div>
          <NumRow label="gain" value={sel.e.gain ?? 0.4} step={0.05} onChange={(v) => cb.patchSfx(sel.idx, { gain: v })} />
          <NumRow label="delay" value={sel.e.delay ?? 0} step={0.1} onChange={(v) => cb.patchSfx(sel.idx, { delay: v })} />
          <Rows rows={[
            ["cue", sel.e.cue ?? "—"],
            ["at", sel.e.at],
            ["source", sel.e.source ?? "—"],
          ]} dim />
        </>
      )}

      {sel?.t === "bed" && (
        <>
          <div className="flex items-center gap-2">
            <span className="text-[#b48bff]">♫</span>
            <span className="font-mono text-[12px] flex-1 truncate">{sel.b.name || sel.b.file || "bed"}</span>
            <button className="btn p-1" title="remove from timeline" onClick={() => cb.removeBed(sel.idx)}><IX /></button>
          </div>
          <NumRow label="max seconds" value={sel.b.max_seconds ?? 0} step={1} onChange={(v) => cb.patchBed(sel.idx, { max_seconds: v })} />
          <NumRow label="gain" value={sel.b.gain ?? 0.5} step={0.05} onChange={(v) => cb.patchBed(sel.idx, { gain: v })} />
          <NumRow label="fade in" value={sel.b.fade_in ?? 0} step={0.1} onChange={(v) => cb.patchBed(sel.idx, { fade_in: v })} />
          <NumRow label="fade out" value={sel.b.fade_out ?? 0} step={0.1} onChange={(v) => cb.patchBed(sel.idx, { fade_out: v })} />
          <Rows rows={[
            ["file", sel.b.file ?? "(theme)"],
            ["cues", (sel.b.cues || []).join(", ") || "—"],
            ["anchor", sel.b.anchor ?? "start"],
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
            ["kind", sel.kind === "card" ? "graphics card" : sel.kind],
            ["duration", sel.item.duration_s != null ? `${sel.item.duration_s}s` : "—"],
            ["source", sel.item.source ?? "—"],
            ["license", sel.item.license ?? "—"],
          ]} />
          {sel.item.notes && <div className="text-txt-faint text-[11px] whitespace-pre-wrap">{sel.item.notes}</div>}
          <div className="text-txt-faint text-[11px]">
            Drag onto the {sel.kind === "card" ? "GRAPHICS" : sel.kind === "music" ? "MUSIC" : "SFX"} track to place it.
          </div>
        </>
      )}
    </section>
  );
}

function Head({ asset, slug, onDelete }: { asset: string; slug: string; onDelete: () => void }) {
  return (
    <div className="flex items-center gap-2">
      <video src={mediaUrl.titlePreview(slug, asset)} muted loop autoPlay playsInline className="bg-black rounded" style={{ width: 40, height: 40, objectFit: "contain" }} />
      <span className="font-mono text-[12px] flex-1 truncate">{asset}</span>
      <button className="btn p-1" title="remove from timeline" onClick={onDelete}><IX /></button>
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
