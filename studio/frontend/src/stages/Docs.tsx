import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { docsApi, type DocSummary, type DocScope } from "../api/docs";
import { useStore } from "../store";
import { Markdown } from "../components/Markdown";

interface Sel { name: string; scope: DocScope; }

export function Docs() {
  const qc = useQueryClient();
  const push = useStore((s) => s.pushToast);
  const activeShow = useStore((s) => s.activeShow);

  const listQ = useQuery({
    queryKey: ["docs", activeShow],
    queryFn: () => docsApi.list(activeShow),
  });
  const docs = listQ.data?.docs ?? [];

  const [sel, setSel] = useState<Sel | null>(null);
  const [text, setText] = useState("");
  const [saved, setSaved] = useState(true);
  const [preview, setPreview] = useState(false);

  // Switching shows reloads the list; drop the selection so we re-pick.
  useEffect(() => { setSel(null); }, [activeShow]);

  // Default-select the first doc once the list loads.
  useEffect(() => {
    if (!sel && docs.length) setSel({ name: docs[0].name, scope: docs[0].scope });
  }, [docs, sel]);

  const docQ = useQuery({
    queryKey: ["doc", activeShow, sel?.scope, sel?.name],
    queryFn: () => docsApi.get(sel!.name, activeShow, sel!.scope),
    enabled: !!sel,
  });

  useEffect(() => {
    if (docQ.data && sel && docQ.data.name === sel.name) {
      setText(docQ.data.text);
      setSaved(true);
    }
  }, [docQ.data, sel]);

  const saveMut = useMutation({
    mutationFn: () => docsApi.put(sel!.name, text, activeShow, sel!.scope),
    onSuccess: () => {
      setSaved(true);
      push(`${sel!.name} saved`, "ok");
      qc.invalidateQueries({ queryKey: ["docs", activeShow] });
      qc.invalidateQueries({ queryKey: ["doc", activeShow, sel!.scope, sel!.name] });
    },
    onError: (e: Error) => push("save failed: " + e.message, "err"),
  });

  // Ctrl/Cmd+S
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (!saved && sel) saveMut.mutate();
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [saved, sel, saveMut]);

  const selectDoc = (d: DocSummary) => {
    if (!saved && !confirm("Discard unsaved changes?")) return;
    setSel({ name: d.name, scope: d.scope });
  };

  const isCommon = sel?.scope === "common";

  return (
    <div className="grid grid-cols-[280px_1fr] gap-3 h-full min-h-0">
      {/* LEFT — docs list */}
      <section className="panel flex flex-col min-h-0">
        <header className="px-3 py-2 border-b hairline">
          <div className="panel-title">CANON DOCS <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ {activeShow}</span></div>
        </header>
        <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1">
          {listQ.isLoading && <div className="text-txt-faint p-2">Loading…</div>}
          {docs.map((d: DocSummary) => {
            const active = sel?.name === d.name && sel?.scope === d.scope;
            return (
              <button
                key={`${d.scope}/${d.name}`}
                onClick={() => selectDoc(d)}
                className={"hairline-soft text-left px-2 py-1.5 rounded transition-colors " + (active ? "border-amber" : "")}
                style={active ? { borderColor: "var(--amber)", boxShadow: "var(--glow-amber)", background: "var(--bg-2)" } : {}}
              >
                <div className="flex items-center gap-1.5">
                  <div className="font-mono text-[12px] truncate flex-1">{d.name}</div>
                  {d.scope === "common" && (
                    <span className="label-tiny px-1 rounded bg-[var(--bg-2)] text-txt-faint shrink-0" title="Shared across all shows">SHARED</span>
                  )}
                </div>
                <div className="label-tiny text-txt-faint">{fmtBytes(d.bytes)}</div>
              </button>
            );
          })}
          {!listQ.isLoading && docs.length === 0 && (
            <div className="text-txt-faint p-2">No docs for {activeShow}.</div>
          )}
        </div>
      </section>

      {/* CENTER — editor */}
      <section className="panel flex flex-col min-h-0">
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title flex items-center gap-2">
            {sel?.name || "—"}
            {isCommon && (
              <span className="label-tiny px-1 rounded normal-case tracking-normal" style={{ color: "var(--amber)", border: "1px solid var(--amber)" }} title="Editing this changes it for every show">SHARED · all shows</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className={"text-[11px] " + (saved ? "text-green" : "text-amber")}>
              {saved ? "● SAVED" : "○ UNSAVED"}
            </span>
            <button className={"btn " + (!preview ? "btn-amber" : "")} onClick={() => setPreview(false)}>Edit</button>
            <button className={"btn " + (preview ? "btn-amber" : "")} onClick={() => setPreview(true)}>Preview</button>
            <button
              className="btn"
              disabled={saved || !sel || saveMut.isPending}
              onClick={() => saveMut.mutate()}
            >
              {saveMut.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </header>
        <div className="flex-1 min-h-0">
          {!sel ? (
            <div className="h-full grid place-items-center text-txt-faint">Select a doc.</div>
          ) : docQ.isLoading ? (
            <div className="h-full grid place-items-center text-txt-faint">Loading…</div>
          ) : preview ? (
            <div className="h-full overflow-y-auto p-4 text-[13px] leading-relaxed">
              <Markdown text={text} />
            </div>
          ) : (
            <textarea
              className="w-full h-full p-3 font-mono text-[13px] bg-[#0b0b0a] text-txt resize-none outline-none border-0"
              spellCheck={false}
              value={text}
              onChange={(e) => { setText(e.target.value); setSaved(false); }}
              onBlur={() => { if (!saved && sel) saveMut.mutate(); }}
            />
          )}
        </div>
        <footer className="flex items-center gap-3 px-3 py-1.5 border-t hairline">
          <span className="label-tiny">{text.length} chars</span>
          <span className="label-tiny ml-auto">UTF-8 · markdown · LF · Ctrl/Cmd+S to save</span>
        </footer>
      </section>
    </div>
  );
}

function fmtBytes(n: number): string {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
  return n + " B";
}
