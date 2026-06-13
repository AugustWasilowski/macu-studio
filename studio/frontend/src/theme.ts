// Theme presets. Two kinds:
//  - "accent": recolors the amber family by setting --amber-rgb/--amber-dim
//    inline on :root; every tint/glow/hairline derives from the channel var
//    in CSS. tokens.css holds the defaults; "default" clears the overrides.
//  - "full": a complete skin (surfaces, fonts, shapes, effects) selected by
//    putting data-theme on <html>; the var blocks live in themes.css. Full
//    themes can carry color VARIANTS: clicking a swatch dot makes that color
//    the theme's primary (inline --amber overrides beat the data-theme block)
//    and, where it makes sense, the displaced native primary rotates into the
//    clicked color's own slot — so Pretty Princess clicked-blue becomes "blue
//    with pink accents" instead of losing the pink entirely.
export interface ThemeVariant {
  hex: string;                                   // becomes the theme's primary (--amber family)
  // Where the DISPLACED native primary gets re-injected. Omit for neutral /
  // surface-toned dots — the primary just changes, secondaries stay native.
  swap?: "--cyan-rgb" | "--green-rgb" | "--violet";
}

export interface Theme {
  id: string;
  label: string;
  kind: "accent" | "full";
  accent: string;     // swatch dot; for accent kind, the --amber override
  accentDim?: string; // accent kind only
  swatch?: string[];  // display-only preview dots (themes without variants)
  // Clickable color rotations; dot 0 is always the native accent. A stored
  // theme id "princess@2" = princess with variants[1] applied.
  variants?: ThemeVariant[];
}

export const THEMES: Theme[] = [
  { id: "default", label: "Amber (default)", kind: "accent", accent: "#f5a623", accentDim: "#b87811" },
  { id: "green", label: "Terminal Green", kind: "accent", accent: "#33ff66", accentDim: "#1e9e3d" },
  { id: "cyan", label: "Cyan", kind: "accent", accent: "#00e5ff", accentDim: "#0a93a3" },
  { id: "magenta", label: "Magenta", kind: "accent", accent: "#ff5cc8", accentDim: "#b03088" },
  { id: "mono", label: "Mono Grey", kind: "accent", accent: "#c9c9c9", accentDim: "#7d7d7d" },
  { id: "starship", label: "Starship", kind: "full", accent: "#ff9c00",
    variants: [{ hex: "#cc99cc", swap: "--violet" }, { hex: "#9999ff", swap: "--cyan-rgb" }] },
  { id: "wasteland", label: "Wasteland", kind: "full", accent: "#c1440e",
    variants: [{ hex: "#9aa85b", swap: "--green-rgb" }, { hex: "#d9cfb8" }] },
  { id: "pro", label: "Slate Pro", kind: "full", accent: "#4d90ff",
    variants: [{ hex: "#9aa3b2" }, { hex: "#d7dbe2" }] },
  { id: "marquee", label: "Movie Palace", kind: "full", accent: "#d4af37",
    variants: [{ hex: "#e8b4b8", swap: "--cyan-rgb" }, { hex: "#e53935" }] },
  { id: "dracula", label: "Dracula", kind: "full", accent: "#c41e3a",
    variants: [{ hex: "#b288ff", swap: "--cyan-rgb" }, { hex: "#86de62", swap: "--green-rgb" }] },
  { id: "princess", label: "Pretty Princess", kind: "full", accent: "#ec4899",
    variants: [{ hex: "#38b6ff", swap: "--cyan-rgb" }, { hex: "#ffd166", swap: "--cyan-rgb" }] },
];

// Every var a theme application may set inline (cleared on each apply).
const VARS = ["--amber-rgb", "--amber-dim", "--cyan-rgb", "--green-rgb", "--violet"] as const;

// "#33ff66" -> "51 255 102" (the space-separated channel form the CSS expects)
function channels(hex: string): string {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

// Darken a hex ~45% for the --amber-dim companion (hover/pressed states).
function dim(hex: string): string {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  const scale = (v: number) => Math.round(v * 0.55).toString(16).padStart(2, "0");
  return `#${scale((n >> 16) & 255)}${scale((n >> 8) & 255)}${scale(n & 255)}`;
}

/** "princess@2" -> { base: "princess", variant: 2 }; plain ids -> variant 0. */
export function parseThemeId(id: string): { base: string; variant: number } {
  const [base, v] = id.split("@");
  const variant = parseInt(v || "0", 10);
  return { base, variant: Number.isFinite(variant) && variant > 0 ? variant : 0 };
}

export function applyTheme(id: string): void {
  const root = document.documentElement;
  VARS.forEach((v) => root.style.removeProperty(v));
  const { base, variant } = parseThemeId(id);
  const t = THEMES.find((x) => x.id === base);
  if (t?.kind === "full") {
    root.setAttribute("data-theme", t.id);
    const vdef = variant > 0 ? t.variants?.[variant - 1] : undefined;
    if (vdef) {
      root.style.setProperty("--amber-rgb", channels(vdef.hex));
      root.style.setProperty("--amber-dim", dim(vdef.hex));
      if (vdef.swap) {
        // Rotate the displaced native primary into the clicked color's slot.
        root.style.setProperty(
          vdef.swap,
          vdef.swap.endsWith("-rgb") ? channels(t.accent) : t.accent,
        );
      }
    }
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
