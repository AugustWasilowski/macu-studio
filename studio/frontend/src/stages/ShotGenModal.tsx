import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import type { ShotProposal } from "../api";
import { useStore } from "../store";
import { Modal } from "../components/Modal";

/** Review modal for LLM-proposed shot lists. Calls /shots/generate on open (slow —
 * the local LLM cold-starts), shows new-vs-reused keys + per-cue plan with editable
 * new cores, then /shots/apply on confirm. */
export function ShotGenModal({ slug, open, onClose }: { slug: string; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const [phase, setPhase] = useState<"loading" | "review" | "applying" | "error">("loading");
  const [err, setErr] = useState("");
  const [p, setP] = useState<ShotProposal | null>(null);

  useEffect(() => {
    if (!open) return;
    setPhase("loading"); setErr(""); setP(null);
    let alive = true;
    api.generateShots(slug)
      .then((res) => { if (alive) { setP(res); setPhase("review"); } })
      .catch((e: Error) => { if (alive) { setErr(e.message); setPhase("error"); } });
    return () => { alive = false; };
  }, [open, slug]);

  const editChar = (key: string, core: string) => setP((pp) => pp && ({ ...pp, characters: { ...pp.characters, [key]: { ...pp.characters[key], core } } }));
  const editBroll = (key: string, prompt: string) => setP((pp) => pp && ({ ...pp, broll: { ...pp.broll, [key]: { ...pp.broll[key], prompt } } }));

  const apply = async () => {
    if (!p) return;
    setPhase("applying");
    try {
      const r = await api.applyShots(slug, p);
      push(`shot list applied — ${r.applied_cues} cues, ${r.new_characters} new chars, ${r.new_broll} new broll`, "ok");
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["shots", slug] });
      qc.invalidateQueries({ queryKey: ["cues", slug] });
      onClose();
    } catch (e: any) {
      push("apply failed: " + (e?.message ?? "error"), "err");
      setPhase("review");
    }
  };

  const s = p?.summary;
  const newChars = s?.new_characters ?? [];
  const newBroll = s?.new_broll ?? [];

  return (
    <Modal open={open} onClose={onClose} width={680} title="GENERATE SHOT LIST"
      footer={
        <>
          <button className="btn" onClick={onClose}>Close</button>
          <button className="btn btn-cyan" disabled={phase !== "review" || !p} onClick={apply}>
            {phase === "applying" ? "Applying…" : "Apply to manifest"}
          </button>
        </>
      }>
      {phase === "loading" && (
        <div className="text-txt-dim text-[13px] py-6 text-center">
          Asking the local LLM (Qwen2.5-7B) to plan the shots…<br />
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
          <div className="grid grid-cols-2 gap-2 text-[12px]">
            <Stat label="cues planned" value={s!.cues_planned} />
            <Stat label="reused characters" value={s!.reused_characters.length} />
            <Stat label="new characters" value={newChars.length} accent={newChars.length > 0} />
            <Stat label="new b-roll" value={newBroll.length} accent={newBroll.length > 0} />
          </div>

          {newChars.length > 0 && (
            <Section title="NEW characters — minted (edit the core if you like)">
              {newChars.map((k) => (
                <div key={k} className="flex flex-col gap-1 mb-2">
                  <div className="flex items-center gap-2"><span className="font-mono text-amber text-[12px]">{k}</span><span className="text-txt-faint text-[10px]">seed {p.characters[k]?.seed ?? "—"}</span></div>
                  <textarea className="input text-[12px]" style={{ minHeight: 48 }} value={p.characters[k]?.core ?? ""} onChange={(e) => editChar(k, e.target.value)} />
                </div>
              ))}
            </Section>
          )}
          {newBroll.length > 0 && (
            <Section title="NEW b-roll — minted">
              {newBroll.map((k) => (
                <div key={k} className="flex flex-col gap-1 mb-2">
                  <span className="font-mono text-cyan text-[12px]">{k}</span>
                  <textarea className="input text-[12px]" style={{ minHeight: 40 }} value={p.broll[k]?.prompt ?? ""} onChange={(e) => editBroll(k, e.target.value)} />
                </div>
              ))}
            </Section>
          )}
          {s!.reused_characters.length > 0 && (
            <Section title={`REUSED characters (${s!.reused_characters.length})`}>
              <div className="flex flex-wrap gap-1">{s!.reused_characters.map((k) => <span key={k} className="hairline-soft rounded px-1.5 py-0.5 font-mono text-[11px] text-txt-dim">{k}</span>)}</div>
            </Section>
          )}

          <Section title="PER-CUE PLAN">
            <div className="max-h-[200px] overflow-y-auto text-[11px] font-mono">
              {p.cues.map((c) => (
                <div key={c.cue_id} className="flex gap-2 py-0.5 border-b border-[var(--line-soft)]">
                  <span className="text-amber w-10">{c.cue_id}</span>
                  <span className="flex-1 text-txt-dim truncate">{c.shots.map((sh) => `${sh.kind === "broll" ? "▦" : "●"}${sh.who}`).join("  ")}</span>
                </div>
              ))}
            </div>
          </Section>
          <p className="text-txt-faint text-[11px]">Apply overwrites each planned cue's shots[] and writes new character/b-roll defs. Reused keys keep their existing cores + seeds.</p>
        </div>
      )}
    </Modal>
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
