import type { Cue, Overlay } from "../types";
import type { AssetItem, MusicBed, SfxEntry } from "../api/library";

// What the metadata panel (lower-right) is currently showing. Any timeline clip OR
// any asset-drawer row resolves to one of these. idx is the index into its manifest
// array so edits/deletes can target it.
export type Selection =
  | { t: "cue"; cue: Cue }
  | { t: "overlay"; idx: number; ov: Overlay }
  | { t: "sfx"; idx: number; e: SfxEntry }
  | { t: "bed"; idx: number; b: MusicBed }
  | { t: "lib"; item: AssetItem; kind: "music" | "sfx" | "card" };

export type TrackKind = "graphics" | "music" | "sfx";

// Module-level drag payload for drawer→track HTML5 drops. `kind` gates which track
// will accept it (mismatched track ignores the drop).
export type DrawerDrag =
  | { kind: "card"; asset: string }
  | { kind: "music"; file: string }
  | { kind: "sfx"; file: string };

let _drawerDrag: DrawerDrag | null = null;
export const drawerDrag = {
  set: (d: DrawerDrag | null) => { _drawerDrag = d; },
  get: () => _drawerDrag,
  clear: () => { _drawerDrag = null; },
};
