import { useState } from "react";
import { useStore } from "../store";
import { ITerminal, IX } from "./Icons";
import { useT } from "../i18n";
import { Trans } from "../i18n/Trans";

// Optional ttyd web terminal attached to a tmux session running Claude Code.
// Server-side setup lives in deploy/macu-ttyd/ and is stood up by the
// `setup-macu-channel` skill (alongside the chat bridge). Without it, Connect fails
// with "refuses to connect" — that's the missing ttyd service, not a frontend bug.
// Configurable at build time (Vite): VITE_TERMINAL_URL (full URL), or
// VITE_TERMINAL_PORT (default 7682) + VITE_TERMINAL_SESSION (the tmux session name,
// shown in the UI). The default targets the SAME host you loaded Studio from
// (window.location.hostname), so it adapts: localhost when local, the WSL host via
// localhost forwarding, or the LAN IP when you reach Studio over the network. For
// LAN-remote access ttyd must be reachable on that host — the shipped unit binds
// loopback by default (secure), so open it per deploy/macu-ttyd/README to use the
// drawer from another machine. http only (ttyd is http-only); never expose on WAN.
const _ENV = ((import.meta as any).env ?? {}) as Record<string, string | undefined>;
const TERMINAL_PORT = _ENV.VITE_TERMINAL_PORT || "7682";
const TERMINAL_SESSION = _ENV.VITE_TERMINAL_SESSION || "claude";
const TERMINAL_URL =
  _ENV.VITE_TERMINAL_URL ||
  `http://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:${TERMINAL_PORT}/`;

/* Right-hand slide-in panel (mirrors ManifestDrawer/LogDrawer) that embeds the
   ttyd web terminal. Connecting mounts the iframe → ttyd opens a WebSocket and
   tmux-attaches to the configured session (talking to Claude directly); disconnecting unmounts
   it → the WebSocket closes and the tmux client detaches. The drawer stays
   mounted while closed, so a connected session keeps running in the background. */
export function TerminalDrawer() {
  const t = useT();
  const open = useStore((s) => s.terminalOpen);
  const close = useStore((s) => s.closeTerminal);
  const [connected, setConnected] = useState(false);

  return (
    <>
      <div
        className={"fixed inset-0 z-[800] bg-black/40 transition-opacity duration-300 " + (open ? "opacity-100" : "opacity-0 pointer-events-none")}
        onClick={close}
      />
      <aside
        className={"fixed top-0 right-0 h-full z-[900] panel flex flex-col transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] " + (open ? "translate-x-0" : "translate-x-full")}
        style={{ width: 680 }}
      >
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title flex items-center gap-2">
            <ITerminal /> {t("terminal.title")}
            <span className="text-txt-faint normal-case tracking-normal text-[11px]">{t("terminal.sessionLabel", { session: TERMINAL_SESSION })}</span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="led-dot"
              style={{ "--led-c": connected ? "#33ff66" : "#5a5a5a" } as React.CSSProperties}
              title={connected ? t("terminal.attached") : t("terminal.detached")}
            />
            <button
              className={"btn " + (connected ? "btn-amber" : "btn-cyan")}
              onClick={() => setConnected((c) => !c)}
            >
              {connected ? t("terminal.disconnect") : t("terminal.connect")}
            </button>
            <button className="btn p-1" onClick={close}><IX /></button>
          </div>
        </header>
        <div className="flex-1 min-h-0 bg-black">
          {connected ? (
            <iframe
              src={TERMINAL_URL}
              title={t("terminal.iframeTitle", { session: TERMINAL_SESSION })}
              className="w-full h-full"
              style={{ border: 0, display: "block" }}
            />
          ) : (
            <div className="grid place-items-center h-full text-txt-faint text-[12px] p-6 text-center">
              <div>
                <Trans
                  k="terminal.helpMain"
                  vars={{ session: TERMINAL_SESSION }}
                  tags={[(c) => <span className="font-mono">{c}</span>]}
                />
                <div className="mt-2 text-[11px] text-txt-faint">
                  <Trans
                    k="terminal.helpDetail"
                    vars={{ url: TERMINAL_URL }}
                    tags={[(c) => <span className="font-mono">{c}</span>]}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
