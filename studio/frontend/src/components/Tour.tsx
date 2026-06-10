import { useEffect, useLayoutEffect, useState } from "react";
import { TOUR_STEPS } from "../tour";
import type { Route } from "../route";
import { useT } from "../i18n";

export const TOUR_DONE_KEY = "macu.tour.done";

interface Props {
  slug: string;
  go: (r: Partial<Route>) => void;
  onClose: () => void;
  onStartWizard: () => void;
}

const PAD = 6;

export function Tour({ slug, go, onClose, onStartWizard }: Props) {
  const t = useT();
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const step = TOUR_STEPS[i];

  function finish() {
    localStorage.setItem(TOUR_DONE_KEY, "1");
    onClose();
  }

  // Navigate the screen behind the spotlight for context.
  useEffect(() => {
    if (step.stage) go({ page: "stage", slug, stage: step.stage });
    else if (step.topPage) go({ page: step.topPage });
  }, [i]); // eslint-disable-line react-hooks/exhaustive-deps

  // Measure the spotlight target (re-measure on step change + resize).
  useLayoutEffect(() => {
    const measure = () => {
      if (!step.target) { setRect(null); return; }
      const el = document.querySelector(step.target);
      setRect(el ? el.getBoundingClientRect() : null);
    };
    const t = setTimeout(measure, 30); // let any nav-driven re-render settle
    window.addEventListener("resize", measure);
    return () => { clearTimeout(t); window.removeEventListener("resize", measure); };
  }, [i]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard: → / Enter advance, ← back, Esc skip.
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
      else if (e.key === "ArrowRight" || e.key === "Enter") next();
      else if (e.key === "ArrowLeft") setI((n) => Math.max(0, n - 1));
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }); // re-bind each render so next()/finish() close over current i

  function next() {
    if (i >= TOUR_STEPS.length - 1) finish();
    else setI(i + 1);
  }

  const last = i === TOUR_STEPS.length - 1;

  // Tooltip placement: below the target if there's room, else above; centered
  // when there's no target.
  const cardW = 320;
  let cardStyle: React.CSSProperties;
  if (rect) {
    const below = rect.bottom + 12;
    const left = Math.min(Math.max(8, rect.left), window.innerWidth - cardW - 8);
    cardStyle = { position: "fixed", top: below, left, width: cardW };
  } else {
    cardStyle = { position: "fixed", top: "50%", left: "50%", width: cardW, transform: "translate(-50%,-50%)" };
  }

  return (
    <div className="fixed inset-0 z-[3000]" style={{ pointerEvents: "auto" }} onClick={(e) => e.stopPropagation()}>
      {/* Spotlight hole (transparent box + huge shadow darkens everything else) */}
      {rect ? (
        <div
          style={{
            position: "fixed",
            top: rect.top - PAD, left: rect.left - PAD,
            width: rect.width + PAD * 2, height: rect.height + PAD * 2,
            borderRadius: 5,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.72)",
            border: "1px solid var(--amber)",
            pointerEvents: "none",
            transition: "all 0.15s ease",
          }}
        />
      ) : (
        <div className="fixed inset-0" style={{ background: "rgba(0,0,0,0.72)" }} />
      )}

      {/* Coachmark card */}
      <div className="panel p-3 flex flex-col gap-2" style={cardStyle}>
        <div className="flex items-center justify-between">
          <div className="panel-title">{t(step.titleKey)}</div>
          <span className="label-tiny">{i + 1}/{TOUR_STEPS.length}</span>
        </div>
        <p className="text-[12px] leading-relaxed text-txt">{t(step.bodyKey)}</p>
        {last && (
          <button
            className="btn btn-cyan justify-center"
            onClick={() => { finish(); onStartWizard(); }}
          >
            {t("tour.startWalkthrough")}
          </button>
        )}
        <div className="flex items-center justify-between pt-1">
          <button className="btn" onClick={finish}>{last ? t("common.close") : t("tour.skip")}</button>
          <div className="flex gap-2">
            {i > 0 && <button className="btn" onClick={() => setI(i - 1)}>{t("common.back")}</button>}
            <button className="btn btn-amber" onClick={next}>{last ? t("tour.done") : t("tour.next")}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
