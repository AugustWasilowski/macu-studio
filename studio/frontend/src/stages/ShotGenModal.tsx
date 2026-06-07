import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import type { ShotProposal } from "../api";
import { useStore } from "../store";
import { Modal } from "../components/Modal";
import { useT } from "../i18n";

/** Review modal for LLM-proposed shot lists. Calls /shots/generate on open (slow —
 * the local LLM cold-starts), shows new-vs-reused keys + per-cue plan with editable
 * new cores, then /shots/apply on confirm. */
export function ShotGenModal({ slug, open, onClose }: { slug: string; open: boolean; onClose: () => void }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const [phase, setPhase] = useState<"loading" | "review" | "applying" | "error">("loading");
  const [err, setErr] = useState("");
  const [p, setP] = useState<ShotProposal | null>(null);
  // Gap-fill by default: only plan cues that have no shots yet, so apply never clobbers
  // shots you've already tuned. Toggle off to re-plan the whole episode from scratch.
  const [onlyMissing, setOnlyMissing] = useState(true);

  useEffect(() => {
    if (!open) return;
    setPhase("loading"); setErr(""); setP(null);
    let alive = true;
    api.generateShots(slug, onlyMissing)
      .then((res) => { if (alive) { setP(res); setPhase("review"); } })
      .catch((e: Error) => { if (alive) { setErr(e.message); setPhase("error"); } });
    return () => { alive = false; };
  }, [open, slug, onlyMissing]);

  const editChar = (key: string, core: string) => setP((pp) => pp && ({ ...pp, characters: { ...pp.characters, [key]: { ...pp.characters[key], core } } }));
  const editBroll = (key: string, prompt: string) => setP((pp) => pp && ({ ...pp, broll: { ...pp.broll, [key]: { ...pp.broll[key], prompt } } }));

  const apply = async () => {
    if (!p) return;
    setPhase("applying");
    try {
      const r = await api.applyShots(slug, p);
      push(t("toast.shotApplied", { appliedCues: r.applied_cues, newChars: r.new_characters, newBroll: r.new_broll }), "ok");
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["shots", slug] });
      qc.invalidateQueries({ queryKey: ["cues", slug] });
      onClose();
    } catch (e: any) {
      push(t("toast.shotApplyFailed", { message: e?.message ?? "error" }), "err");
      setPhase("review");
    }
  };

  const s = p?.summary;
  const newChars = s?.new_characters ?? [];
  const newBroll = s?.new_broll ?? [];

  return (
    <Modal open={open} onClose={onClose} width={680} title={t("shotgen.title")}
      footer={
        <>
          <button className="btn" onClick={onClose}>{t("common.close")}</button>
          <button className="btn btn-cyan" disabled={phase !== "review" || !p || (p?.cues.length ?? 0) === 0} onClick={apply}>
            {phase === "applying" ? t("shotgen.applying") : t("shotgen.applyToManifest")}
          </button>
        </>
      }>
      <label className="flex items-center gap-2 text-[11px] text-txt-dim mb-3 cursor-pointer select-none"
        title={t("shotgen.onlyMissingTooltip")}>
        <input type="checkbox" checked={onlyMissing} disabled={phase === "loading" || phase === "applying"}
          onChange={(e) => setOnlyMissing(e.target.checked)} />
        {t("shotgen.onlyMissingLabel")} <span className="text-txt-faint">{t("shotgen.onlyMissingHint")}</span>
      </label>
      {phase === "loading" && (
        <div className="text-txt-dim text-[13px] py-6 text-center">
          {t("shotgen.loadingMain")}<br />
          <span className="text-txt-faint text-[11px]">{t("shotgen.loadingSub")}</span>
        </div>
      )}
      {phase === "error" && (
        <div className="text-red text-[12px] whitespace-pre-wrap py-3">
          {err.includes("409") || err.toLowerCase().includes("busy")
            ? t("shotgen.errorGpuBusy")
            : t("shotgen.errorGenFailed", { err })}
        </div>
      )}
      {(phase === "review" || phase === "applying") && p && p.cues.length === 0 && (
        <div className="text-txt-dim text-[12px] py-4">
          {onlyMissing
            ? t("shotgen.emptyAllFilled")
            : t("shotgen.emptyNoShots")}
        </div>
      )}
      {(phase === "review" || phase === "applying") && p && p.cues.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2 text-[12px]">
            <Stat label={t("shotgen.statCuesPlanned")} value={s!.cues_planned} />
            <Stat label={t("shotgen.statReusedChars")} value={s!.reused_characters.length} />
            <Stat label={t("shotgen.statNewChars")} value={newChars.length} accent={newChars.length > 0} />
            <Stat label={t("shotgen.statNewBroll")} value={newBroll.length} accent={newBroll.length > 0} />
          </div>

          {newChars.length > 0 && (
            <Section title={t("shotgen.sectionNewChars")}>
              {newChars.map((k) => (
                <div key={k} className="flex flex-col gap-1 mb-2">
                  <div className="flex items-center gap-2"><span className="font-mono text-amber text-[12px]">{k}</span><span className="text-txt-faint text-[10px]">{t("shotgen.seedLabel", { seed: p.characters[k]?.seed ?? "—" })}</span></div>
                  <textarea className="input text-[12px]" style={{ minHeight: 48 }} value={p.characters[k]?.core ?? ""} onChange={(e) => editChar(k, e.target.value)} />
                </div>
              ))}
            </Section>
          )}
          {newBroll.length > 0 && (
            <Section title={t("shotgen.sectionNewBroll")}>
              {newBroll.map((k) => (
                <div key={k} className="flex flex-col gap-1 mb-2">
                  <span className="font-mono text-cyan text-[12px]">{k}</span>
                  <textarea className="input text-[12px]" style={{ minHeight: 40 }} value={p.broll[k]?.prompt ?? ""} onChange={(e) => editBroll(k, e.target.value)} />
                </div>
              ))}
            </Section>
          )}
          {s!.reused_characters.length > 0 && (
            <Section title={t("shotgen.sectionReusedChars", { count: s!.reused_characters.length })}>
              <div className="flex flex-wrap gap-1">{s!.reused_characters.map((k) => <span key={k} className="hairline-soft rounded px-1.5 py-0.5 font-mono text-[11px] text-txt-dim">{k}</span>)}</div>
            </Section>
          )}

          <Section title={t("shotgen.sectionPerCue")}>
            <div className="max-h-[200px] overflow-y-auto text-[11px] font-mono">
              {p.cues.map((c) => (
                <div key={c.cue_id} className="flex gap-2 py-0.5 border-b border-[var(--line-soft)]">
                  <span className="text-amber w-10">{c.cue_id}</span>
                  <span className="flex-1 text-txt-dim truncate">{c.shots.map((sh) => `${sh.kind === "broll" ? "▦" : "●"}${sh.who}`).join("  ")}</span>
                </div>
              ))}
            </div>
          </Section>
          <p className="text-txt-faint text-[11px]">{t("shotgen.applyFootnote")}</p>
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
