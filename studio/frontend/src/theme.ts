// Theme presets. Two kinds:
//  - "accent": recolors the amber family by setting --amber-rgb/--amber-dim
//    inline on :root; every tint/glow/hairline derives from the channel var
//    in CSS. tokens.css holds the defaults; "default" clears the overrides.
//  - "full": a complete skin (surfaces, fonts, shapes, effects) selected by
//    putting data-theme on <html>; the var blocks live in themes.css.
export interface Theme {
  id: string;
  label: string;
  kind: "accent" | "full";
  accent: string;     // swatch dot; for accent kind, the --amber override
  accentDim?: string; // accent kind only
  swatch?: string[];  // extra preview dots for full themes
}

export const THEMES: Theme[] = [
  { id: "default", label: "Amber (default)", kind: "accent", accent: "#f5a623", accentDim: "#b87811" },
  { id: "green", label: "Terminal Green", kind: "accent", accent: "#33ff66", accentDim: "#1e9e3d" },
  { id: "cyan", label: "Cyan", kind: "accent", accent: "#00e5ff", accentDim: "#0a93a3" },
  { id: "magenta", label: "Magenta", kind: "accent", accent: "#ff5cc8", accentDim: "#b03088" },
  { id: "mono", label: "Mono Grey", kind: "accent", accent: "#c9c9c9", accentDim: "#7d7d7d" },
  { id: "starship", label: "Starship", kind: "full", accent: "#ff9c00", swatch: ["#ff9c00", "#cc99cc", "#9999ff"] },
  { id: "wasteland", label: "Wasteland", kind: "full", accent: "#c1440e", swatch: ["#c1440e", "#9aa85b", "#d9cfb8"] },
  { id: "pro", label: "Slate Pro", kind: "full", accent: "#4d90ff", swatch: ["#4d90ff", "#14171d", "#d7dbe2"] },
];

const VARS = ["--amber-rgb", "--amber-dim"] as const;

// "#33ff66" -> "51 255 102" (the space-separated channel form the CSS expects)
function channels(hex: string): string {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

export function applyTheme(id: string): void {
  const root = document.documentElement;
  VARS.forEach((v) => root.style.removeProperty(v));
  const t = THEMES.find((x) => x.id === id);
  if (t?.kind === "full") {
    root.setAttribute("data-theme", t.id);
    return;
  }
  root.removeAttribute("data-theme");
  if (!t || t.id === "default") return; // tokens.css defaults (unknown ids fall through too)
  root.style.setProperty("--amber-rgb", channels(t.accent));
  root.style.setProperty("--amber-dim", t.accentDim!);
}

export function currentTheme(): string {
  return localStorage.getItem("macu.theme") || "default";
}

export function setTheme(id: string): void {
  localStorage.setItem("macu.theme", id);
  applyTheme(id);
}
