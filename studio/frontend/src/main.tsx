import React from "react";
import { createRoot } from "react-dom/client";
import "./tokens.css";
import { App } from "./app";
import { applyTheme, currentTheme } from "./theme";
import { applyLocale, currentLocale } from "./i18n";

applyTheme(currentTheme());

// Load the saved locale's catalog (and set <html lang/dir>) before the first render,
// so a non-English startup paints translated, not raw keys. En resolves instantly.
applyLocale(currentLocale()).finally(() => {
  createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
