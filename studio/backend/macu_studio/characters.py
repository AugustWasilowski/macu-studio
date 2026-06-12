"""Show-level character library — the roster behind the Characters page.

Layout (mirrors show_archive_dir's convention: show-scoped data lives under
SHARES/shows/<id>/ even for the legacy flat default show):

  SHARES/shows/<show_id>/characters/<key>/
    character.json          # the record: prompts + takes metadata
    takes/take-NNN.png      # immutable generations; numbering never reused
    takes/.thumbs/          # lazy 256px jpeg thumbs

Takes are immutable artifacts — provenance (engine/model/prompt/seed/sha16)
lives in character.json; there is nothing to cache-invalidate at the library
level. Billing protection stays episode-local: use_in_episode() copies a take
into episodes/<slug>/stills/<key>.png and stamps the episode's stills sidecar
exactly the way the Higgsfield still generator does, so estimates/cloud-shot
hashes behave identically. pipeline/hf_cache.py is untouched.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from . import config
from . import episodes as ep_mod
from . import hfcache as hfc
from . import manifest as manifest_mod
from . import shows as shows_mod

VERSION = 1


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def chars_root(show_id: str) -> Path:
    show_id = shows_mod.safe_segment(show_id, "show id")
    return config.SHARES / "shows" / show_id / "characters"


def char_dir(show_id: str, key: str) -> Path:
    return chars_root(show_id) / shows_mod.safe_segment(key, "character key")


def _json_path(show_id: str, key: str) -> Path:
    return char_dir(show_id, key) / "character.json"


def _write(show_id: str, key: str, data: dict) -> None:
    p = _json_path(show_id, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".character.", suffix=".json.tmp", dir=p.parent)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def load(show_id: str, key: str) -> dict:
    p = _json_path(show_id, key)
    if not p.exists():
        raise FileNotFoundError(f"no character '{key}' in show '{show_id}'")
    return json.loads(p.read_text())


def list_chars(show_id: str) -> list[dict]:
    root = chars_root(show_id)
    out: list[dict] = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        try:
            c = json.loads((d / "character.json").read_text())
        except Exception:
            continue
        out.append({"key": c.get("key") or d.name, "name": c.get("name"),
                    "tags": c.get("tags") or [],
                    "take_count": len(c.get("takes") or []),
                    "default_take": c.get("default_take"),
                    "updated_at": c.get("updated_at")})
    return out


EDITABLE = ("name", "core", "still_prompt", "voice_hint", "tags", "seed")


def create(show_id: str, key: str, fields: dict) -> dict:
    key = shows_mod.safe_segment(key, "character key")
    if _json_path(show_id, key).exists():
        raise FileExistsError(f"character '{key}' already exists in show '{show_id}'")
    c: dict = {"version": VERSION, "key": key, "name": fields.get("name") or key,
               "core": "", "still_prompt": "", "voice_hint": "", "tags": [],
               "seed": None, "default_take": None, "takes": [],
               "created_at": _now(), "updated_at": _now()}
    for f in EDITABLE:
        if fields.get(f) is not None:
            c[f] = fields[f]
    _write(show_id, key, c)
    return c


def update(show_id: str, key: str, fields: dict) -> dict:
    c = load(show_id, key)
    for f in EDITABLE:
        if f in fields:
            c[f] = fields[f]
    c["updated_at"] = _now()
    _write(show_id, key, c)
    return c


def delete(show_id: str, key: str) -> None:
    """Recoverable delete: move the char dir to characters/.trash-<ts>-<key>/."""
    d = char_dir(show_id, key)
    if not d.exists():
        raise FileNotFoundError(f"no character '{key}'")
    shutil.move(str(d), str(chars_root(show_id) / f".trash-{int(time.time())}-{key}"))


# ---- takes -----------------------------------------------------------------------

def take_path(show_id: str, key: str, take_id: str) -> Path:
    take_id = shows_mod.safe_segment(take_id, "take id")
    return char_dir(show_id, key) / "takes" / f"{take_id}.png"


def next_take_id(c: dict) -> str:
    nums = [int(t["id"].split("-")[1]) for t in c.get("takes") or []
            if isinstance(t.get("id"), str) and t["id"].startswith("take-")
            and t["id"].split("-")[1].isdigit()]
    return f"take-{(max(nums) + 1 if nums else 1):03d}"


def add_take(show_id: str, key: str, png: Path, *, engine: str, model: str | None,
             prompt: str, seed: int | None, params: dict | None) -> dict:
    """Record an already-written take PNG into character.json (re-reads the file
    so concurrent appends within one process don't clobber each other)."""
    c = load(show_id, key)
    tid = next_take_id(c)
    dest = take_path(show_id, key, tid)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if png.resolve() != dest.resolve():
        shutil.move(str(png), str(dest))
    rec = {"id": tid, "file": f"takes/{tid}.png", "engine": engine, "model": model,
           "prompt": prompt, "seed": seed, "params": params or {},
           "sha16": hfc.file_sha(dest), "created_at": _now()}
    c.setdefault("takes", []).append(rec)
    if not c.get("default_take"):
        c["default_take"] = tid
    c["updated_at"] = _now()
    _write(show_id, key, c)
    return rec


def delete_take(show_id: str, key: str, take_id: str) -> dict:
    c = load(show_id, key)
    takes = [t for t in c.get("takes") or [] if t.get("id") != take_id]
    if len(takes) == len(c.get("takes") or []):
        raise FileNotFoundError(f"no take '{take_id}'")
    c["takes"] = takes
    if c.get("default_take") == take_id:
        c["default_take"] = takes[-1]["id"] if takes else None
    c["updated_at"] = _now()
    take_path(show_id, key, take_id).unlink(missing_ok=True)
    thumb = char_dir(show_id, key) / "takes" / ".thumbs" / f"{take_id}.jpg"
    thumb.unlink(missing_ok=True)
    _write(show_id, key, c)
    return c


def set_default_take(show_id: str, key: str, take_id: str) -> dict:
    c = load(show_id, key)
    if not any(t.get("id") == take_id for t in c.get("takes") or []):
        raise FileNotFoundError(f"no take '{take_id}'")
    c["default_take"] = take_id
    c["updated_at"] = _now()
    _write(show_id, key, c)
    return c


def thumb_path(show_id: str, key: str, take_id: str) -> Path:
    """256px jpeg thumb, generated lazily on first request."""
    take_id = shows_mod.safe_segment(take_id, "take id")
    src = take_path(show_id, key, take_id)
    if not src.exists():
        raise FileNotFoundError(f"no take '{take_id}'")
    tdir = src.parent / ".thumbs"
    thumb = tdir / f"{take_id}.jpg"
    if thumb.exists() and thumb.stat().st_mtime >= src.stat().st_mtime:
        return thumb
    tdir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".jpg", dir=tdir, delete=False) as t:
        tmp = Path(t.name)
    try:
        subprocess.run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=256:256",
                        str(tmp)], check=True, capture_output=True, timeout=30)
        tmp.replace(thumb)
    except Exception:
        tmp.unlink(missing_ok=True)
        return src  # fall back to the full PNG
    return thumb


# ---- episode sync ------------------------------------------------------------------

def _episode_manifest(slug: str) -> tuple[dict, Path]:
    m = manifest_mod.load(slug)
    return m, ep_mod.episode_dir(slug)


def _invalidated_cloud_shots(m: dict, ep: Path, key: str) -> list[str]:
    """Cached cloud shots whose source_still resolves to this character's episode
    still — replacing the still flips their generation hash → re-bill on next
    stage 2."""
    cached = hfc.load_sidecar(hfc.clips_sidecar_path(ep), "shots")
    target = hfc.still_path(ep, key)
    out: list[str] = []
    for cue, shot in hfc.cloud_shots(m):
        still = hfc.resolve_still(shot, m, ep)
        if still and still.resolve() == target.resolve():
            sid = shot.get("id") or ""
            if sid in cached or hfc.clip_path(ep, sid).exists():
                out.append(sid)
    return out


def use_in_episode(show_id: str, key: str, slug: str, take_id: str | None = None,
                   overwrite_still: bool = False) -> dict:
    """Copy a take into an episode (stills/<key>.png) + merge the manifest
    character entry + stamp the stills sidecar so nothing re-bills."""
    c = load(show_id, key)
    tid = take_id or c.get("default_take")
    if not tid:
        raise FileNotFoundError(f"character '{key}' has no takes yet")
    src = take_path(show_id, key, tid)
    if not src.exists():
        raise FileNotFoundError(f"take file missing: {src}")
    take = next((t for t in c["takes"] if t["id"] == tid), {})

    m, ep = _episode_manifest(slug)
    dest = hfc.still_path(ep, key)
    take_sha = take.get("sha16") or hfc.file_sha(src)
    cur_sha = hfc.file_sha(dest)
    invalidates = _invalidated_cloud_shots(m, ep, key) if cur_sha != take_sha else []
    if dest.exists() and cur_sha != take_sha and not overwrite_still:
        return {"needs_confirm": True, "current_sha": cur_sha, "take_sha": take_sha,
                "invalidates": invalidates}

    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", dir=dest.parent, delete=False) as t:
        tmp = Path(t.name)
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)

    # Merge manifest entry: fill where empty, never clobber episode-local edits.
    chars = m.setdefault("characters", {})
    entry = chars.get(key)
    if not isinstance(entry, dict):
        entry = {"core": entry} if isinstance(entry, str) and entry else {}
        chars[key] = entry
    for field, lib_field in (("core", "core"), ("still_prompt", "still_prompt"),
                             ("seed", "seed")):
        if not entry.get(field) and c.get(lib_field) not in (None, ""):
            entry[field] = c[lib_field]
    entry["still"] = f"stills/{key}.png"
    entry["library_ref"] = f"{key}/{tid}"
    entry["library_sha"] = take_sha
    manifest_mod.save(slug, m)

    # Freshness stamp — exactly what the Higgsfield still generator writes, so
    # estimate/derive treat this still as fresh (free).
    sc_path = hfc.stills_sidecar_path(ep)
    entries = hfc.load_sidecar(sc_path, "stills")
    entries[key] = hfc.still_hash(entry, m)
    hfc.save_sidecar(sc_path, "stills", entries)

    return {"ok": True, "slug": slug, "take": tid, "sha": take_sha,
            "invalidates": invalidates}


def usage(show_id: str, key: str) -> list[dict]:
    """Per-episode sync state for this character across the show."""
    c = load(show_id, key)
    default = next((t for t in c.get("takes") or []
                    if t.get("id") == c.get("default_take")), None)
    lib_sha = (default or {}).get("sha16")
    out: list[dict] = []
    for e in ep_mod.list_episodes(show_id):
        slug = e.slug
        try:
            m, ep = _episode_manifest(slug)
        except Exception:
            continue
        entry = (m.get("characters") or {}).get(key)
        if entry is None:
            continue
        still = hfc.still_path(ep, key)
        cur_sha = hfc.file_sha(still)
        ref_sha = entry.get("library_sha") if isinstance(entry, dict) else None
        if cur_sha is None:
            state = "no_still"
        elif lib_sha and cur_sha == lib_sha:
            state = "in_sync"
        elif ref_sha and cur_sha == ref_sha:
            state = "stale"      # synced from the library once, library moved on
        else:
            state = "diverged"   # episode-local still, not from the library
        out.append({"slug": slug, "state": state})
    return out


def import_episode(show_id: str, slug: str) -> dict:
    """Seed library entries from an episode's manifest characters (+ stills as
    take-001 where present). Existing library characters are left alone."""
    m, ep = _episode_manifest(slug)
    created, skipped = [], []
    for key, val in (m.get("characters") or {}).items():
        try:
            shows_mod.safe_segment(key, "character key")
        except ValueError:
            skipped.append(key)
            continue
        if _json_path(show_id, key).exists():
            skipped.append(key)
            continue
        entry = val if isinstance(val, dict) else {"core": str(val or "")}
        c = create(show_id, key, {
            "name": key.replace("_", " ").title(),
            "core": entry.get("core") or "",
            "still_prompt": entry.get("still_prompt") or "",
            "seed": entry.get("seed"),
        })
        still = hfc.still_path(ep, key)
        if still.exists():
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
                tmp = Path(t.name)
            shutil.copyfile(still, tmp)
            add_take(show_id, key, tmp, engine="upload", model=None,
                     prompt=entry.get("still_prompt") or "", seed=None, params=None)
        created.append(c["key"])
    return {"created": created, "skipped": skipped}
