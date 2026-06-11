import { gsap } from "gsap";

// Central motion vocabulary — every GSAP call in the app goes through these so
// timing/easing stay coherent and reduced-motion is honored in one place.
export const DUR = { fast: 0.18, base: 0.28, slow: 0.45 };
export const EASE = { out: "power3.out", in: "power2.in", inOut: "power2.inOut" };

export function reducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Stage-mount entrance: fade + rise the top-level panels with a short stagger.
    Falls back to animating the container itself when there's nothing to stagger. */
export function enterStage(el: HTMLElement): gsap.core.Tween | null {
  if (reducedMotion()) return null;
  const all = Array.from(el.querySelectorAll<HTMLElement>(".panel"));
  // Only top-level panels — staggering nested panels compounds transforms.
  const tops = all.filter((p) => !p.parentElement?.closest(".panel"));
  const targets = tops.length >= 2 && tops.length <= 14 ? tops : [el];
  return gsap.fromTo(
    targets,
    { opacity: 0, y: 10 },
    {
      opacity: 1,
      y: 0,
      duration: DUR.base,
      ease: EASE.out,
      stagger: 0.045,
      clearProps: "opacity,transform", // leave no inline residue (fixed children, drag math)
      overwrite: "auto",
    }
  );
}
