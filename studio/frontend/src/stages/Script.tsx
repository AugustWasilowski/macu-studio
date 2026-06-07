import { useEffect, useState, type ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type GenManifestSummary, type ScriptVersion, type ScriptDiffLine } from "../api";
import { useStore } from "../store";
import { Modal } from "../components/Modal";
import { Markdown } from "../components/Markdown";
import { useT, t as tFn } from "../i18n";
import { Trans } from "../i18n/Trans";

const WPM = 150;

export function Script({ slug }: { slug: string }) {
  const t = useT();
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);

  const scriptQ = useQuery({
    queryKey: ["script", slug],
    queryFn: () => api.script(slug),
  });

  const [text, setText] = useState("");
  const [mode, setMode] = useState<"edit" | "preview" | "diff">("preview");
  // script-text font size (script body only, not the rest of the UI); persisted
  const [fontPx, setFontPx] = useState(() => {
    const v = Number(localStorage.getItem("macu.script.fontPx"));
    return v >= 9 && v <= 28 ? v : 13;
  });
  const bumpFont = (d: number) => setFontPx((p) => {
    const n = Math.max(9, Math.min(28, p + d));
    localStorage.setItem("macu.script.fontPx", String(n));
    return n;
  });
  const [saved, setSaved] = useState(true);
  const [gen, setGen] = useState<GenManifestSummary | null>(null);

  useEffect(() => {
    if (scriptQ.data) {
      setText(scriptQ.data.text);
      setSaved(true);
    }
  }, [scriptQ.data]);

  const saveMut = useMutation({
    mutationFn: () => api.putScript(slug, text),
    onSuccess: () => {
      setSaved(true);
      push(t("toast.scriptSaved"), "ok");
      qc.invalidateQueries({ queryKey: ["script", slug] });
    },
    onError: (e: Error) => push("save failed: " + e.message, "err"),
  });

  // Generate manifest from script — dry-run preview first
  const genMut = useMutation({
    mutationFn: async () => {
      if (!saved) await saveMut.mutateAsync();
      return api.genManifest(slug, false);
    },
    onSuccess: (r) => setGen(r.summary),
    onError: (e: Error) => push("generate failed: " + e.message, "err"),
  });

  // Apply the generated manifest (writes manifest.json + .bak)
  const applyMut = useMutation({
    mutationFn: () => api.genManifest(slug, true),
    onSuccess: (r) => {
      const s = r.summary;
      push(t("toast.manifestWritten", { cues: s.new_cue_count, added: s.cues_added, reshot: s.cues_reshot }), "ok");
      setGen(null);
      qc.invalidateQueries({ queryKey: ["manifest", slug] });
      qc.invalidateQueries({ queryKey: ["cues", slug] });
    },
    onError: (e: Error) => push("apply failed: " + e.message, "err"),
  });

  // Ctrl/Cmd+S
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (!saved) saveMut.mutate();
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [saved, saveMut]);

  const cueCount = (text.match(/\[CUE/gi) || []).length;
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  const runtime = Math.round((words / WPM) * 60);
  const mm = String(Math.floor(runtime / 60)).padStart(2, "0");
  const ss = String(runtime % 60).padStart(2, "0");

  return (
    <div className="flex h-full">
      <section className="panel flex flex-col flex-1 min-w-0">
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">
            SCRIPT <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ episodes/{slug}/script.md</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={"text-[11px] " + (saved ? "text-green" : "text-amber")}>
              {saved ? t("script.saved") : t("script.unsaved")}
            </span>
            <span className="inline-flex items-center gap-0.5 mr-1" title={t("script.fontSizeTitle")}>
              <button className="btn px-1.5 py-0.5" onClick={() => bumpFont(-1)}>A−</button>
              <span className="text-txt-faint text-[10px] w-6 text-center tabular-nums">{fontPx}</span>
              <button className="btn px-1.5 py-0.5" onClick={() => bumpFont(1)}>A+</button>
            </span>
            <button className={"btn " + (mode === "edit" ? "btn-amber" : "")} onClick={() => setMode("edit")}>{t("script.modeEdit")}</button>
            <button className={"btn " + (mode === "preview" ? "btn-amber" : "")} onClick={() => setMode("preview")}>{t("script.modePreview")}</button>
            <button className={"btn " + (mode === "diff" ? "btn-amber" : "")} onClick={() => setMode("diff")} title={t("script.modeDiffTitle")}>{t("script.modeDiff")}</button>
            <button
              className="btn"
              disabled={saved || saveMut.isPending}
              onClick={() => saveMut.mutate()}
            >
              {saveMut.isPending ? t("script.saving") : t("common.save")}
            </button>
            <button
              className="btn btn-cyan"
              disabled={genMut.isPending}
              title={t("script.generateTitle")}
              onClick={() => genMut.mutate()}
            >
              {genMut.isPending ? t("script.readingScript") : t("script.generateManifest")}
            </button>
          </div>
        </header>
        <div className="flex-1 min-h-0">
          {mode === "preview" ? (
            <div className="h-full overflow-y-auto p-4 leading-relaxed" style={{ fontSize: fontPx }}>
              <ScriptPreview text={text} />
            </div>
          ) : mode === "diff" ? (
            <DiffView slug={slug} fontPx={fontPx} />
          ) : (
            <textarea
              className="w-full h-full p-3 font-mono bg-[#0b0b0a] text-txt resize-none outline-none border-0"
              style={{ fontSize: fontPx }}
              spellCheck={false}
              value={text}
              onChange={(e) => { setText(e.target.value); setSaved(false); }}
              onBlur={() => { if (!saved) saveMut.mutate(); }}
            />
          )}
        </div>
        <footer className="flex items-center gap-3 px-3 py-1.5 border-t hairline">
          <span className="seg-readout">{String(cueCount).padStart(2, "0")} {t("script.cues", { count: cueCount })}</span>
          <span className="seg-readout cyan">{mm}:{ss} <span className="text-txt-faint">{t("script.estRuntime")}</span></span>
          <span className="label-tiny">{t("script.words", { count: words })}</span>
          <span className="label-tiny ml-auto">{t("script.encoding")}</span>
        </footer>
      </section>

      <GenManifestModal
        summary={gen}
        onClose={() => setGen(null)}
        onApply={() => applyMut.mutate()}
        applying={applyMut.isPending}
      />
    </div>
  );
}

function GenManifestModal({
  summary, onClose, onApply, applying,
}: {
  summary: GenManifestSummary | null;
  onClose: () => void;
  onApply: () => void;
  applying: boolean;
}) {
  const t = useT();
  const s = summary;
  const noChange = !!s && s.cues_added === 0 && s.cues_reshot === 0 && !s.renumbered;
  return (
    <Modal
      open={!!s}
      onClose={onClose}
      title={<>{t("script.modalTitle")} <span className="text-cyan ml-2 text-[10px]">{t("script.modalTitleSub")}</span></>}
      width={560}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={applying}>{t("common.cancel")}</button>
          <button className="btn btn-amber" onClick={onApply} disabled={applying || noChange}>
            {applying ? t("script.writing") : noChange ? t("script.noChanges") : t("script.applyManifest")}
          </button>
        </>
      }
    >
      {s && (
        <div className="flex flex-col gap-3 text-[13px]">
          <div className="flex items-center gap-3">
            <span className="seg-readout">{s.old_cue_count} → {s.new_cue_count} {t("script.cuesStat")}</span>
            <span className="label-tiny text-green">{s.cues_added} {t("script.cuesNew")}</span>
            <span className="label-tiny text-amber">{s.cues_reshot} {t("script.cuesReshot")}</span>
            {s.renumbered && <span className="label-tiny text-amber">{t("script.renumbered")}</span>}
          </div>

          <p className="text-txt-dim text-[12px]">
            <Trans k="script.mergeHelp" tags={[(c) => <code key="0">{c}</code>, (c) => <code key="1">{c}</code>]} />
          </p>

          {s.unmapped_speakers.length > 0 && (
            <div className="rounded-[3px] p-2" style={{ background: "rgba(245,166,35,0.08)", borderLeft: "2px solid var(--amber)" }}>
              <div className="label-tiny text-amber mb-1">{t("script.unmappedLabel")}</div>
              <div className="text-[12px]">{s.unmapped_speakers.join(", ")}</div>
              <div className="label-tiny text-txt-faint mt-1">{t("script.unmappedHint")}</div>
            </div>
          )}

          {s.warnings.length > 0 && (
            <div className="rounded-[3px] p-2 max-h-32 overflow-y-auto" style={{ background: "rgba(255,122,89,0.06)", borderLeft: "2px solid #ff7a59" }}>
              <div className="label-tiny mb-1" style={{ color: "#ff7a59" }}>{t("script.warningsLabel", { count: s.warnings.length })}</div>
              {s.warnings.map((w, i) => <div key={i} className="text-[12px] text-txt-dim">{w}</div>)}
            </div>
          )}

          {s.changes.length > 0 ? (
            <div className="max-h-48 overflow-y-auto flex flex-col gap-1">
              <div className="label-tiny">{t("script.changedCues")}</div>
              {s.changes.map((c) => (
                <div key={c.id} className="flex items-baseline gap-2 text-[12px]">
                  <span className="seg-readout" style={{ minWidth: 38 }}>{c.id}</span>
                  <span className={c.type === "added" ? "text-green" : "text-amber"} style={{ minWidth: 48 }}>{c.type}</span>
                  <span className="text-txt-dim" style={{ minWidth: 60 }}>{c.speaker}</span>
                  <span className="text-txt-faint truncate">{c.vo}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-txt-faint text-[12px]">{t("script.noChangesDetail")}</div>
          )}
        </div>
      )}
    </Modal>
  );
}

// Thin wrapper kept for call sites; rendering now lives in the shared Markdown
// component (components/Markdown.tsx).
function ScriptPreview({ text }: { text: string }) {
  return <Markdown text={text} />;
}

// ---- Diff mode: step through synced versions (git) + the live working copy ----

function vlabel(v: ScriptVersion, t: typeof tFn): string {
  if (v.kind === "working") return t("script.workingCopy");
  const when = v.iso
    ? new Date(v.iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : "";
  return `${when}${v.short ? "  ·  " + v.short : ""}`;
}

function Pad({ children }: { children: ReactNode }) {
  return <div className="p-4 text-[12px] text-txt-faint">{children}</div>;
}

function DiffView({ slug, fontPx }: { slug: string; fontPx: number }) {
  const t = useT();
  const versionsQ = useQuery({
    queryKey: ["scriptVersions", slug],
    queryFn: () => api.scriptVersions(slug),
  });
  const versions = versionsQ.data?.versions ?? [];
  // i = the NEWER version in the pair; compared against versions[i+1] (older).
  const [i, setI] = useState(0);
  useEffect(() => { setI(0); }, [slug, versions.length]);

  const target = versions[i];
  const base = versions[i + 1];
  const diffQ = useQuery({
    queryKey: ["scriptDiff", slug, base?.id, target?.id],
    queryFn: () => api.scriptDiff(slug, base!.id, target!.id),
    enabled: !!base && !!target,
  });

  if (versionsQ.isLoading) return <Pad>{t("script.loadingVersions")}</Pad>;
  if (versions.length === 0)
    return <Pad>{t("script.noVersionsYet")}</Pad>;
  if (versions.length === 1)
    return <Pad>{t("script.oneVersionOnly", { label: vlabel(versions[0], t) })}</Pad>;

  const d = diffQ.data;
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-3 py-2 border-b hairline text-[12px]">
        <button className="btn" disabled={i >= versions.length - 2}
          onClick={() => setI((n) => Math.min(versions.length - 2, n + 1))} title={t("script.olderComparison")}>◀</button>
        <button className="btn" disabled={i <= 0}
          onClick={() => setI((n) => Math.max(0, n - 1))} title={t("script.newerComparison")}>▶</button>
        <span className="text-txt-dim truncate">{vlabel(base, t)}</span>
        <span className="text-txt-faint">→</span>
        <span className="text-txt truncate">{vlabel(target, t)}</span>
        {d && (
          <span className="ml-auto flex gap-2 shrink-0">
            <span style={{ color: "#8fd19e" }}>+{d.added}</span>
            <span style={{ color: "#e08c8c" }}>−{d.removed}</span>
          </span>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto font-mono leading-[1.55]" style={{ fontSize: fontPx }}>
        {diffQ.isLoading && <Pad>{t("script.computingDiff")}</Pad>}
        {d && d.lines.length === 0 && <Pad>{t("script.noDiffChanges")}</Pad>}
        {d && d.lines.map((ln, idx) => <DiffLine key={idx} line={ln} />)}
      </div>
    </div>
  );
}

function DiffLine({ line }: { line: ScriptDiffLine }) {
  if (line.tag === "hunk")
    return <div className="px-3 py-1 select-none" style={{ color: "#6aa0c0", background: "#0e0e0d" }}>{line.text}</div>;
  const cfg =
    line.tag === "add" ? { bg: "rgba(70,160,90,0.16)", sym: "+", col: "#8fd19e", txt: "var(--txt)" }
    : line.tag === "del" ? { bg: "rgba(200,70,70,0.16)", sym: "−", col: "#e08c8c", txt: "var(--txt)" }
    : { bg: "transparent", sym: " ", col: "#6b6b66", txt: "#9a9a93" };
  return (
    <div className="px-3 whitespace-pre-wrap break-words" style={{ background: cfg.bg }}>
      <span className="select-none mr-2" style={{ color: cfg.col }}>{cfg.sym}</span>
      <span style={{ color: cfg.txt }}>{line.text || " "}</span>
    </div>
  );
}
