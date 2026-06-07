async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export type DocScope = "common" | "show";

export interface DocSummary {
  name: string;
  scope: DocScope;
  mtime: number;
  bytes: number;
}

const qs = (params: Record<string, string>) =>
  Object.entries(params)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join("&");

export const docsApi = {
  list: (show: string) =>
    fetch(`/api/docs?${qs({ show })}`).then((r) => J<{ docs: DocSummary[] }>(r)),
  get: (name: string, show: string, scope: DocScope) =>
    fetch(`/api/docs/${encodeURIComponent(name)}?${qs({ show, scope })}`).then((r) =>
      J<{ name: string; scope: DocScope; text: string }>(r)
    ),
  put: (name: string, text: string, show: string, scope: DocScope) =>
    fetch(`/api/docs/${encodeURIComponent(name)}?${qs({ show })}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, scope }),
    }).then((r) => J<{ ok: boolean; scope: DocScope }>(r)),
};
