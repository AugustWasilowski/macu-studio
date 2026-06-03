import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useStore } from "../store";

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
  const [split, setSplit] = useState(58);
  const dragRef = useRef(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scriptQ.data) {
      setText(scriptQ.data.text);
      setSaved(true);
    }
  }, [scriptQ.data]);

  // mouse-driven splitter
  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!dragRef.current || !wrapRef.current) return;
      const r = wrapRef.current.getBoundingClientRect();
      setSplit(Math.min(75, Math.max(35, ((e.clientX - r.left) / r.width) * 100)));
    };
    const up = () => (dragRef.current = false);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, []);

  const saveMut = useMutation({
    mutationFn: () => api.putScript(slug, text),
    onSuccess: () => {
      setSaved(true);
      push("script.md saved", "ok");
      qc.invalidateQueries({ queryKey: ["script", slug] });
    },
    onError: (e: Error) => push("save failed: " + e.message, "err"),
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
    <div ref={wrapRef} className="flex h-full gap-0">
      <section className="panel flex flex-col" style={{ width: `${split}%` }}>
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

      <div
        className="w-1.5 cursor-col-resize bg-bg hover:bg-amber-dim"
        onMouseDown={() => (dragRef.current = true)}
        style={{ background: "var(--bg)" }}
      />

      <ChatMax slug={slug} split={100 - split} />
    </div>
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

function ChatMax({ slug, split }: { slug: string; split: number }) {
  interface Msg { role: "user" | "max" | "system"; text: string }
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "system", text: `Session seeded · episode ${slug} · ss-chat-channel proxy stubbed in v0.4 — ships in v0.7.` },
    { role: "max", text: "Max online. Talk to me about cuts, lines, beats. (Real reply path is a stub for now — your messages reach the backend but get a canned response.)" },
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [msgs, typing]);

  const send = async () => {
    const t = input.trim();
    if (!t) return;
    setMsgs((m) => [...m, { role: "user", text: t }]);
    setInput("");
    setTyping(true);
    try {
      const r = await fetch(`/api/episodes/${slug}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: t }),
      });
      if (r.ok) {
        const data = await r.json();
        setMsgs((m) => [...m, { role: "max", text: data.reply ?? "(empty reply)" }]);
      } else {
        setMsgs((m) => [...m, { role: "max", text: `(chat error: HTTP ${r.status})` }]);
      }
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "max", text: `(network error: ${e.message})` }]);
    }
    setTyping(false);
  };

  const reset = () => setMsgs(msgs.slice(0, 2));

  return (
    <section className="panel flex flex-col" style={{ width: `${split}%` }}>
      <header className="flex items-center justify-between px-3 py-2 border-b hairline">
        <div className="panel-title">CHAT — MAX <span className="text-cyan ml-2 text-[10px]">● ss-chat-channel (stub)</span></div>
        <button className="btn" onClick={reset}>New conversation</button>
      </header>
      <div ref={bodyRef} className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {msgs.map((m, i) => (
          <div
            key={i}
            className={"flex flex-col gap-1 " + (m.role === "user" ? "items-end" : m.role === "system" ? "items-center" : "items-start")}
          >
            {m.role !== "system" && (
              <span className="label-tiny">{m.role === "max" ? "MAX" : "YOU"}</span>
            )}
            <div
              className="px-3 py-1.5 rounded-[3px] max-w-[80%] whitespace-pre-wrap"
              style={
                m.role === "max" ? { background: "var(--bg-2)", borderLeft: "2px solid var(--amber)" } :
                m.role === "user" ? { background: "rgba(0,229,255,0.06)", border: "1px solid rgba(0,229,255,0.3)" } :
                { borderTop: "1px dashed var(--line-soft)", borderBottom: "1px dashed var(--line-soft)", color: "var(--txt-faint)", fontSize: 11 }
              }
            >
              {m.text}
            </div>
          </div>
        ))}
        {typing && (
          <div className="flex items-center gap-1.5">
            <span className="label-tiny">MAX</span>
            <span className="flex gap-1">
              <span className="led-dot pulse" style={{ "--led-c": "var(--amber)" } as React.CSSProperties} />
              <span className="led-dot pulse" style={{ "--led-c": "var(--amber)", animationDelay: ".3s" } as React.CSSProperties} />
              <span className="led-dot pulse" style={{ "--led-c": "var(--amber)", animationDelay: ".6s" } as React.CSSProperties} />
            </span>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 px-3 py-2 border-t hairline">
        <textarea
          rows={1}
          value={input}
          placeholder="message Max…  (Shift+Enter = newline)"
          className="input flex-1 py-1.5"
          style={{ height: 32, resize: "none" }}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button className="btn btn-amber" onClick={send}>SEND</button>
      </div>
    </section>
  );
}
