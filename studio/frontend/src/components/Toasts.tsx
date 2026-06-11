import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { useStore, Toast } from "../store";
import { DUR, EASE, reducedMotion } from "../lib/motion";

// Per-kind auto-dismiss; errors linger longer. A toast with an action gets the
// err duration so the button is actually reachable. Hovering pauses the clock.
const KIND_MS: Record<string, number> = { ok: 3200, info: 3500, run: 3500, err: 6500 };

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dropToast = useStore((s) => s.dropToast);
  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <ToastItem key={t.id} t={t} onDone={() => dropToast(t.id)} />
      ))}
    </div>
  );
}

function ToastItem({ t, onDone }: { t: Toast; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const leaving = useRef(false);
  const [paused, setPaused] = useState(false);

  function leave() {
    if (leaving.current) return;
    leaving.current = true;
    const el = ref.current;
    if (!el || reducedMotion()) { onDone(); return; }
    // Collapse height + margin too so the stack slides up instead of snapping.
    gsap.to(el, {
      opacity: 0, x: 32, height: 0, marginTop: 0, paddingTop: 0, paddingBottom: 0,
      duration: DUR.fast, ease: EASE.in, onComplete: onDone,
    });
  }

  // Entrance: slide in from the right.
  useEffect(() => {
    if (!ref.current || reducedMotion()) return;
    gsap.fromTo(ref.current, { x: 48, opacity: 0 }, { x: 0, opacity: 1, duration: DUR.base, ease: EASE.out });
  }, []);

  // Dedupe bump: pulse instead of re-entering, and the timer below restarts.
  useEffect(() => {
    if (t.count > 1 && ref.current && !reducedMotion()) {
      gsap.fromTo(ref.current, { scale: 1.04 }, { scale: 1, duration: DUR.fast, ease: EASE.out });
    }
  }, [t.count]);

  // Auto-dismiss clock + progress bar. Hover pauses; leaving hover restarts full.
  useEffect(() => {
    if (paused || leaving.current) return;
    const ms = t.duration ?? (t.action ? KIND_MS.err : KIND_MS[t.kind] ?? 3500);
    const timer = setTimeout(leave, ms);
    let bar: gsap.core.Tween | undefined;
    if (barRef.current && !reducedMotion()) {
      bar = gsap.fromTo(barRef.current, { scaleX: 1 }, { scaleX: 0, duration: ms / 1000, ease: "none" });
    }
    return () => { clearTimeout(timer); bar?.kill(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused, t.count]);

  return (
    <div
      ref={ref}
      className={`toast ${t.kind}`}
      role="status"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="flex items-center gap-3">
        <span className="flex-1 min-w-0">
          {t.text}
          {t.count > 1 && <span className="toast-count">×{t.count}</span>}
        </span>
        {t.action && (
          <button
            className="toast-action"
            onClick={() => { t.action!.fn(); leave(); }}
          >
            {t.action.label}
          </button>
        )}
        <button className="toast-close" aria-label="dismiss" onClick={leave}>✕</button>
      </div>
      <div className="toast-progress" aria-hidden="true">
        <div ref={barRef} className="toast-progress-bar" />
      </div>
    </div>
  );
}
