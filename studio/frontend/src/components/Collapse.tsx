import { useEffect, useRef, type ReactNode } from "react";
import { gsap } from "gsap";
import { DUR, EASE, reducedMotion } from "../lib/motion";

/** Height-animated collapse that keeps its children MOUNTED — drawer state,
    queries, and refs survive a collapse instead of being torn down. */
export function Collapse({ open, children, className = "" }: { open: boolean; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const first = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const target = { height: open ? "auto" : 0, opacity: open ? 1 : 0, pointerEvents: open ? "auto" : "none" } as const;
    if (first.current || reducedMotion()) {
      first.current = false;
      gsap.set(el, target);
      return;
    }
    gsap.to(el, { ...target, duration: DUR.base, ease: EASE.inOut, overwrite: "auto" });
  }, [open]);
  return (
    <div ref={ref} className={"overflow-hidden " + className} aria-hidden={!open}>
      {children}
    </div>
  );
}
