import React from "react";
import { createRoot } from "react-dom/client";
import "./tokens.css";
import { App } from "./app";
import { applyTheme, currentTheme } from "./theme";

applyTheme(currentTheme());

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
