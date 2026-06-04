async function J<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export type AssetKind = "sfx" | "music";

export interface AssetItem {
  file: string;
  duration_s: number | null;
  source?: string | null;
  license?: string | null;
  notes?: string | null;
}

// One manifest.sfx[] entry. file is a bare basename (resolved as assets/sfx/<file>).
export interface SfxEntry {
  file: string;
  cue: string | null;
  at: "start" | "end";
  gain?: number;
  fade?: number;
  delay?: number;
  prompt?: string;
  query?: string;
  seed?: number | null;
  source?: string;
  [k: string]: unknown;
}

export const libraryApi = {
  list: (kind: AssetKind): Promise<AssetItem[]> =>
    fetch(`/api/assets/${kind}`).then(J<{ assets: AssetItem[] }>).then((r) => r.assets),
  audioUrl: (kind: AssetKind, file: string) =>
    `/api/assets/${kind}/${encodeURIComponent(file)}/audio`,
  putSfx: (slug: string, sfx: SfxEntry[]) =>
    fetch(`/api/episodes/${slug}/sfx`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sfx }),
    }).then(J<{ ok: boolean; count: number }>),
  addBed: (slug: string, file: string) =>
    fetch(`/api/episodes/${slug}/music/add-bed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file }),
    }).then(J<{ ok: boolean; added: boolean }>),
};
