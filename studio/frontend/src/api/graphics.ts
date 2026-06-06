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
export interface GenCardTextResp {
  card_type: string;
  composition: string;
  fields: Record<string, string>;
  idtag_default: string;
  warnings: string[];
}

export const graphicsApi = {
  templates: () =>
    fetch("/api/hf/templates").then((r) => J<{ templates: string[] }>(r)),
  // The editable ‹PLACEHOLDER› field set for a composition (scaffolds the JSON when the
  // layout dropdown changes — no LLM needed).
  templateFields: (composition: string) =>
    fetch(`/api/hf/templates/${encodeURIComponent(composition)}/fields`)
      .then((r) => J<{ composition: string; placeholders: string[]; fields: Record<string, string> }>(r)),
  cardTypes: () =>
    fetch("/api/card-types").then((r) => J<{ card_types: string[] }>(r)),
  // On-demand Ollama: write deadpan card text (the five HF fields) for a card type.
  genCardText: (slug: string, body: { card_type: string; composition?: string }) =>
    fetch(`/api/episodes/${slug}/card-text/generate`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<GenCardTextResp>(r)),
  newTitle: (slug: string, body: NewTitleArgs) =>
    fetch(`/api/episodes/${slug}/title/new`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<JobSubmitResp>(r)),
  // On-demand Ollama: write a NEW HyperFrames composition (animated card HTML) from a brief,
  // saved as the template named `key`. Returns the composition name + its placeholder fields.
  genComposition: (slug: string, body: { key: string; brief: string }) =>
    fetch(`/api/episodes/${slug}/composition/generate`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<{ ok: boolean; key: string; composition: string; fields: Record<string, string>; placeholders: string[]; bytes: number }>(r)),
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
