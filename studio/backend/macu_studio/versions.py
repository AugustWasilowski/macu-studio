"""Asset versioning — archive + promote.

Model: the **active** version always keeps the canonical filename the pipeline
reads (`vo/<cue>.wav`, `clips/<key>_master.zs.webp`, `final/<slug>_thumb.png`),
so the render path (lib.staged_master_webp / stage 4) is UNCHANGED. Previous
generations are archived under `<dir>/.versions/<key>/<name>.vN.<ext>` and recorded
in a per-episode sidecar `.versions.json`. The UI browses [current + history] and
"promote" copies an archived version back over the canonical name (archiving the
current first, so nothing is lost).

There is no post-render hook (regen is fire-and-forget to :8773), so "current" is
defined simply as *whatever bytes are in the canonical file right now*. `archive_current`
is called BEFORE a regen/overwrite to push the outgoing file into history.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from .episodes import episode_dir
from . import manifest as manifest_mod
from . import shows as shows_mod

KINDS = ("cue", "shot", "ythumb")


def _sidecar_path(slug: str) -> Path:
    return episode_dir(slug) / ".versions.json"


def _atomic_write(path: Path, blob: str, mode: int = 0o664) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".v.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(blob)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load(slug: str) -> dict[str, Any]:
    p = _sidecar_path(slug)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save(slug: str, data: dict[str, Any]) -> None:
    _atomic_write(_sidecar_path(slug), json.dumps(data, indent=2))


def _ek(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def canonical_for(slug: str, kind: str, key: str) -> str:
    """Canonical path RELATIVE to the episode dir. Mirrors lib.staged_master_webp
    and regen.py exactly (single source of truth for these conventions)."""
    # key is interpolated into clips/vo paths — must stay a single in-tree segment.
    shows_mod.safe_segment(key, "key")
    if kind == "cue":
        return f"vo/{key}.wav"
    if kind == "ythumb":
        return f"final/{slug}_thumb.png"
    if kind == "shot":
        m = manifest_mod.load(slug)
        chars = m.get("characters") or {}
        broll = m.get("broll") or {}
        if key in chars:
            return f"clips/{key}_master.zs.webp"  # key=='safe' → 'safe_master.zs.webp'
        if key in broll:
            return "clips/c09_s1.zs.webp" if key == "empty_room" else f"clips/broll_{key}.zs.webp"
        # Unknown key — prefer whichever file exists on disk.
        ep = episode_dir(slug)
        for rel in (f"clips/{key}_master.zs.webp", f"clips/broll_{key}.zs.webp"):
            if (ep / rel).exists():
                return rel
        return f"clips/{key}_master.zs.webp"
    raise ValueError(f"unknown version kind: {kind}")


def _archive_dir_rel(kind: str, key: str, canonical_rel: str) -> str:
    return str(Path(canonical_rel).parent / ".versions" / key)


def _split_name(canonical_rel: str) -> tuple[str, str]:
    """('c01', '.wav') or ('ron_master', '.zs.webp')."""
    name = Path(canonical_rel).name
    suffix = "".join(Path(canonical_rel).suffixes)
    stem = name[: -len(suffix)] if suffix else name
    return stem, suffix


def history(slug: str, kind: str, key: str) -> list[dict]:
    rec = _load(slug).get(_ek(kind, key)) or {}
    return sorted(rec.get("history") or [], key=lambda e: int(e["v"]), reverse=True)


def version_file(slug: str, kind: str, key: str, v: int) -> Optional[Path]:
    ep = episode_dir(slug)
    for e in history(slug, kind, key):
        if int(e["v"]) == int(v):
            return ep / e["file"]
    return None


def version_meta(slug: str, kind: str, key: str, v: int) -> dict:
    """The per-version metadata stamped at archive time (e.g. {"seed": N})."""
    for e in history(slug, kind, key):
        if int(e["v"]) == int(v):
            return dict(e.get("meta") or {})
    return {}


def _capture_meta(slug: str, kind: str, key: str) -> dict:
    """Auto-stamp metadata for the canonical asset being archived. For shot/
    character we record the seed it was rendered with (lives in the manifest) so
    the UI can show the right seed when browsing back, and promote can restore it."""
    if kind == "shot":
        m = manifest_mod.load(slug)
        cdef = (m.get("characters") or {}).get(key)
        if isinstance(cdef, dict) and cdef.get("seed") is not None:
            return {"seed": cdef["seed"]}
        bdef = (m.get("broll") or {}).get(key)
        if isinstance(bdef, dict) and bdef.get("seed") is not None:
            return {"seed": bdef["seed"]}
    return {}


def archive_current(slug: str, kind: str, key: str, meta: Optional[dict] = None) -> Optional[int]:
    """Copy the current canonical file into history. Returns the new version
    number, or None if there is no canonical file yet (first generation). `meta`
    is stamped onto the history entry (defaults to auto-captured seed for shots)."""
    ep = episode_dir(slug)
    canonical_rel = canonical_for(slug, kind, key)
    canonical = ep / canonical_rel
    if not canonical.exists():
        return None
    if meta is None:
        meta = _capture_meta(slug, kind, key)
    data = _load(slug)
    ek = _ek(kind, key)
    rec = data.get(ek) or {}
    rec["canonical"] = canonical_rel
    rec.setdefault("archive_dir", _archive_dir_rel(kind, key, canonical_rel))
    hist = rec.setdefault("history", [])
    nextv = max((int(e["v"]) for e in hist), default=0) + 1
    stem, suffix = _split_name(canonical_rel)
    vfile_rel = f"{rec['archive_dir']}/{stem}.v{nextv}{suffix}"
    (ep / rec["archive_dir"]).mkdir(parents=True, exist_ok=True)
    shutil.copy2(canonical, ep / vfile_rel)
    entry = {"v": nextv, "file": vfile_rel, "ts": int(canonical.stat().st_mtime)}
    if meta:
        entry["meta"] = meta
    hist.append(entry)
    data[ek] = rec
    _save(slug, data)
    return nextv


def promote(slug: str, kind: str, key: str, v: int) -> dict:
    """Restore archived version v as the canonical (active) file. The current
    canonical is archived first so it isn't lost."""
    ep = episode_dir(slug)
    src = version_file(slug, kind, key, v)
    if not src or not src.exists():
        raise FileNotFoundError(f"version {v} not found for {kind}:{key}")
    canonical = ep / canonical_for(slug, kind, key)
    if canonical.exists():
        archive_current(slug, kind, key)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".promote.", dir=canonical.parent)
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, canonical)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return summary(slug, kind, key)


def summary(slug: str, kind: str, key: str) -> dict:
    """What the UI needs to render the ← → arrows: the live 'current' plus the
    archived history (newest first). count <= 1 → arrows greyed out."""
    ep = episode_dir(slug)
    rec = _load(slug).get(_ek(kind, key)) or {}
    canonical_rel = rec.get("canonical") or canonical_for(slug, kind, key)
    canonical = ep / canonical_rel
    hist = history(slug, kind, key)
    return {
        "kind": kind,
        "key": key,
        "canonical": canonical_rel,
        "current": {
            "exists": canonical.exists(),
            "mtime": canonical.stat().st_mtime if canonical.exists() else None,
        },
        "history": hist,
        "count": (1 if canonical.exists() else 0) + len(hist),
    }
