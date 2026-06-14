import type { HfGenMeta } from "./higgsfield";

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}
const post = <T,>(url: string, body?: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined }).then((r) => J<T>(r));
const put = <T,>(url: string, body: unknown) =>
  fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => J<T>(r));

export interface CharSummary {
  key: string; name: string; tags: string[];
  take_count: number; default_take: string | null; updated_at: string;
}
export interface Take {
  id: string; file: string; engine: string; model: string | null;
  prompt: string; seed: number | null; params: Record<string, unknown>;
  sha16: string; created_at: string;
  hf?: HfGenMeta;   // Higgsfield generation provenance (HF takes only)
}
export interface CharJob {
  state: string; error: string | null;
  progress: { done: number; total: number };
}
export interface Character {
  version: number; key: string; name: string; core: string; still_prompt: string;
  voice_hint: string; tags: string[]; seed: number | null;
  default_take: string | null; takes: Take[];
  created_at: string; updated_at: string;
  job: CharJob | null;
}
export interface UseResult {
  ok?: boolean; needs_confirm?: boolean;
  current_sha?: string; take_sha?: string;
  take?: string; invalidates: string[];
}
export interface UsageRow { slug: string; state: "in_sync" | "stale" | "diverged" | "no_still"; }

const base = (show: string) => `/api/shows/${show}/characters`;

export const charactersApi = {
  roster: (show: string) => fetch(base(show)).then((r) => J<{ characters: CharSummary[] }>(r)),
  create: (show: string, body: { key: string; name?: string; core?: string; still_prompt?: string }) =>
    post<Character>(base(show), body),
  get: (show: string, key: string) => fetch(`${base(show)}/${key}`).then((r) => J<Character>(r)),
  update: (show: string, key: string, fields: Partial<Character>) =>
    put<Character>(`${base(show)}/${key}`, fields),
  remove: (show: string, key: string) =>
    fetch(`${base(show)}/${key}`, { method: "DELETE" }).then((r) => J<{ ok: boolean }>(r)),

  takeUrl: (show: string, key: string, take: string, thumb = false) =>
    `${base(show)}/${key}/takes/${take}${thumb ? "?thumb=1" : ""}`,
  deleteTake: (show: string, key: string, take: string) =>
    fetch(`${base(show)}/${key}/takes/${take}`, { method: "DELETE" }).then((r) => J<Character>(r)),
  setDefault: (show: string, key: string, take: string) =>
    post<Character>(`${base(show)}/${key}/takes/${take}/default`),
  takeToElement: (show: string, key: string, take: string, name?: string) =>
    post<{ id: string; name?: string }>(`${base(show)}/${key}/takes/${take}/element`, name ? { name } : {}),

  generate: (show: string, key: string, body: { engine?: string; prompt?: string; seed?: number; count?: number; params?: Record<string, unknown>; soul_id?: string; element_id?: string }) =>
    post<{ ok: boolean; key: string; engine: string; count: number }>(`${base(show)}/${key}/generate`, body),
  generateStatus: (show: string, key: string) =>
    fetch(`${base(show)}/${key}/generate/status`).then((r) =>
      J<{ job: CharJob | null; take_count: number; takes: Take[]; default_take: string | null }>(r)),

  use: (show: string, key: string, body: { slug: string; take?: string; overwrite_still?: boolean }) =>
    post<UseResult>(`${base(show)}/${key}/use`, body),
  usage: (show: string, key: string) =>
    fetch(`${base(show)}/${key}/usage`).then((r) => J<{ usage: UsageRow[] }>(r)),
  importEpisode: (show: string, slug: string) =>
    post<{ created: string[]; skipped: string[] }>(`${base(show)}/import-episode`, { slug }),
};
