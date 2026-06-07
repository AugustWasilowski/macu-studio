// Self-update API — talks to the backend's routes_version.py. Operates on the CODE
// repo (macu-studio), distinct from the per-episode git-sync (content repo).

export interface VersionCurrent {
  commit: string;
  short: string;
  branch: string;
  subject: string;
  committed_iso: string | null;
  dirty: boolean;
  upstream: string | null;
  can_autorestart: boolean;
}

export interface IncomingCommit {
  short: string;
  subject: string;
  iso: string;
}

export interface VersionCheck {
  ts: number | null;
  behind: number;
  ahead: number;
  update_available: boolean;
  incoming: IncomingCommit[];
  remote_short: string | null;
  error: string | null;
  upstream: string | null;
}

export type UpdatePhase =
  | "idle"
  | "pulling"
  | "building"
  | "restarting"
  | "restart-needed"
  | "error";

export interface UpdateState {
  phase: UpdatePhase;
  log: string[];
  error: string | null;
  started: number | null;
}

export interface VersionInfo {
  current: VersionCurrent;
  check: VersionCheck;
  update: UpdateState;
}

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export const versionApi = {
  get: () => fetch("/api/version").then((r) => J<VersionInfo>(r)),
  check: () => fetch("/api/version/check", { method: "POST" }).then((r) => J<VersionCheck>(r)),
  update: () => fetch("/api/version/update", { method: "POST" }).then((r) => J<{ ok: boolean }>(r)),
  status: () => fetch("/api/version/update/status").then((r) => J<UpdateState>(r)),
};
