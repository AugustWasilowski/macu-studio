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

// Editable timeline tracks. "shots" is move/reorder-only (no resize); the VO track is
// read-only and never a TrackKind (it can't be edited/committed).
export type TrackKind = "graphics" | "music" | "sfx" | "shots";

// Module-level drag payload for drawer→track HTML5 drops. `kind` gates which track
// will accept it (mismatched track ignores the drop).
export type DrawerDrag =
  // `slug` (when set, and != the editing episode) marks a cross-episode asset whose
  // definition must be imported into the current manifest on drop.
  | { kind: "card"; asset: string; slug?: string }
  | { kind: "music"; file: string }
  | { kind: "sfx"; file: string }
  | { kind: "shot"; key: string; shotKind: "character" | "broll"; slug?: string; version?: number } // drawer → add to a cue (version set = a non-live take)
  | { kind: "shot-move"; cueId: string; shotId: string };                          // existing bar → move/reorder/remove

let _drawerDrag: DrawerDrag | null = null;
export const drawerDrag = {
  set: (d: DrawerDrag | null) => { _drawerDrag = d; },
  get: () => _drawerDrag,
  clear: () => { _drawerDrag = null; },
};
