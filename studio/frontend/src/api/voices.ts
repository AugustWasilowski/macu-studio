async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export interface VoiceProfile { id: string; name: string; }
export interface VoiceList { running: boolean; cached?: boolean; profiles: VoiceProfile[]; error?: string; }
export interface CreatedVoice { ok: boolean; id: string; name: string; ref: string; test_file?: string; }

export const voicesApi = {
  list: () => fetch("/api/voices").then((r) => J<VoiceList>(r)),
  // NOTE: do not set Content-Type — the browser sets the multipart boundary.
  create: (form: FormData) =>
    fetch("/api/voices", { method: "POST", body: form }).then((r) => J<CreatedVoice>(r)),
  remove: (id: string) =>
    fetch(`/api/voices/${encodeURIComponent(id)}`, { method: "DELETE" }).then((r) => J<{ ok: boolean }>(r)),
  sampleUrl: (testFile: string) => `/api/voices/sample/${encodeURIComponent(testFile)}`,
};
