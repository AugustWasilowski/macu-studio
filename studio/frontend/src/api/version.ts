// Self-update API — talks to the backend's routes_version.py. Operates on the CODE
// repo (macu-studio), distinct from the per-episode git-sync (content repo).

export interface VersionCurrent {
  commit: string;
  short: string;
  release: string | null; // nearest release tag, e.g. "v0.2.2"
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
  // Set when the pending update touches files the in-app updater can't apply (no sudo:
  // systemd re-template, new prereqs/models). When non-empty the one-click update is
  // blocked and these manual steps are shown instead.
  requires_setup: boolean;
  setup: SetupReason[];
}

export interface SetupReason {
  area: string;
  reason: string;
  command: string | null;
  // false = advisory notice (e.g. new .env option) that does NOT block the one-click update.
  blocking: boolean;
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

export type UpdateStart = { ok: true } | { ok: false; gpuBusy: true; freeMib: number | null };

export const versionApi = {
  get: () => fetch("/api/version").then((r) => J<VersionInfo>(r)),
  check: () => fetch("/api/version/check", { method: "POST" }).then((r) => J<VersionCheck>(r)),
  // A GPU-busy 409 is an expected outcome (the UI asks "update anyway?"), so it's
  // returned as a value rather than thrown; force=true retries past that guard.
  update: async (force = false): Promise<UpdateStart> => {
    const r = await fetch(`/api/version/update${force ? "?force=true" : ""}`, { method: "POST" });
    if (r.status === 409) {
      const detail = (await r.json().catch(() => null))?.detail;
      if (detail && typeof detail === "object" && detail.code === "gpu_busy")
        return { ok: false, gpuBusy: true, freeMib: detail.free_mib ?? null };
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail ?? "409 Conflict"));
    }
    return J<{ ok: true }>(r);
  },
  status: () => fetch("/api/version/update/status").then((r) => J<UpdateState>(r)),
};
