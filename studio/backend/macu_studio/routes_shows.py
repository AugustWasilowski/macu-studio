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
from . import voices as voices_mod
from . import config

router = APIRouter()

TEXT_FILES = ("script.md", "manifest.json", "youtube.txt")
EXPORT_VERSION = 1

# Shared hyperframes title-card templates (index.html + any local assets) live
# outside the episode dir. Exports bundle the ones an episode references so the
# title cards render on import; imports unpack them (overwriting).
HYPERFRAMES_TEMPLATES = config.SHARES / "assets" / "hyperframes" / "templates"
TEMPLATE_ARC_PREFIX = "assets/hyperframes/templates/"

# OmniVoice reference clips travel with an export so the receiving machine can
# re-clone the voices a show uses. The id is machine-specific, so manifests bind
# by voice_name (see _manifest_voice_names) and import rebinds in a deferred step.
VOICE_ARC_PREFIX = "voices/"


def _manifest_voice_names(ep_dir: Path) -> set[str]:
    """OmniVoice voice_names an episode's speaker_map references."""
    names: set[str] = set()
    mf = ep_dir / "manifest.json"
    if not mf.exists():
        return names
    try:
        data = json.loads(mf.read_text())
    except Exception:
        return names
    sm = (data.get("voice") or {}).get("speaker_map") or {}
    if isinstance(sm, dict):
        for v in sm.values():
            if isinstance(v, dict) and v.get("engine") == "omnivoice":
                n = v.get("voice_name")
                if isinstance(n, str) and n:
                    names.add(n)
    return names


def _add_voices(zf: zipfile.ZipFile, names: set[str], seen: set[str]) -> list[str]:
    """Bundle the reference clips for `names` under voices/<name>.wav. `seen`
    dedupes across episodes. Returns the names actually added."""
    added: list[str] = []
    for name, path in voices_mod.refs_for_names(sorted(names)).items():
        if name in seen:
            continue
        seen.add(name)
        zf.write(path, f"{VOICE_ARC_PREFIX}{path.name}")
        added.append(name)
    return added


def _manifest_template_names(ep_dir: Path) -> set[str]:
    """Hyperframes composition names an episode's title_assets reference."""
    names: set[str] = set()
    mf = ep_dir / "manifest.json"
    if not mf.exists():
        return names
    try:
        data = json.loads(mf.read_text())
    except Exception:
        return names
    ta = data.get("title_assets")
    if isinstance(ta, dict):
        for v in ta.values():
            if isinstance(v, dict) and v.get("source") == "hyperframes":
                comp = v.get("composition")
                if isinstance(comp, str) and comp:
                    names.add(comp)
    return names


def _add_templates(zf: zipfile.ZipFile, names: set[str], seen: set[str]) -> None:
    """Bundle each referenced template dir under assets/hyperframes/templates/<name>/.
    `seen` dedupes across episodes in a show export."""
    for name in sorted(names):
        if name in seen:
            continue
        seen.add(name)
        tdir = HYPERFRAMES_TEMPLATES / name
        if not tdir.is_dir():
            continue
        for f in sorted(tdir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(HYPERFRAMES_TEMPLATES)
                zf.write(f, f"{TEMPLATE_ARC_PREFIX}{rel.as_posix()}")


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
def export_episode(slug: str, voices: bool = True):
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
        _add_templates(zf, _manifest_template_names(ep_dir), set())
        vnames = _add_voices(zf, _manifest_voice_names(ep_dir), set()) if voices else []
        if vnames:
            zf.writestr("voices.json", json.dumps(
                {"voices": [{"name": n, "language": "English"} for n in vnames]}, indent=2))
    return _zip_response(buf, f"{show_id}__{slug}.zip")


@router.get("/api/shows/{show}/export")
def export_show(show: str, voices: bool = True):
    try:
        cfg = shows_mod.get_show(show)
    except KeyError as e:
        raise HTTPException(404, str(e))
    ep_root = Path(cfg["episodes_dir"])
    buf = io.BytesIO()
    slugs: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("show.json", json.dumps(cfg, indent=2, ensure_ascii=False))
        seen_templates: set[str] = set()
        seen_voices: set[str] = set()
        added_voices: list[str] = []
        if ep_root.exists():
            for entry in sorted(ep_root.iterdir(), key=lambda p: p.name):
                if entry.is_dir() and (entry / "manifest.json").exists():
                    _add_episode_text(zf, entry, f"episodes/{entry.name}/")
                    _add_templates(zf, _manifest_template_names(entry), seen_templates)
                    if voices:
                        added_voices += _add_voices(zf, _manifest_voice_names(entry), seen_voices)
                    slugs.append(entry.name)
        if added_voices:
            zf.writestr("voices.json", json.dumps(
                {"voices": [{"name": n, "language": "English"} for n in added_voices]}, indent=2))
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


def _extract_voices(zf: zipfile.ZipFile, names) -> list[str]:
    """Drop bundled reference clips into the local refs/ — OVERWRITES existing.
    Re-cloning into OmniVoice is a separate (GPU) step. Returns the voice names."""
    out: list[str] = []
    for n in names:
        if not n.startswith(VOICE_ARC_PREFIX) or n.endswith("/"):
            continue
        fn = n[len(VOICE_ARC_PREFIX):]
        if "/" in fn or "\\" in fn or ".." in fn or not fn.endswith(".wav"):
            continue
        voices_mod.import_ref(fn[:-4], zf.read(n))
        out.append(fn[:-4])
    return sorted(set(out))


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
    # A voices-only export carries no show — just drop the reference clips. The
    # caller offers the optional GPU re-clone step afterward.
    if kind == "voices":
        return {"ok": True, "kind": "voices", "voices": _extract_voices(zf, names)}
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

    # Unpack bundled hyperframes templates into the shared templates dir (OVERWRITE).
    templates: set[str] = set()
    base = HYPERFRAMES_TEMPLATES.resolve()
    for n in names:
        if not n.startswith(TEMPLATE_ARC_PREFIX) or n.endswith("/"):
            continue
        rel = n[len(TEMPLATE_ARC_PREFIX):]
        dest = (HYPERFRAMES_TEMPLATES / rel).resolve()
        if not str(dest).startswith(str(base) + "/"):   # zip path-traversal guard
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(n))
        templates.add(rel.split("/")[0])

    # Drop bundled voice reference clips (re-cloning is the optional GPU step).
    voices_imported = _extract_voices(zf, names)

    return {
        "ok": not errors or bool(created or updated),
        "show": show_id,
        "kind": kind,
        "created_show": created_show,
        "created": sorted(created),
        "updated": sorted(updated),
        "templates": sorted(templates),
        "voices": voices_imported,
        "errors": errors,
    }
