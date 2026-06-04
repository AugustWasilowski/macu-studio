export interface WritersNotes {
  text: string;
  mtime: number | null;
  exists: boolean;
}

async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text().catch(() => "")}`);
  return r.json() as Promise<T>;
}

export const writersApi = {
  kick: (slug: string) =>
    fetch(`/api/episodes/${slug}/writers-room`, { method: "POST" })
      .then((r) => J<{ ok: boolean; queued: boolean }>(r)),
  notes: (slug: string) =>
    fetch(`/api/episodes/${slug}/writers-room`).then((r) => J<WritersNotes>(r)),
};
