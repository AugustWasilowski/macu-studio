import type { JobSubmitResp, Overlay } from "../types";

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export interface NewTitleArgs {
  key: string;
  composition: string;
  fields: Record<string, unknown>;
}
export interface RegenYThumbArgs {
  fields: Record<string, unknown>;
  composition?: string;
}

export const graphicsApi = {
  templates: () =>
    fetch("/api/hf/templates").then((r) => J<{ templates: string[] }>(r)),
  newTitle: (slug: string, body: NewTitleArgs) =>
    fetch(`/api/episodes/${slug}/title/new`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<JobSubmitResp>(r)),
  regenYThumb: (slug: string, body: RegenYThumbArgs) =>
    fetch(`/api/episodes/${slug}/ythumb/regen`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<JobSubmitResp>(r)),
  ythumbPreviewUrl: (slug: string) =>
    `/api/episodes/${slug}/ythumb/preview`,
  // Replace manifest.overlays[] wholesale (drag-to-place + timeline drag/resize/edit).
  putOverlays: (slug: string, overlays: Overlay[]) =>
    fetch(`/api/episodes/${slug}/overlays`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overlays }),
    }).then((r) => J<{ ok: boolean; count: number }>(r)),
};
