import { useMemo } from "react";

// Shared markdown renderer, factored out of Script.tsx so the YouTube reader and
// the docs preview render scripts/canon docs identically. Handles MACU [CUE …]
// lines, headings, blockquotes, and plain paragraphs — the same lightweight
// subset Script.tsx has always rendered (no external markdown dependency).
export function Markdown({ text }: { text: string }) {
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
        if (line.startsWith("### ")) return <h3 key={i} className="text-amber font-semibold text-sm mt-2 mb-1">{line.slice(4)}</h3>;
        if (line.startsWith("> ")) return <blockquote key={i} className="border-l-2 border-[var(--line-soft)] pl-2 my-1 text-txt-dim italic">{line.slice(2)}</blockquote>;
        if (!line.trim()) return <div key={i} className="h-2" />;
        return <p key={i} className="my-1">{line}</p>;
      })}
    </>
  );
}

export function colorForSpeaker(name: string): string {
  if (!name) return "#938d82";
  const palette = ["#f5a623", "#00e5ff", "#33ff66", "#c08bff", "#ff7a59", "#9ad6ff", "#ffd166", "#7cc97a"];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return palette[Math.abs(h) % palette.length];
}
