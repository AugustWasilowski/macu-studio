"""Cross-episode asset corpus.

By default the asset drawer shows only the current episode's manifest-derived assets
(shots, VO, graphics cards). With the "all episodes" toggle on, the drawer lists the
same asset kinds across EVERY episode so an operator can pull, say, a character shot
rendered in ep-07 into the episode they're editing.

Shots/titles are defined per-manifest and their masters render per-episode, so importing
one cross-episode means copying its DEFINITION (core + seed for a shot; the title_assets
entry for a card) into the target manifest — it then renders here deterministically from
the same seed. See import_shot / import_title.
"""
from __future__ import annotations

import shutil

from . import manifest as manifest_mod
from . import versions as versions_mod
from .config import EPISODES
from .episodes import episode_dir


def _slugs() -> list[str]:
    if not EPISODES.exists():
        return []
    return [e.name for e in sorted(EPISODES.iterdir())
            if e.is_dir() and (e / "manifest.json").exists()]


def _tag(rows: list[dict], slug: str) -> list[dict]:
    out = []
    for r in rows:
        r = dict(r)
        r["slug"] = slug
        out.append(r)
    return out


def shots() -> list[dict]:
    out: list[dict] = []
    for slug in _slugs():
        try:
            out.extend(_tag(manifest_mod.derive_shots(slug), slug))
        except Exception:
            continue
    return out


def titles() -> list[dict]:
    out: list[dict] = []
    for slug in _slugs():
        try:
            out.extend(_tag(manifest_mod.derive_titles(slug), slug))
        except Exception:
            continue
    return out


def cues() -> list[dict]:
    out: list[dict] = []
    for slug in _slugs():
        try:
            out.extend(_tag(manifest_mod.derive_cues(slug), slug))
        except Exception:
            continue
    return out


def _master_webp_rel(key: str, kind: str) -> str:
    """Master .zs.webp path relative to the episode dir (mirrors lib.staged_master_webp)."""
    if kind == "character":
        return f"clips/{'safe_master' if key == 'safe' else key + '_master'}.zs.webp"
    return f"clips/{'c09_s1' if key == 'empty_room' else 'broll_' + key}.zs.webp"


def _rife_dir_rel(key: str, kind: str) -> str:
    """RIFE output frames dir relative to the episode dir (mirrors lib.staged_master_dir)."""
    if kind == "character":
        return f".rife_frames/{'safe_master_out' if key == 'safe' else key + '_master_out'}"
    return f".rife_frames/{'c09_s1_out' if key == 'empty_room' else 'broll_' + key + '_out'}"


def _copy_master(from_slug: str, slug: str, key: str, kind: str) -> bool:
    """Copy a rendered shot's master (the .zs.webp + its RIFE frame dir) from another
    episode into this one, so the EXACT shot is reused with no re-render (stage 2 & 3 both
    skip; stage 4 assembles it). Won't clobber an existing local master, and returns False
    if the source hasn't rendered it yet (then the target re-renders from the copied def)."""
    src_ep, tgt_ep = episode_dir(from_slug), episode_dir(slug)
    src_webp, tgt_webp = src_ep / _master_webp_rel(key, kind), tgt_ep / _master_webp_rel(key, kind)
    if tgt_webp.exists() or not src_webp.exists():
        return False
    tgt_webp.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_webp, tgt_webp)
    src_rife, tgt_rife = src_ep / _rife_dir_rel(key, kind), tgt_ep / _rife_dir_rel(key, kind)
    if src_rife.is_dir() and not tgt_rife.exists():
        shutil.copytree(src_rife, tgt_rife)
    return True


def shot_alternates(slug: str | None = None) -> list[dict]:
    """Archived (non-live) shot generations. For each shot in scope (one episode if `slug`
    is given, else the whole corpus) emit one row per version in its history — the takes
    that weren't promoted to live. Each row carries enough to pull it in: source slug, key,
    kind, version number, and the seed it was rendered with."""
    out: list[dict] = []
    for s in ([slug] if slug else _slugs()):
        try:
            shots = manifest_mod.derive_shots(s)
        except Exception:
            continue
        for sh in shots:
            for v in versions_mod.history(s, "shot", sh["key"]):
                out.append({
                    "slug": s, "key": sh["key"], "kind": sh["kind"],
                    "v": int(v["v"]), "seed": (v.get("meta") or {}).get("seed"),
                })
    return out


def import_shot_version(slug: str, from_slug: str, key: str, kind: str, v: int) -> dict:
    """Pull a specific archived generation (non-live version `v`) of a shot into `slug`:
    copy that version's frame over as the master, set the def's seed to the version's seed,
    and clear the local RIFE frames so the next render re-interpolates this take. The
    current live master (if any) is archived first, so the swap is reversible."""
    bucket = "characters" if kind == "character" else "broll"
    vfile = versions_mod.version_file(from_slug, "shot", key, v)
    if vfile is None or not vfile.exists():
        raise FileNotFoundError(f"version {v} of {key!r} not found in {from_slug}")
    seed = (versions_mod.version_meta(from_slug, "shot", key, v) or {}).get("seed")

    tgt = manifest_mod.load(slug)
    if key not in (tgt.get(bucket) or {}):
        src = manifest_mod.load(from_slug)
        sdef = (src.get(bucket) or {}).get(key)
        if sdef is None:
            raise FileNotFoundError(f"{kind} {key!r} not found in {from_slug}")
        tgt.setdefault(bucket, {})[key] = sdef
    # Pin the version's seed so a later full re-render reproduces this exact take.
    if seed is not None:
        d = tgt[bucket].get(key)
        if isinstance(d, dict):
            d["seed"] = seed
        elif kind == "broll":
            tgt[bucket][key] = {"prompt": d, "seed": seed}
    manifest_mod.save(slug, tgt)

    tgt_webp = episode_dir(slug) / _master_webp_rel(key, kind)
    # Preserve the current live master as a version before overwriting (reversible swap).
    if tgt_webp.exists():
        try:
            versions_mod.archive_current(slug, "shot", key)
        except Exception:
            pass
    tgt_webp.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(vfile, tgt_webp)
    # Versions only store the master frame, not RIFE output — clear it so stage 3 re-RIFEs.
    tgt_rife = episode_dir(slug) / _rife_dir_rel(key, kind)
    if tgt_rife.exists():
        shutil.rmtree(tgt_rife)
    return {"ok": True, "key": key, "kind": kind, "v": v, "needs_rife": True}


def import_shot(slug: str, from_slug: str, key: str, kind: str) -> dict:
    """Copy a shot's definition (characters[key]/broll[key]) from `from_slug` into `slug`'s
    manifest AND, when the source has rendered it, copy its master frames over so the exact
    shot is reused with no re-render. The copied definition carries the seed, so a later
    re-render stays identical."""
    bucket = "characters" if kind == "character" else "broll"
    tgt = manifest_mod.load(slug)
    already = key in (tgt.get(bucket) or {})
    if not already:
        src = manifest_mod.load(from_slug)
        sdef = (src.get(bucket) or {}).get(key)
        if sdef is None:
            raise FileNotFoundError(f"{kind} {key!r} not found in {from_slug}")
        tgt.setdefault(bucket, {})[key] = sdef
        manifest_mod.save(slug, tgt)
    master_copied = _copy_master(from_slug, slug, key, kind)
    return {"ok": True, "key": key, "kind": kind, "already": already, "master_copied": master_copied}


def import_title(slug: str, from_slug: str, key: str) -> dict:
    """Copy a title-card definition (title_assets[key]) from `from_slug` into `slug`, and
    its rendered titles/<key>.mp4 if present (so it's usable without re-render)."""
    tgt = manifest_mod.load(slug)
    already = key in (tgt.get("title_assets") or {})
    if not already:
        src = manifest_mod.load(from_slug)
        sdef = (src.get("title_assets") or {}).get(key)
        if sdef is None:
            raise FileNotFoundError(f"title {key!r} not found in {from_slug}")
        tgt.setdefault("title_assets", {})[key] = sdef
        manifest_mod.save(slug, tgt)
    src_mp4 = episode_dir(from_slug) / "titles" / f"{key}.mp4"
    tgt_mp4 = episode_dir(slug) / "titles" / f"{key}.mp4"
    master_copied = False
    if src_mp4.exists() and not tgt_mp4.exists():
        tgt_mp4.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_mp4, tgt_mp4)
        master_copied = True
    return {"ok": True, "key": key, "already": already, "master_copied": master_copied}
