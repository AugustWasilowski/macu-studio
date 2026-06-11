import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { IX } from "./Icons";
import { DUR, EASE, reducedMotion } from "../lib/motion";

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
  const backRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  // Pop-in on open (close stays instant — the unmount is the snappy path).
  useEffect(() => {
    if (!open || reducedMotion()) return;
    if (backRef.current) gsap.fromTo(backRef.current, { opacity: 0 }, { opacity: 1, duration: DUR.fast, ease: "none" });
    if (panelRef.current) {
      gsap.fromTo(
        panelRef.current,
        { opacity: 0, scale: 0.96, y: 10 },
        { opacity: 1, scale: 1, y: 0, duration: DUR.base, ease: EASE.out, clearProps: "transform" }
      );
    }
  }, [open]);
  if (!open) return null;
  return (
    <div
      ref={backRef}
      className="fixed inset-0 z-[2000] grid place-items-center bg-black/60"
      onClick={onClose}
    >
      <div ref={panelRef} className="panel" style={{ width }} onClick={(e) => e.stopPropagation()}>
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
