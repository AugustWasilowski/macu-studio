import { useStore, ToastKind } from "../store";
import { IList, IX } from "./Icons";

const KIND_COLOR: Record<ToastKind, string> = {
  info: "var(--txt-dim)",
  ok: "var(--cyan)",
  run: "var(--amber)",
  err: "var(--red, #ff5a5a)",
};
const KIND_LABEL: Record<ToastKind, string> = {
  info: "INFO",
  ok: "OK",
  run: "RUN",
  err: "ERR",
};

function fmtTime(ts: number) {
  return new Date(ts).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/* Right-hand slide-in panel mirroring ManifestDrawer. Records every toast /
   notification pushed via the store (newest first) so they aren't lost when the
   3.2s toast auto-dismisses. */
export function LogDrawer() {
  const open = useStore((s) => s.logOpen);
  const close = useStore((s) => s.closeLog);
  const clear = useStore((s) => s.clearLog);
  const log = useStore((s) => s.log);

  const entries = [...log].reverse(); // newest first

  return (
    <>
      <div
        className={"fixed inset-0 z-[800] bg-black/40 transition-opacity " + (open ? "opacity-100" : "opacity-0 pointer-events-none")}
        onClick={close}
      />
      <aside
        className={"fixed top-0 right-0 h-full z-[900] panel flex flex-col transition-transform " + (open ? "translate-x-0" : "translate-x-full")}
        style={{ width: 420 }}
      >
        <header className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title flex items-center gap-2">
            <IList /> ACTIVITY LOG
            <span className="text-txt-faint normal-case tracking-normal text-[11px]">/ {log.length} event{log.length === 1 ? "" : "s"}</span>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn" onClick={clear} disabled={log.length === 0}>Clear</button>
            <button className="btn p-1" onClick={close}><IX /></button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1">
          {entries.length === 0 && (
            <div className="text-txt-faint p-3">No activity yet. Toasts and notifications will collect here.</div>
          )}
          {entries.map((e) => (
            <div key={e.id} className="flex items-start gap-2 px-2 py-1.5 hairline-soft rounded text-[12px]">
              <span className="font-mono text-txt-faint tabular-nums shrink-0">{fmtTime(e.ts)}</span>
              <span
                className="font-mono text-[10px] shrink-0 w-[34px] text-center rounded px-1"
                style={{ color: KIND_COLOR[e.kind], border: `1px solid ${KIND_COLOR[e.kind]}` }}
              >
                {KIND_LABEL[e.kind]}
              </span>
              <span className="break-words" style={{ color: e.kind === "err" ? KIND_COLOR.err : undefined }}>{e.text}</span>
            </div>
          ))}
        </div>
      </aside>
    </>
  );
}
