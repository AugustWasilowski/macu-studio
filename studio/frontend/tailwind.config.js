/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      // Colors resolve through the CSS vars in tokens.css so full themes
      // (themes.css data-theme blocks) recolor Tailwind utilities too. The
      // accent family uses channel vars so opacity modifiers (amber/40) work.
      colors: {
        bg: "var(--bg)",
        "bg-1": "var(--bg-1)",
        "bg-2": "var(--bg-2)",
        "bg-3": "var(--bg-3)",
        line: "var(--line)",
        "line-soft": "var(--line-soft)",
        amber: "rgb(var(--amber-rgb) / <alpha-value>)",
        cyan: "rgb(var(--cyan-rgb) / <alpha-value>)",
        green: "rgb(var(--green-rgb) / <alpha-value>)",
        red: "rgb(var(--red-rgb) / <alpha-value>)",
        violet: "var(--violet)",
        txt: "var(--txt)",
        "txt-dim": "var(--txt-dim)",
        "txt-faint": "var(--txt-faint)",
      },
      fontFamily: {
        // The "data" font — tables, timelines, editors keep mono in every theme.
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: { sm: "var(--radius)", DEFAULT: "var(--radius)" },
      boxShadow: {
        "glow-amber": "var(--glow-amber)",
        "glow-cyan": "var(--glow-cyan)",
        "glow-green": "var(--glow-green)",
        "glow-red": "0 0 6px rgb(var(--red-rgb) / 0.55)",
      },
    },
  },
  plugins: [],
};
