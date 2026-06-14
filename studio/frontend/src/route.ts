import { useEffect, useState } from "react";
import { UI_STAGES, UIStage } from "./types";

// Top-level pages that aren't tied to a (slug, stage) pair. They use the
// global activeShow/activeSlug from the store for context. TOP_PAGES = valid
// hash targets; STRIP_PAGES = the subset shown as topbar tabs (docs moved into
// the file menu, but #docs deep links keep working).
export type TopPage = "docs" | "characters" | "cowork";
export const TOP_PAGES: TopPage[] = ["docs", "characters", "cowork"];
// Characters renders inline as numbered tab #2 (between Script and Audio); the
// strip after the separator holds the remaining non-numbered pages.
export const STRIP_PAGES: TopPage[] = ["cowork"];
export type Page = "stage" | TopPage;

export interface Route {
  page: Page;
  slug: string;
  stage: UIStage;
}

const DEFAULT_STAGE: UIStage = "assembly";

const validStage = (s: string): s is UIStage => UI_STAGES.some((x) => x.key === s);
const isTop = (s: string): s is TopPage => (TOP_PAGES as string[]).includes(s);

export function parseHash(): Route {
  const raw = window.location.hash.replace(/^#/, "");
  const parts = raw.split("/");
  if (isTop(parts[0])) {
    return { page: parts[0], slug: "", stage: DEFAULT_STAGE };
  }
  const [slug, stage] = parts;
  return {
    page: "stage",
    slug: slug || "",
    stage: stage && validStage(stage) ? stage : DEFAULT_STAGE,
  };
}

export function setHash(r: Route) {
  window.location.hash = r.page !== "stage" ? r.page : `${r.slug}/${r.stage}`;
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
    setRoute(r);
  };
  return [route, go];
}
