import { useEffect, useState } from "react";
import { UI_STAGES, UIStage } from "./types";

export interface Route {
  slug: string;
  stage: UIStage;
}

const DEFAULT_STAGE: UIStage = "assembly";

const valid = (s: string): s is UIStage =>
  UI_STAGES.some((x) => x.key === s);

export function parseHash(): Route {
  const raw = window.location.hash.replace(/^#/, "");
  const [slug, stage] = raw.split("/");
  return {
    slug: slug || "",
    stage: stage && valid(stage) ? stage : DEFAULT_STAGE,
  };
}

export function setHash(r: Route) {
  window.location.hash = `${r.slug}/${r.stage}`;
}

export function useRoute(): [Route, (r: Partial<Route>) => void] {
  const [route, setRoute] = useState<Route>(() => parseHash());
  useEffect(() => {
    const on = () => setRoute(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (next: Partial<Route>) => {
    const r = { ...route, ...next };
    setHash(r);
  };
  return [route, go];
}
