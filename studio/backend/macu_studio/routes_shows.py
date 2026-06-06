"""Show management + project export/import.

Routes:
  GET    /api/shows                      list shows (id/name/episodes_dir/count)
  POST   /api/shows                      create a show {id, name}
  GET    /api/shows/{show}/config        full show object (incl. episode_defaults)
  PUT    /api/shows/{show}/config        update editable show fields
  POST   /api/shows/{show}/episodes      scaffold a new episode {slug, title}
  GET    /api/episodes/{slug}/export     download a single-episode .zip (text files)
  GET    /api/shows/{show}/export        download a whole-show .zip
  POST   /api/import                     upload a .zip → merge/create (auto-detect)

Exports bundle TEXT files only (script.md / manifest.json / youtube.txt) plus an
export.json marker — the same portable-text philosophy as git-sync. Generated
media (vo/clips/final) is never bundled.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from . import shows as shows_mod
from . import episodes as ep_mod

router = APIRouter()

TEXT_FILES = ("script.md", "manifest.json", "youtube.txt")
EXPORT_VERSION = 1


# --------------------------------------------------------------------------- #
# Shows
# --------------------------------------------------------------------------- #

@router.get("/api/shows")
def get_shows():
    return {"shows": shows_mod.list_shows(), "default": shows_mod.DEFAULT_SHOW}


@router.post("/api/shows")
def post_show(body: dict = Body(...)):
    try:
        entry = shows_mod.create_show(body.get("id") or "", body.get("name") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "show": entry["id"], "name": entry["name"]}


@router.get("/api/shows/{show}/config")
def get_show_config(show: str):
    try:
        return shows_mod.get_show(show)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.put("/api/shows/{show}/config")
def put_show_config(show: str, body: dict = Body(...)):
    try:
        return shows_mod.save_show_config(show, body)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/api/shows/{show}/episodes")
def post_episode(show: str, body: dict = Body(...)):
    try:
        return shows_mod.create_episode(show, body.get("slug") or "", body.get("title") or "")
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

def _zip_response(buf: io.BytesIO, filename: str) -> StreamingResponse:
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _add_episode_text(zf: zipfile.ZipFile, ep_dir: Path, arc_prefix: str) -> int:
    n = 0
    for name in TEXT_FILES:
        f = ep_dir / name
        if f.exists():
            zf.write(f, f"{arc_prefix}{name}")
            n += 1
    return n


@router.get("/api/episodes/{slug}/export")
def export_episode(slug: str):
    try:
        ep_dir = ep_mod.episode_dir(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    show_id = shows_mod.show_of(slug)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("export.json", json.dumps({
            "kind": "episode", "show": show_id, "slug": slug,
            "version": EXPORT_VERSION, "exported_at": time.time(),
        }, indent=2))
        _add_episode_text(zf, ep_dir, f"episodes/{slug}/")
    return _zip_response(buf, f"{show_id}__{slug}.zip")


@router.get("/api/shows/{show}/export")
def export_show(show: str):
    try:
        cfg = shows_mod.get_show(show)
    except KeyError as e:
        raise HTTPException(404, str(e))
    ep_root = Path(cfg["episodes_dir"])
    buf = io.BytesIO()
    slugs: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("show.json", json.dumps(cfg, indent=2, ensure_ascii=False))
        if ep_root.exists():
            for entry in sorted(ep_root.iterdir(), key=lambda p: p.name):
                if entry.is_dir() and (entry / "manifest.json").exists():
                    _add_episode_text(zf, entry, f"episodes/{entry.name}/")
                    slugs.append(entry.name)
        zf.writestr("export.json", json.dumps({
            "kind": "show", "show": show, "name": cfg.get("name"),
            "episodes": slugs, "version": EXPORT_VERSION, "exported_at": time.time(),
        }, indent=2))
    return _zip_response(buf, f"{show}.zip")


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #

def _safe_slug(s: str) -> str | None:
    s = (s or "").strip().lower()
    return s if shows_mod._SLUG_RE.match(s) else None


def _write_episode_text(ep_dir: Path, files: dict[str, bytes]) -> str:
    """Write text files into an episode dir, backing up an existing manifest.
    Returns 'created' or 'updated'. Validates manifest.json parses first."""
    existed = ep_dir.exists() and (ep_dir / "manifest.json").exists()
    ep_dir.mkdir(parents=True, exist_ok=True)
    if "manifest.json" in files:
        try:
            json.loads(files["manifest.json"].decode("utf-8"))
        except Exception as e:
            raise ValueError(f"invalid manifest.json: {e}")
        mpath = ep_dir / "manifest.json"
        if mpath.exists():
            ts = time.strftime("%Y%m%d-%H%M%S")
            (ep_dir / f"manifest.json.bak.{ts}").write_bytes(mpath.read_bytes())
    for name, data in files.items():
        if name in TEXT_FILES:
            (ep_dir / name).write_bytes(data)
    return "updated" if existed else "created"


@router.post("/api/import")
async def import_zip(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "not a valid zip file")

    names = set(zf.namelist())
    if "export.json" not in names:
        raise HTTPException(400, "missing export.json — not a MACU Studio export")
    try:
        meta = json.loads(zf.read("export.json"))
    except Exception:
        raise HTTPException(400, "corrupt export.json")

    kind = meta.get("kind")
    show_id = _safe_slug(meta.get("show") or "")
    if not show_id:
        raise HTTPException(400, "export.json has no valid show id")

    # Group the bundled text files by episode slug (episodes/<slug>/<file>).
    per_ep: dict[str, dict[str, bytes]] = {}
    for n in names:
        parts = n.split("/")
        if len(parts) == 3 and parts[0] == "episodes" and parts[2] in TEXT_FILES:
            slug = _safe_slug(parts[1])
            if slug:
                per_ep.setdefault(slug, {})[parts[2]] = zf.read(n)

    # Ensure the target show exists (create it for a show-kind import; for an
    # episode-kind import into an unknown show, create a minimal placeholder).
    created_show = False
    try:
        shows_mod.get_show(show_id)
    except KeyError:
        name = meta.get("name") or show_id
        shows_mod.create_show(show_id, name)
        created_show = True

    # A show export carries its show.json — apply it (so a fresh show inherits
    # the sender's episode_defaults). On merge into an existing show we leave the
    # local config untouched.
    if kind == "show" and created_show and "show.json" in names:
        try:
            incoming = json.loads(zf.read("show.json"))
            shows_mod.save_show_config(show_id, incoming)
        except Exception:
            pass

    ep_root = shows_mod.show_episodes_dir(show_id)
    created: list[str] = []
    updated: list[str] = []
    errors: list[str] = []
    for slug, files in per_ep.items():
        # Don't let an import collide with an episode owned by a different show.
        try:
            owner, _ = shows_mod.resolve_episode(slug)
            if owner != show_id:
                errors.append(f"{slug}: slug already used by show '{owner}'")
                continue
        except FileNotFoundError:
            pass
        try:
            res = _write_episode_text(ep_root / slug, files)
            (created if res == "created" else updated).append(slug)
        except ValueError as e:
            errors.append(f"{slug}: {e}")

    return {
        "ok": not errors or bool(created or updated),
        "show": show_id,
        "kind": kind,
        "created_show": created_show,
        "created": sorted(created),
        "updated": sorted(updated),
        "errors": errors,
    }
