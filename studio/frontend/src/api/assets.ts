import type { VersionSummary } from "../types";

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
};
