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

export const higgsfieldApi = {
  auth: () => fetch("/api/higgsfield/auth").then((r) => J<HfAuth>(r)),
  authStart: () => post<HfAuthStart>("/api/higgsfield/auth/start"),
  authPoll: (handle: string) => post<HfPoll>("/api/higgsfield/auth/poll", { handle }),
  authManual: (redirect_url: string) => post<{ ok: boolean }>("/api/higgsfield/auth/manual", { redirect_url }),
  disconnect: () => post<{ connected: boolean }>("/api/higgsfield/auth/disconnect"),
  balance: (force = false) => fetch(`/api/higgsfield/balance?force=${force}`).then((r) => J<HfBalance>(r)),
  models: (refresh = false) => fetch(`/api/higgsfield/models?refresh=${refresh}`).then((r) => J<{ items: HfModel[] }>(r)),
};
