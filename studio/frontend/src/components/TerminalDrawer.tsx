import { useState } from "react";
import { useStore } from "../store";
import { ITerminal, IX } from "./Icons";

// ttyd is LAN-only on :7682, attached to the `ss-channels` tmux session. Use the
// same host the Studio page was loaded from, forced to http (ttyd is http-only).
// Off-LAN/https loads won't reach it — terminal access is intentionally LAN-only.
const TERMINAL_URL = `http://${typeof window !== "undefined" ? window.location.hostname : "10.0.0.245"}:7682/`;

/* Right-hand slide-in panel (mirrors ManifestDrawer/LogDrawer) that embeds the
   ttyd web terminal. Connecting mounts the iframe → ttyd opens a WebSocket and
   tmux-attaches to ss-channels (talking to Max directly); disconnecting unmounts
   it → the WebSocket closes and the tmux client detaches. The drawer stays
   mounted while closed, so a connected session keeps running in the background. */
export function TerminalDrawer() {
  const open = useStore((s) => s.terminalOpen);
  const close = useStore((s) => s.closeTerminal);
  const [connected, setConnected] = useState(false);

  return (
    <>
      <div
        className={"fixed inset-0 z-[800] bg-black/40 transition-opacity " + (open ? "opacity-100" : "opacity-0 pointer-events-none")}
        onClick={close}
      />
      <aside
        className={"fixed top-0 right-0 h-full z-[900] panel flex flex-col transition-transform " + (open ? "translate-x-0" : "translate-x-full")}
        style={{ width: 680 }}
      >
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title flex items-center gap-2">
            <ITerminal /> TERMINAL
            <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ tmux: ss-channels — talks to Max</span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="led-dot"
              style={{ "--led-c": connected ? "#33ff66" : "#5a5a5a" } as React.CSSProperties}
              title={connected ? "attached" : "detached"}
            />
            <button
              className={"btn " + (connected ? "btn-amber" : "btn-cyan")}
              onClick={() => setConnected((c) => !c)}
            >
              {connected ? "Disconnect" : "Connect"}
            </button>
            <button className="btn p-1" onClick={close}><IX /></button>
          </div>
        </header>
        <div className="flex-1 min-h-0 bg-black">
          {connected ? (
            <iframe
              src={TERMINAL_URL}
              title="ss-channels terminal"
              className="w-full h-full"
              style={{ border: 0, display: "block" }}
            />
          ) : (
            <div className="grid place-items-center h-full text-txt-faint text-[12px] p-6 text-center">
              <div>
                Detached. Click <span className="text-cyan">Connect</span> to attach to the
                {" "}<span className="font-mono">ss-channels</span> tmux session and talk to Max directly.
                <div className="mt-2 text-[11px] text-txt-faint">
                  Detach without closing: <span className="font-mono">Ctrl-b d</span> · LAN-only ({TERMINAL_URL})
                </div>
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
