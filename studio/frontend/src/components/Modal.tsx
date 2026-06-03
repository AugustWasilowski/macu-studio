import { useEffect } from "react";
import { IX } from "./Icons";

export function Modal({
  open, onClose, title, children, footer, width = 520,
}: {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[2000] grid place-items-center bg-black/60"
      onClick={onClose}
    >
      <div className="panel" style={{ width }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-3 py-2 border-b hairline">
          <div className="panel-title">{title}</div>
          <button className="btn p-1" onClick={onClose}><IX /></button>
        </div>
        <div className="p-3">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 px-3 py-2 border-t hairline-soft">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
