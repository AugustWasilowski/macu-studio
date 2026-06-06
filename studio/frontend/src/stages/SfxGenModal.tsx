import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import type { SfxProposal, SfxProposalEntry } from "../api";
import { useStore } from "../store";
import { Modal } from "../components/Modal";
import { IX } from "../components/Icons";

/** Review modal for LLM-proposed sound-effect lists. Calls /sfx/generate on open (slow —
 * the local LLM cold-starts), reads the script as a radio play, shows the SFX it wants to
 * place (favoring the existing kit, flagging any that need acquiring) with editable gain /
 * acquire-query and per-row remove, then /sfx/apply on confirm. Applied effects land in
 * manifest.sfx[] in the same shape as a drag-drop, so they appear in the Audio timeline. */
export function SfxGenModal({ slug, open, onClose }: { slug: string; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const [phase, setPhase] = useState<"loading" | "review" | "applying" | "error">("loading");
  const [err, setErr] = useState("");
  const [p, setP] = useState<SfxProposal | null>(null);

  useEffect(() => {
    if (!open) return;
    setPhase("loading"); setErr(""); setP(null);
    let alive = true;
    api.generateSfx(slug)
      .then((res) => { if (alive) { setP(res); setPhase("review"); } })
      .catch((e: Error) => { if (alive) { setErr(e.message); setPhase("error"); } });
    return () => { alive = false; };
  }, [open, slug]);

  const editEntry = (idx: number, patch: Partial<SfxProposalEntry>) =>
    setP((pp) => pp && ({ ...pp, sfx: pp.sfx.map((e, i) => (i === idx ? { ...e, ...patch } : e)) }));
  const removeEntry = (idx: number) =>
    setP((pp) => pp && ({ ...pp, sfx: pp.sfx.filter((_, i) => i !== idx) }));

  const apply = async () => {
    if (!p) return;
    setPhase("applying");
    try {
      const r = await api.applySfx(slug, p);
      const acq = r.acquire.length ? `, ${r.acquire.length} to acquire` : "";
      push(`SFX list applied — ${r.placed} placed (${r.reused} from library${acq})`, "ok");
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["assets", "sfx"] });
      onClose();
    } catch (e: any) {
      push("apply failed: " + (e?.message ?? "error"), "err");
      setPhase("review");
    }
  };

  const entries = p?.sfx ?? [];
  const reuse = entries.map((e, i) => ({ e, i })).filter((o) => !o.e.need);
  const acquire = entries.map((e, i) => ({ e, i })).filter((o) => o.e.need);

  return (
    <Modal open={open} onClose={onClose} width={720} title="GENERATE SFX LIST"
      footer={
        <>
          <button className="btn" onClick={onClose}>Close</button>
          <button className="btn btn-cyan" disabled={phase !== "review" || !p || entries.length === 0} onClick={apply}>
            {phase === "applying" ? "Applying…" : `Add ${entries.length} to timeline`}
          </button>
        </>
      }>
      {phase === "loading" && (
        <div className="text-txt-dim text-[13px] py-6 text-center">
          Asking the local LLM (Qwen2.5-7B) to read the script as a radio play…<br />
          <span className="text-txt-faint text-[11px]">starts Ollama on the GPU, ~30-60s</span>
        </div>
      )}
      {phase === "error" && (
        <div className="text-red text-[12px] whitespace-pre-wrap py-3">
          {err.includes("409") || err.toLowerCase().includes("busy")
            ? "GPU is busy — a render is active. Try again when it's idle."
            : `Generation failed: ${err}`}
        </div>
      )}
      {(phase === "review" || phase === "applying") && p && (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-3 gap-2 text-[12px]">
            <Stat label="opportunities" value={entries.length} />
            <Stat label="from library" value={reuse.length} />
            <Stat label="to acquire" value={acquire.length} accent={acquire.length > 0} />
          </div>

          {entries.length === 0 && (
            <div className="text-txt-faint text-[12px] py-3">No sound-effect opportunities found — the model judged the script needs none, or everything is already placed.</div>
          )}

          {reuse.length > 0 && (
            <Section title={`USING EXISTING SFX (${reuse.length}) — already in the kit`}>
              {reuse.map(({ e, i }) => <Row key={i} e={e} onGain={(g) => editEntry(i, { gain: g })} onRemove={() => removeEntry(i)} />)}
            </Section>
          )}

          {acquire.length > 0 && (
            <Section title={`NEEDS ACQUIRING (${acquire.length}) — edit the search, fetch later from the library`}>
              {acquire.map(({ e, i }) => (
                <div key={i} className="flex flex-col gap-1 mb-2 hairline-soft rounded px-2 py-1.5">
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-amber w-10 font-mono">{e.cue}</span>
                    <span className="text-txt-faint">{e.at}</span>
                    <span className="font-mono text-amber flex-1 truncate" title={e.file}>{e.file}</span>
                    <GainInput value={e.gain} onChange={(g) => editEntry(i, { gain: g })} />
                    <button className="btn p-0.5" title="drop this effect" onClick={() => removeEntry(i)}><IX /></button>
                  </div>
                  <label className="flex items-center gap-1 text-txt-faint text-[10px]">
                    freesound query
                    <input className="input flex-1 text-[11px] py-0 font-mono text-cyan" value={e.query}
                      onChange={(ev) => editEntry(i, { query: ev.target.value })} />
                  </label>
                  {e.reason && <div className="text-txt-faint text-[10px] italic pl-11">{e.reason}</div>}
                </div>
              ))}
            </Section>
          )}

          <p className="text-txt-faint text-[11px]">
            Apply inserts these into the audio timeline (manifest.sfx[]) exactly like a drag-drop —
            per-gap delays are auto-staggered. Library effects play immediately; “to acquire” effects
            are placeholders until you fetch them (Library → Add → Freesound) under the shown filename;
            a render skips any sound not yet on disk.
          </p>
        </div>
      )}
    </Modal>
  );
}

function Row({ e, onGain, onRemove }: { e: SfxProposalEntry; onGain: (g: number) => void; onRemove: () => void }) {
  return (
    <div className="flex flex-col gap-0.5 mb-1.5">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="text-amber w-10 font-mono">{e.cue}</span>
        <span className="text-txt-faint">{e.at}</span>
        <span className="font-mono text-cyan flex-1 truncate" title={e.file}>{e.file}</span>
        <GainInput value={e.gain} onChange={onGain} />
        <button className="btn p-0.5" title="drop this effect" onClick={onRemove}><IX /></button>
      </div>
      {e.reason && <div className="text-txt-faint text-[10px] italic pl-11">{e.reason}</div>}
    </div>
  );
}

function GainInput({ value, onChange }: { value: number; onChange: (g: number) => void }) {
  return (
    <label className="flex items-center gap-1 text-txt-faint text-[10px]" title="gain — 0–1 linear">
      g
      <input className="input w-16 text-[11px] py-0" type="number" step="0.05" value={value}
        onChange={(e) => { const v = parseFloat(e.target.value); onChange(Number.isFinite(v) ? v : 0.4); }} />
    </label>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="hairline-soft rounded px-2 py-1 flex items-center justify-between">
      <span className="label-tiny">{label}</span>
      <span className={"font-mono text-[14px] " + (accent ? "text-amber" : "text-cyan")}>{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="label-tiny mb-1">{title}</div>
      {children}
    </div>
  );
}
