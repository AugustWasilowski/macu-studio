import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type GenManifestSummary } from "../api";
import { useStore } from "../store";
import { Modal } from "../components/Modal";

const WPM = 150;

export function Script({ slug }: { slug: string }) {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);

  const scriptQ = useQuery({
    queryKey: ["script", slug],
    queryFn: () => api.script(slug),
  });

  const [text, setText] = useState("");
  const [preview, setPreview] = useState(false);
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
      push("script.md saved", "ok");
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
      push(`manifest written — ${s.new_cue_count} cues (${s.cues_added} new, ${s.cues_reshot} reshot)`, "ok");
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
              {saved ? "● SAVED" : "○ UNSAVED"}
            </span>
            <button className={"btn " + (!preview ? "btn-amber" : "")} onClick={() => setPreview(false)}>Edit</button>
            <button className={"btn " + (preview ? "btn-amber" : "")} onClick={() => setPreview(true)}>Preview</button>
            <button
              className="btn"
              disabled={saved || saveMut.isPending}
              onClick={() => saveMut.mutate()}
            >
              {saveMut.isPending ? "Saving…" : "Save"}
            </button>
            <button
              className="btn btn-cyan"
              disabled={genMut.isPending}
              title="Re-parse script.md into manifest cues (preview before writing)"
              onClick={() => genMut.mutate()}
            >
              {genMut.isPending ? "Reading script…" : "Generate manifest"}
            </button>
          </div>
        </header>
        <div className="flex-1 min-h-0">
          {preview ? (
            <div className="h-full overflow-y-auto p-4 text-[13px] leading-relaxed">
              <ScriptPreview text={text} />
            </div>
          ) : (
            <textarea
              className="w-full h-full p-3 font-mono text-[13px] bg-[#0b0b0a] text-txt resize-none outline-none border-0"
              spellCheck={false}
              value={text}
              onChange={(e) => { setText(e.target.value); setSaved(false); }}
              onBlur={() => { if (!saved) saveMut.mutate(); }}
            />
          )}
        </div>
        <footer className="flex items-center gap-3 px-3 py-1.5 border-t hairline">
          <span className="seg-readout">{String(cueCount).padStart(2, "0")} CUES</span>
          <span className="seg-readout cyan">{mm}:{ss} <span className="text-txt-faint">EST RUNTIME</span></span>
          <span className="label-tiny">{words} words</span>
          <span className="label-tiny ml-auto">UTF-8 · markdown · LF</span>
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
  const s = summary;
  const noChange = !!s && s.cues_added === 0 && s.cues_reshot === 0 && !s.renumbered;
  return (
    <Modal
      open={!!s}
      onClose={onClose}
      title={<>GENERATE MANIFEST <span className="text-cyan ml-2 text-[10px]">● from script.md</span></>}
      width={560}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={applying}>Cancel</button>
          <button className="btn btn-amber" onClick={onApply} disabled={applying || noChange}>
            {applying ? "Writing…" : noChange ? "No changes" : "Apply — write manifest.json"}
          </button>
        </>
      }
    >
      {s && (
        <div className="flex flex-col gap-3 text-[13px]">
          <div className="flex items-center gap-3">
            <span className="seg-readout">{s.old_cue_count} → {s.new_cue_count} CUES</span>
            <span className="label-tiny text-green">{s.cues_added} new</span>
            <span className="label-tiny text-amber">{s.cues_reshot} reshot</span>
            {s.renumbered && <span className="label-tiny text-amber">⚠ renumbered (VO cache may rebuild)</span>}
          </div>

          <p className="text-txt-dim text-[12px]">
            Cues are re-parsed from <code>script.md</code> and merged in; voice profiles, character
            seeds, b-roll, comfyui/style/music and title assets are preserved. A timestamped
            <code> manifest.json.bak</code> is written before applying.
          </p>

          {s.unmapped_speakers.length > 0 && (
            <div className="rounded-[3px] p-2" style={{ background: "rgba(245,166,35,0.08)", borderLeft: "2px solid var(--amber)" }}>
              <div className="label-tiny text-amber mb-1">SPEAKERS WITH NO VOICE MAPPING</div>
              <div className="text-[12px]">{s.unmapped_speakers.join(", ")}</div>
              <div className="label-tiny text-txt-faint mt-1">Add them to voice.speaker_map (Manifest drawer) or those cues won't get VO.</div>
            </div>
          )}

          {s.warnings.length > 0 && (
            <div className="rounded-[3px] p-2 max-h-32 overflow-y-auto" style={{ background: "rgba(255,122,89,0.06)", borderLeft: "2px solid #ff7a59" }}>
              <div className="label-tiny mb-1" style={{ color: "#ff7a59" }}>WARNINGS ({s.warnings.length})</div>
              {s.warnings.map((w, i) => <div key={i} className="text-[12px] text-txt-dim">{w}</div>)}
            </div>
          )}

          {s.changes.length > 0 ? (
            <div className="max-h-48 overflow-y-auto flex flex-col gap-1">
              <div className="label-tiny">CHANGED CUES</div>
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
            <div className="text-txt-faint text-[12px]">Script matches the manifest — nothing to write.</div>
          )}
        </div>
      )}
    </Modal>
  );
}

function ScriptPreview({ text }: { text: string }) {
  const lines = useMemo(() => text.split("\n"), [text]);
  return (
    <>
      {lines.map((line, i) => {
        const cue = line.match(/^\[CUE\s+([\w\-]+)\s*\/\s*([^\]]+)\]/i);
        if (cue) {
          const color = colorForSpeaker(cue[2].trim());
          return (
            <div
              key={i}
              className="flex items-baseline gap-2 my-1 pl-2 py-1 rounded-[3px]"
              style={{ borderLeft: `3px solid ${color}`, background: `${color}10` }}
            >
              <span className="text-amber font-bold text-[12px] tracking-wider">CUE {cue[1]}</span>
              <span className="text-[12px]" style={{ color }}>{cue[2].trim()}</span>
            </div>
          );
        }
        if (line.startsWith("# ")) return <h1 key={i} className="text-amber font-bold text-xl mt-3 mb-1" style={{ textShadow: "var(--glow-amber)" }}>{line.slice(2)}</h1>;
        if (line.startsWith("## ")) return <h2 key={i} className="text-amber font-semibold text-base mt-2 mb-1">{line.slice(3)}</h2>;
        if (line.startsWith("> ")) return <blockquote key={i} className="border-l-2 border-[var(--line-soft)] pl-2 my-1 text-txt-dim italic">{line.slice(2)}</blockquote>;
        if (!line.trim()) return <div key={i} className="h-2" />;
        return <p key={i} className="my-1">{line}</p>;
      })}
    </>
  );
}

function colorForSpeaker(name: string): string {
  if (!name) return "#938d82";
  const palette = ["#f5a623", "#00e5ff", "#33ff66", "#c08bff", "#ff7a59", "#9ad6ff", "#ffd166", "#7cc97a"];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return palette[Math.abs(h) % palette.length];
}
