/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#0d0d0d",
        "bg-1": "#121212",
        "bg-2": "#181715",
        "bg-3": "#201e1a",
        line: "rgba(245,166,35,0.13)",
        "line-soft": "rgba(255,255,255,0.07)",
        amber: "#f5a623",
        cyan: "#00e5ff",
        green: "#33ff66",
        red: "#ff4d4d",
        violet: "#c08bff",
        txt: "#ded9cf",
        "txt-dim": "#938d82",
        "txt-faint": "#5f5a51",
      },
      fontFamily: {
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: { sm: "3px", DEFAULT: "3px" },
      boxShadow: {
        "glow-amber": "0 0 6px rgba(245,166,35,.55)",
        "glow-cyan": "0 0 6px rgba(0,229,255,.5)",
        "glow-green": "0 0 6px rgba(51,255,102,.55)",
        "glow-red": "0 0 6px rgba(255,77,77,.55)",
      },
    },
  },
  plugins: [],
};
