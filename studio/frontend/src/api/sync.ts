async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export interface SyncItem { path: string; reason: string; }
export interface SyncConflict { path: string; winner: "local" | "remote"; local_ts: number; remote_ts: number; }
export interface SyncPlan {
  show: string;
  push: SyncItem[];
  pull: SyncItem[];
  conflicts: SyncConflict[];
  in_sync: number;
  remote_empty: boolean;
  clean: boolean;
  log: string;
}
export interface SyncReport {
  ok: boolean;
  pulled: string[];
  pushed: string[];
  conflicts_resolved: string[];
  backed_up: string[];
  errors: string[];
  touched_episodes: string[];
  log: string;
}

export const syncApi = {
  status: (show: string) =>
    fetch(`/api/shows/${show}/sync/status`).then((r) => J<{ connected: boolean; base: string | null; host: string }>(r)),
  plan: (show: string) =>
    fetch(`/api/shows/${show}/sync/plan`).then((r) => J<SyncPlan>(r)),
  apply: (show: string, message?: string) =>
    fetch(`/api/shows/${show}/sync/apply`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message ? { message } : {}),
    }).then((r) => J<SyncReport>(r)),
};
