async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export type Capability = "masters" | "stills" | "cloud_video" | "lipsync";
export type EngineId = "comfy_local" | "comfy_zimage" | "higgsfield" | "remote_render" | "local_wan";

export interface EnginesConfig {
  version: number;
  endpoints: {
    comfy_local: { url: string; zimage_unet: string };
    remote_render: { url: string; enabled: boolean };
  };
  routing: Record<Capability, EngineId>;
  overridden: string[];
  capabilities: { id: Capability; engines: { id: EngineId; available: boolean; reason?: string | null }[] }[];
}

export interface EngineProbe {
  comfy_local: { ok: boolean; latency_ms?: number; error?: string };
  remote_render: { ok: boolean; latency_ms?: number; error?: string; disabled?: boolean };
  higgsfield: { ok: boolean; connected?: boolean; credits?: number | null; plan?: string | null; error?: string };
}

export const enginesApi = {
  get: () => fetch("/api/engines").then((r) => J<EnginesConfig>(r)),
  put: (body: { endpoints?: Partial<EnginesConfig["endpoints"]>; routing?: Partial<EnginesConfig["routing"]> }) =>
    fetch("/api/engines", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => J<EnginesConfig>(r)),
  probe: () => fetch("/api/engines/probe").then((r) => J<EngineProbe>(r)),
};
