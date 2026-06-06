import type { Cue, VersionSummary } from "../types";

export type CueShot = Cue["shots"][number];

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

type Kind = "cue" | "shot" | "ythumb";

export interface AddShotBody {
  key: string;
  kind: "character" | "broll";
  prompt: string;
  seed?: number | null;
  attach_to_cue?: string | null;
}

export const versionsApi = {
  summary: (slug: string, kind: Kind, key: string) =>
    fetch(`/api/episodes/${slug}/versions/${kind}/${encodeURIComponent(key)}`)
      .then((r) => J<VersionSummary>(r)),
  promote: (slug: string, kind: Kind, key: string, v: number) =>
    fetch(`/api/episodes/${slug}/versions/${kind}/${encodeURIComponent(key)}/promote`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ v }),
    }).then((r) => J<VersionSummary>(r)),
  mediaUrl: (slug: string, kind: Kind, key: string, v: number) =>
    `/api/episodes/${slug}/versions/${kind}/${encodeURIComponent(key)}/${v}/media`,
  addShot: (slug: string, body: AddShotBody) =>
    fetch(`/api/episodes/${slug}/shots/add`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<{ ok: boolean; key: string }>(r)),
  // Set cue.shots[] for the named cues only (timeline SHOTS track: move/reorder/add/remove).
  putCueShots: (slug: string, cues: Record<string, CueShot[]>) =>
    fetch(`/api/episodes/${slug}/cue-shots`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cues }),
    }).then((r) => J<{ ok: boolean; count: number }>(r)),
  // Cross-episode corpus listings (drawer "all episodes" toggle); each row carries `slug`.
  corpus: (kind: "shots" | "titles" | "cues") =>
    fetch(`/api/corpus/${kind}`).then((r) => J<any>(r)),
  // Archived (non-live) shot generations. Omit slug for the whole corpus.
  corpusAlternates: (slug?: string) =>
    fetch(`/api/corpus/shot-alternates${slug ? `?slug=${encodeURIComponent(slug)}` : ""}`).then((r) => J<any>(r)),
  // Pull a specific archived take of a shot in (copies that frame + pins its seed).
  importShotVersion: (slug: string, from_slug: string, key: string, kind: "character" | "broll", v: number) =>
    fetch(`/api/episodes/${slug}/import-shot-version`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_slug, key, kind, v }),
    }).then((r) => J<{ ok: boolean; key: string; kind: string; v: number; needs_rife: boolean }>(r)),
  // Copy a shot/title definition from another episode's manifest into this one.
  importShot: (slug: string, from_slug: string, key: string, kind: "character" | "broll") =>
    fetch(`/api/episodes/${slug}/import-shot`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_slug, key, kind }),
    }).then((r) => J<{ ok: boolean; key: string; kind: string; already: boolean; master_copied: boolean }>(r)),
  importTitle: (slug: string, from_slug: string, key: string) =>
    fetch(`/api/episodes/${slug}/import-title`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_slug, key }),
    }).then((r) => J<{ ok: boolean; key: string; already: boolean; master_copied: boolean }>(r)),
};
