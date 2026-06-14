async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export interface HfAuth {
  connected: boolean;
  plan: string | null;
  credits: number | null;
  balance_error?: string;
}
export interface HfAuthStart { handle: string; auth_url?: string; connected?: boolean; }
export interface HfPoll { status: "pending" | "connected" | "error"; error: string | null; auth_url: string | null; }
export interface HfBalance { credits: number; subscription_plan_type: string; }

export interface HfModelParam {
  name: string;
  required?: string;
  type?: string;
  description?: string;
  default?: unknown;
  options?: string[];
}
export interface HfModelMedia { name: string; type: string; roles?: string[]; required?: boolean; max?: number; }
export interface HfModel {
  id: string;
  name: string;
  provider_name: string;
  description: string;
  output_type: "video" | "image" | "audio" | "3d";
  parameters: HfModelParam[];
  medias: HfModelMedia[];
  aspect_ratios: string[];
  tags: string[];
  durations?: number[];
  duration_range?: { min: number; max: number };
}

const post = <T,>(url: string, body?: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined }).then((r) => J<T>(r));

export interface HfEstimateShot {
  id: string; cue: string; kind: string; cached: boolean;
  credits: number | null; segments: number; note: string | null;
}
export interface HfEstimate {
  shots: HfEstimateShot[];
  stills: { who: string; cached: boolean; has_prompt: boolean }[];
  total_credits: number;
  unknown_costs: number;
  balance: number | null;
  plan: string | null;
  sufficient: boolean | null;
}
export interface HfStillStatus {
  exists: boolean; fresh: boolean; mtime: number | null; has_prompt: boolean;
  job: { state: string | null; error: string | null } | null;
}

// ---- Soul characters / Elements / account (SSA-129) ----------------------------
export interface HfSoul { id: string; name?: string; status?: string; type?: string;
  preview_url?: string; thumb_url?: string; }
export interface HfElement { id: string; name?: string; category?: string;
  url?: string; thumb_url?: string; preview_url?: string; }
export interface HfUnlimited { plan?: string; period?: string; group?: string;
  model?: string; badges?: string[]; note?: string; }
export interface HfAccount {
  connected: boolean; credits: number | null; plan: string | null;
  unlimited: HfUnlimited[]; balance_error?: string; plans_error?: string;
}
export interface HfTxn { display_name?: string; credits?: number; action?: string; created_at?: string; }

// Generation provenance stamped on each HF take (backend gen_metadata()).
export interface HfGenMeta {
  provider: string; tool: string;
  model_requested: string; model_used: string;
  job_id: string | null; seed: number | null; prompt: string | null;
  aspect_ratio?: string | null; width?: number | null; height?: number | null;
  resolution?: string | null;
  raw_url: string | null; thumb_url: string | null; created_at?: string | null;
  credits_spent: number | null; unlimited: boolean;
  soul_id?: string; element_id?: string;
}

export const higgsfieldApi = {
  souls: (status?: string) =>
    fetch(`/api/higgsfield/souls${status ? `?status=${status}` : ""}`).then((r) => J<{ items: HfSoul[] }>(r)),
  soulTrain: (name: string, images: string[]) =>
    post<HfSoul>("/api/higgsfield/souls/train", { name, images }),
  soulStatus: (id: string) => fetch(`/api/higgsfield/souls/${id}`).then((r) => J<HfSoul>(r)),
  elements: () => fetch("/api/higgsfield/elements").then((r) => J<{ items: HfElement[] }>(r)),
  createElement: (body: { path?: string; medias?: unknown[]; name?: string; category?: string }) =>
    post<HfElement>("/api/higgsfield/elements", body),
  account: () => fetch("/api/higgsfield/account").then((r) => J<HfAccount>(r)),
  transactions: (size = 20) => fetch(`/api/higgsfield/transactions?size=${size}`).then((r) => J<{ items: HfTxn[] }>(r)),
  cost: (params: { model: string; duration?: number; resolution?: string; aspect_ratio?: string }) =>
    post<{ model: string; credits: number | null }>("/api/higgsfield/cost", params),
  estimate: (slug: string) =>
    fetch(`/api/episodes/${slug}/higgsfield/estimate`).then((r) => J<HfEstimate>(r)),
  regenShot: (slug: string, shotId: string) =>
    post<{ job_id: string }>(`/api/episodes/${slug}/shot/${shotId}/higgsfield/regen`),
  stillRegen: (slug: string, who: string) =>
    post<{ ok: boolean }>(`/api/episodes/${slug}/characters/${who}/still/regen`),
  stillStatus: (slug: string, who: string) =>
    fetch(`/api/episodes/${slug}/characters/${who}/still/status`).then((r) => J<HfStillStatus>(r)),
  stillUrl: (slug: string, who: string, v?: number | null) =>
    `/api/episodes/${slug}/still/${who}${v != null ? `?v=${Math.floor(v)}` : ""}`,
  auth: () => fetch("/api/higgsfield/auth").then((r) => J<HfAuth>(r)),
  authStart: () => post<HfAuthStart>("/api/higgsfield/auth/start"),
  authPoll: (handle: string) => post<HfPoll>("/api/higgsfield/auth/poll", { handle }),
  authManual: (redirect_url: string) => post<{ ok: boolean }>("/api/higgsfield/auth/manual", { redirect_url }),
  disconnect: () => post<{ connected: boolean }>("/api/higgsfield/auth/disconnect"),
  balance: (force = false) => fetch(`/api/higgsfield/balance?force=${force}`).then((r) => J<HfBalance>(r)),
  models: (refresh = false) => fetch(`/api/higgsfield/models?refresh=${refresh}`).then((r) => J<{ items: HfModel[] }>(r)),
};
