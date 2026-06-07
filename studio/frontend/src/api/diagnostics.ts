// Diagnostics API — runs the installer preflight (deploy/doctor.sh) on the host and
// returns its report. See the backend's routes_diag.py.

export interface DiagnosticsResult {
  ok: boolean;              // true when all REQUIRED checks pass (doctor exit 0)
  exit_code: number | null;
  output: string;           // the ANSI-stripped report (✓ / ✗ / ! lines)
}

export const diagnosticsApi = {
  run: () =>
    fetch("/api/diagnostics", { method: "POST" }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
      return r.json() as Promise<DiagnosticsResult>;
    }),
};
