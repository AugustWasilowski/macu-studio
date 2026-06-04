async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export interface DocSummary {
  name: string;
  mtime: number;
  bytes: number;
}

export const docsApi = {
  list: () => fetch("/api/docs").then((r) => J<{ docs: DocSummary[] }>(r)),
  get: (name: string) =>
    fetch(`/api/docs/${encodeURIComponent(name)}`).then((r) =>
      J<{ name: string; text: string }>(r)
    ),
  put: (name: string, text: string) =>
    fetch(`/api/docs/${encodeURIComponent(name)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((r) => J<{ ok: boolean }>(r)),
};
