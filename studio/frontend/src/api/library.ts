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

// One manifest.music.beds[] entry — a music clip spanning a cue range (stage_5_music).
export interface MusicBed {
  name?: string;
  file?: string;            // which clip plays (basename); falls back to the theme bed
  cues: string[];           // the cue ids the bed spans
  anchor?: "start" | "end"; // where the bed is pinned in its span
  max_seconds?: number;     // duration cap
  gain?: number;
  fade_in?: number;
  fade_out?: number;
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
  // Replace manifest.music.beds[] wholesale (timeline MUSIC track placements).
  putBeds: (slug: string, beds: MusicBed[]) =>
    fetch(`/api/episodes/${slug}/music/beds`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ beds }),
    }).then(J<{ ok: boolean; count: number }>),
};
