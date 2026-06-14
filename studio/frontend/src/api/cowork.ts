// CoWork job-board (SSA-133): the free-web → local-harvest queue. Read + light
// management for the Studio queue panel; CoWork itself drives the board via the
// cowork_* MCP tools, Leo/August queue via these REST routes.
async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}
const post = <T,>(url: string, body?: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined }).then((r) => J<T>(r));

export type CoworkStatus = "pending" | "claimed" | "in_progress" | "done" | "failed" | "skipped";
export type CoworkKind = "still" | "video" | "soul";

export interface CoworkJob {
  id: string; episode: string; kind: CoworkKind; target: string;
  prompt: string; model: string; params: Record<string, unknown>;
  status: CoworkStatus; claimed_by: string | null;
  result_gen_ids: string[]; result: Record<string, unknown>;
  note: string; error: string | null;
  created_at: string; updated_at: string;
}
export interface CoworkStats {
  pending: number; claimed: number; in_progress: number;
  done: number; failed: number; skipped: number; total: number;
}

const base = "/api/cowork/jobs";

export const coworkApi = {
  list: (opts: { episode?: string; status?: string; kind?: string } = {}) => {
    const q = new URLSearchParams();
    if (opts.episode) q.set("episode", opts.episode);
    if (opts.status) q.set("status", opts.status);
    if (opts.kind) q.set("kind", opts.kind);
    const qs = q.toString();
    return fetch(`${base}${qs ? `?${qs}` : ""}`).then((r) => J<{ jobs: CoworkJob[] }>(r));
  },
  stats: (episode?: string) =>
    fetch(`${base}/stats${episode ? `?episode=${encodeURIComponent(episode)}` : ""}`).then((r) => J<CoworkStats>(r)),
  patch: (id: string, body: Partial<Pick<CoworkJob, "status" | "note">> & { result_gen_ids?: string[] }) =>
    fetch(`${base}/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => J<CoworkJob>(r)),
  remove: (id: string) =>
    fetch(`${base}/${id}`, { method: "DELETE" }).then((r) => J<{ deleted: string }>(r)),
  clear: (episode?: string) =>
    post<{ removed: number }>(`${base}/clear`, episode ? { episode } : {}),
};
