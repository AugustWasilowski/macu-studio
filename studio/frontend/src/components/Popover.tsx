import { useEffect } from "react";

export function Popover({
  open, onClose, title, children, width = 300, anchor,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  width?: number;
  anchor?: { top: number; left: number };
}) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="fixed inset-0 z-[1000]" onClick={onClose} />
      <div
        className="absolute z-[1001] panel p-3"
        style={{ width, top: anchor?.top, left: anchor?.left }}
        onClick={(e) => e.stopPropagation()}
      >
        {title && <div className="label-tiny mb-2">{title}</div>}
        {children}
      </div>
    </>
  );
}
