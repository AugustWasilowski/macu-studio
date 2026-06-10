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

// Liveness of the optional GPU/render services, used by the guided walkthrough to mark
// GPU-dependent steps (video shots, full render) as skippable when a service is down.
export interface ServicesStatus {
  comfyui: boolean; // ComfyUI reachable (t2v shot render)
  voice: boolean;   // TTS endpoint reachable (Piper/OmniVoice)
  gpu: boolean;     // nvidia-smi present → a GPU is visible
}

export const servicesApi = {
  get: (show: string) =>
    fetch(`/api/services?show=${encodeURIComponent(show)}`).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json() as Promise<ServicesStatus>;
    }),
};
