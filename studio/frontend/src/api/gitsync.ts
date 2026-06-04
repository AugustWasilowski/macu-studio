async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export interface GitSyncResp {
  ok: boolean;
  committed: boolean;
  commit: string | null;
  pushed: boolean;
  log: string;
}

export const gitsyncApi = {
  sync: (slug: string) =>
    fetch(`/api/episodes/${slug}/git-sync`, { method: "POST" }).then((r) => J<GitSyncResp>(r)),
};
