// Color-theme presets. Each preset recolors the primary accent (the amber
// family + its glow + the hairline tint) by overriding a handful of CSS vars on
// :root. tokens.css holds the default values; "default" clears the overrides.
export interface Theme {
  id: string;
  label: string;
  accent: string;     // --amber
  accentDim: string;  // --amber-dim
}

export const THEMES: Theme[] = [
  { id: "default", label: "Amber (default)", accent: "#f5a623", accentDim: "#b87811" },
  { id: "green", label: "Terminal Green", accent: "#33ff66", accentDim: "#1e9e3d" },
  { id: "cyan", label: "Cyan", accent: "#00e5ff", accentDim: "#0a93a3" },
  { id: "magenta", label: "Magenta", accent: "#ff5cc8", accentDim: "#b03088" },
  { id: "mono", label: "Mono Grey", accent: "#c9c9c9", accentDim: "#7d7d7d" },
];

const VARS = ["--amber", "--amber-dim", "--glow-amber", "--line"] as const;

function rgba(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

export function applyTheme(id: string): void {
  const root = document.documentElement;
  const t = THEMES.find((x) => x.id === id);
  if (!t || id === "default") {
    // Revert to tokens.css defaults by removing the inline overrides.
    VARS.forEach((v) => root.style.removeProperty(v));
    return;
  }
  root.style.setProperty("--amber", t.accent);
  root.style.setProperty("--amber-dim", t.accentDim);
  root.style.setProperty("--glow-amber", `0 0 6px ${rgba(t.accent, 0.55)}`);
  root.style.setProperty("--line", rgba(t.accent, 0.13));
}

export function currentTheme(): string {
  return localStorage.getItem("macu.theme") || "default";
}

export function setTheme(id: string): void {
  localStorage.setItem("macu.theme", id);
  applyTheme(id);
}
