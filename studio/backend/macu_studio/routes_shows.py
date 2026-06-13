"""Show management + project export/import.

Routes:
  GET    /api/shows                      list shows (id/name/episodes_dir/count)
  POST   /api/shows                      create a show {id, name}
  GET    /api/shows/{show}/config        full show object (incl. episode_defaults)
  PUT    /api/shows/{show}/config        update editable show fields
  POST   /api/shows/{show}/episodes      scaffold a new episode {slug, title}
  GET    /api/archive                    list archived episodes (by show) + shows
  POST   .../episodes/{slug}/archive     move an episode (+ family) into archived/
  POST   .../episodes/{name}/unarchive   restore an archived episode {new_slug?}
  POST   /api/shows/{show}/archive       move a whole show into _archived-shows/
  POST   /api/shows/{name}/unarchive     restore an archived show
  GET    /api/episodes/{slug}/export     download a single-episode .zip (text files)
  GET    /api/shows/{show}/export        download a whole-show .zip
  POST   /api/import                     upload a .zip → merge/create (auto-detect)

Exports bundle the portable WORKING TEXT (script.md / manifest.json) plus an
export.json marker, and — when assets=True (default) — the binaries a recipient
needs but can't trivially recreate: OmniVoice reference clips, referenced SFX /
music, hyperframes title templates, the show's character library (character.json
+ takes), each episode's reference stills, and the PAID Higgsfield cloud clips.
Stills and HF clips ride with their cache sidecars (stills/.cache.json,
clips/.hf_cache.json) so a re-import is a guaranteed cache hit and never re-bills.
Cheap-to-regenerate local renders (zeroscope .webp clips, vo/, final/) are never
bundled. The text-only one-click Sync (studiosync.py) is a separate path.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from . import shows as shows_mod
from . import episodes as ep_mod
from . import voices as voices_mod
from . import manifest as manifest_mod
from . import characters as chars_mod
from . import config

router = APIRouter()

TEXT_FILES = ("script.md", "manifest.json")  # youtube.txt deprecated → folded into manifest.json
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


# SFX + music files a show uses (referenced by name in the manifest) travel with the
# export so a recipient can render without re-sourcing them. The provenance catalogs
# (how each was made — freesound URL / agen prompt+seed) ride along as READMEs.
SFX_DIR = config.SHARES / "assets" / "sfx"
MUSIC_DIR = config.SHARES / "assets" / "music"
SFX_ARC_PREFIX = "assets/sfx/"
MUSIC_ARC_PREFIX = "assets/music/"


def _manifest_audio_files(ep_dir: Path) -> tuple[set[str], set[str]]:
    """(sfx filenames, music filenames) an episode's manifest references."""
    sfx: set[str] = set()
    music: set[str] = set()
    mf = ep_dir / "manifest.json"
    if not mf.exists():
        return sfx, music
    try:
        d = json.loads(mf.read_text())
    except Exception:
        return sfx, music
    for s in (d.get("sfx") or []):
        if isinstance(s, dict) and isinstance(s.get("file"), str):
            sfx.add(s["file"])
    mu = d.get("music") or {}
    if isinstance(mu, dict):
        for c in (mu.get("clips") or []):
            if isinstance(c, str):
                music.add(c)
        for b in (mu.get("beds") or []):
            if isinstance(b, dict) and isinstance(b.get("file"), str):
                music.add(b["file"])
    return sfx, music


def _add_audio(zf: zipfile.ZipFile, files: set[str], src_dir: Path, arc_prefix: str, seen: set[str]) -> None:
    for fn in sorted(files):
        if fn in seen or "/" in fn or "\\" in fn or ".." in fn:
            continue
        p = src_dir / fn
        if not p.is_file():
            continue
        seen.add(fn)
        zf.write(p, f"{arc_prefix}{fn}")


def _bundle_assets(zf: zipfile.ZipFile, ep_dirs: list[Path]) -> list[str]:
    """Bundle the binary source assets the manifests reference — OmniVoice reference
    clips, SFX, and music — plus the asset catalog READMEs (the 'how it was made'
    metadata). Deduped across episodes. Returns the voice names bundled."""
    seen_v: set[str] = set()
    seen_s: set[str] = set()
    seen_m: set[str] = set()
    voices_added: list[str] = []
    for ep in ep_dirs:
        voices_added += _add_voices(zf, _manifest_voice_names(ep), seen_v)
        sfx_files, music_files = _manifest_audio_files(ep)
        _add_audio(zf, sfx_files, SFX_DIR, SFX_ARC_PREFIX, seen_s)
        _add_audio(zf, music_files, MUSIC_DIR, MUSIC_ARC_PREFIX, seen_m)
    for src, arc in ((SFX_DIR / "README.md", SFX_ARC_PREFIX + "README.md"),
                     (MUSIC_DIR / "README.md", MUSIC_ARC_PREFIX + "README.md")):
        if src.is_file():
            zf.write(src, arc)
    return voices_added


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


# Character library (show-level): SHARES/shows/<show>/characters/<key>/ holds
# character.json + takes/take-NNN.png. Bundled so the receiving Studio inherits
# the reference-still roster and its provenance. takes/.thumbs/ are regenerable —
# never bundled.
CHARACTERS_ARC_PREFIX = "characters/"

# Episode generated binaries worth carrying: the reference stills (+ their cache
# sidecar) and the PAID Higgsfield cloud clips (+ their sidecar). Local zeroscope
# renders (.webp / non-hf .mp4), vo/, and final/ are cheap to regenerate and stay
# out. Sidecars travel with the binaries so stage 2 sees a cache hit on import and
# never re-bills (hf_cache.py: matching hash + existing artifact ⇒ skip).
STILLS_CACHE = ".cache.json"
HF_CACHE = ".hf_cache.json"


def _manifest_character_keys(ep_dir: Path) -> set[str]:
    """Character library keys an episode's manifest references."""
    mf = ep_dir / "manifest.json"
    if not mf.exists():
        return set()
    try:
        d = json.loads(mf.read_text())
    except Exception:
        return set()
    c = d.get("characters")
    return set(c.keys()) if isinstance(c, dict) else set()


def _add_characters(zf: zipfile.ZipFile, show_id: str, keys: set[str], seen: set[str]) -> list[str]:
    """Bundle each character's character.json + takes/*.png under
    characters/<key>/ (skipping .thumbs). `seen` dedupes. Returns keys added."""
    added: list[str] = []
    for key in sorted(keys):
        if key in seen:
            continue
        seen.add(key)
        try:
            cdir = chars_mod.char_dir(show_id, key)
        except ValueError:
            continue
        cj = cdir / "character.json"
        if not cj.is_file():
            continue
        zf.write(cj, f"{CHARACTERS_ARC_PREFIX}{key}/character.json")
        takes = cdir / "takes"
        if takes.is_dir():
            for f in sorted(takes.iterdir()):
                if f.is_file() and f.suffix.lower() == ".png":
                    zf.write(f, f"{CHARACTERS_ARC_PREFIX}{key}/takes/{f.name}")
        added.append(key)
    return added


def _add_episode_stills(zf: zipfile.ZipFile, ep_dir: Path, arc_prefix: str) -> int:
    """Bundle stills/*.png + stills/.cache.json (the billing sidecar)."""
    sdir = ep_dir / "stills"
    if not sdir.is_dir():
        return 0
    n = 0
    for f in sorted(sdir.iterdir()):
        if f.is_file() and (f.suffix.lower() == ".png" or f.name == STILLS_CACHE):
            zf.write(f, f"{arc_prefix}stills/{f.name}")
            n += 1
    return n


def _add_episode_hf_clips(zf: zipfile.ZipFile, ep_dir: Path, arc_prefix: str) -> int:
    """Bundle the paid Higgsfield clips (clips/hf_*.mp4) + clips/.hf_cache.json.
    Local zeroscope renders are intentionally excluded."""
    cdir = ep_dir / "clips"
    if not cdir.is_dir():
        return 0
    n = 0
    for f in sorted(cdir.iterdir()):
        if not f.is_file():
            continue
        if (f.name.startswith("hf_") and f.suffix.lower() == ".mp4") or f.name == HF_CACHE:
            zf.write(f, f"{arc_prefix}clips/{f.name}")
            n += 1
    return n


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
# Open show folder in the OS file manager
# --------------------------------------------------------------------------- #
#
# Only meaningful when the Studio process runs on the machine the user is sitting
# at — the common localhost install, including WSL, where explorer.exe crosses the
# Linux→Windows boundary. On a headless or remote box there is no desktop to open,
# so we return opened=false plus the path(s) and the UI falls back to "copy this
# path". Never an HTTP error for "couldn't open"; only unknown-show 404s.

def _show_folder(show: str) -> Path:
    d = Path(shows_mod.get_show(show)["episodes_dir"])
    # Registry shows live at SHARES/shows/<id>/episodes — open the show base
    # (episodes + assets). The legacy default show's flat dir IS its content dir.
    if d.name == "episodes" and d.parent.name == show:
        return d.parent
    return d


def _wsl_windows_path(path: Path) -> str | None:
    r"""The \\wsl.localhost\... form of *path*, or None when not running under WSL."""
    try:
        if "microsoft" not in Path("/proc/version").read_text().lower():
            return None
    except OSError:
        return None
    try:
        out = subprocess.run(["wslpath", "-w", str(path)],
                             capture_output=True, text=True, timeout=5)
        return (out.stdout.strip() or None) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _open_in_file_manager(path: Path, win_path: str | None) -> tuple[bool, str | None]:
    """(opened, reason). Fire-and-forget; never raises."""
    try:
        if win_path:
            # explorer.exe exits 1 even on success — launch detached, don't check.
            subprocess.Popen(["explorer.exe", win_path], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, None
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], start_new_session=True)
            return True, None
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            if shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", str(path)], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, None
            return False, "no xdg-open on this system"
        return False, "no desktop session on the Studio machine"
    except OSError as e:
        return False, str(e)


@router.post("/api/shows/{show}/open-folder")
def post_open_show_folder(show: str):
    try:
        folder = _show_folder(show)
    except KeyError as e:
        raise HTTPException(404, str(e))
    win_path = _wsl_windows_path(folder)
    opened, reason = _open_in_file_manager(folder, win_path)
    return {"ok": True, "opened": opened, "path": str(folder),
            "windows_path": win_path, "reason": reason}


# --------------------------------------------------------------------------- #
# Archive / unarchive — physically move episodes & shows out of (and back into)
# the active tree. The move is the source of truth; restore/browse is the
# Settings → Archive panel (GET /api/archive). Moves are same-filesystem renames
# but run in a threadpool to stay off the event loop on the rare cross-fs fallback.
# --------------------------------------------------------------------------- #

@router.get("/api/archive")
def get_archive():
    return shows_mod.list_archived()


@router.post("/api/shows/{show}/episodes/{slug}/archive")
async def post_archive_episode(show: str, slug: str):
    try:
        return await run_in_threadpool(shows_mod.archive_episode, slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/shows/{show}/episodes/{name}/unarchive")
async def post_unarchive_episode(show: str, name: str, body: dict = Body(default={})):
    new_slug = (body or {}).get("new_slug") or None
    try:
        return await run_in_threadpool(shows_mod.unarchive_episode, show, name, new_slug)
    except shows_mod.SlugInUse as e:
        raise HTTPException(409, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/shows/{show}/archive")
async def post_archive_show(show: str):
    try:
        return await run_in_threadpool(shows_mod.archive_show, show)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/shows/{name}/unarchive")
async def post_unarchive_show(name: str):
    try:
        return await run_in_threadpool(shows_mod.unarchive_show, name)
    except shows_mod.SlugInUse as e:
        raise HTTPException(409, str(e))
    except FileNotFoundError as e:
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
def export_episode(slug: str, assets: bool = True):
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
        vnames: list[str] = []
        if assets:
            vnames = _bundle_assets(zf, [ep_dir])
            _add_episode_stills(zf, ep_dir, f"episodes/{slug}/")
            _add_episode_hf_clips(zf, ep_dir, f"episodes/{slug}/")
            _add_characters(zf, show_id, _manifest_character_keys(ep_dir), set())
        if vnames:
            zf.writestr("voices.json", json.dumps(
                {"voices": [{"name": n, "language": "English"} for n in vnames]}, indent=2))
    return _zip_response(buf, f"{show_id}__{slug}.zip")


@router.get("/api/shows/{show}/export")
def export_show(show: str, assets: bool = True):
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
        ep_dirs: list[Path] = []
        if ep_root.exists():
            for entry in sorted(ep_root.iterdir(), key=lambda p: p.name):
                if entry.is_dir() and (entry / "manifest.json").exists():
                    _add_episode_text(zf, entry, f"episodes/{entry.name}/")
                    _add_templates(zf, _manifest_template_names(entry), seen_templates)
                    if assets:
                        _add_episode_stills(zf, entry, f"episodes/{entry.name}/")
                        _add_episode_hf_clips(zf, entry, f"episodes/{entry.name}/")
                    ep_dirs.append(entry)
                    slugs.append(entry.name)
        added_voices = _bundle_assets(zf, ep_dirs) if assets else []
        if assets:
            # The whole show's character library (roster reuse across episodes).
            lib_keys = {c["key"] for c in chars_mod.list_chars(show)}
            _add_characters(zf, show, lib_keys, set())
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


def _extract_audio(zf: zipfile.ZipFile, names, prefix: str, dst_dir: Path) -> list[str]:
    """Drop bundled SFX/music files into the local assets dir — OVERWRITES existing.
    Skips the provenance README so a local catalog isn't clobbered. Returns filenames."""
    out: list[str] = []
    for n in names:
        if not n.startswith(prefix) or n.endswith("/"):
            continue
        fn = n[len(prefix):]
        if "/" in fn or "\\" in fn or ".." in fn or fn.lower() == "readme.md":
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / fn).write_bytes(zf.read(n))
        out.append(fn)
    return sorted(set(out))


DOCS_ROOT = config.REPO_ROOT / "docs" / "shows"


def _extract_docs(zf: zipfile.ZipFile, names) -> list[str]:
    """Unpack canon docs (docs/shows/<id>/*.md — character bible, arcs, routines) into the
    local docs dir (OVERWRITE), path-traversal guarded. Lets a 'riff' bring the show's bible."""
    base = DOCS_ROOT.resolve()
    out: list[str] = []
    for n in names:
        if not n.startswith("docs/shows/") or n.endswith("/") or not n.lower().endswith(".md"):
            continue
        rel = n[len("docs/shows/"):]
        dest = (DOCS_ROOT / rel).resolve()
        if not str(dest).startswith(str(base) + "/"):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(n))
        out.append(rel)
    return sorted(out)


def _merge_cache_sidecar(dest: Path, raw: bytes) -> None:
    """Merge an incoming stills/.cache.json or clips/.hf_cache.json into the local
    one (incoming entries win) rather than clobbering local cache state. Preserves
    cache hits for stills/shots that exist locally but aren't in the bundle."""
    try:
        inc = json.loads(raw)
    except Exception:
        return
    inner = "stills" if isinstance(inc.get("stills"), dict) else (
        "shots" if isinstance(inc.get("shots"), dict) else None)
    if not inner:
        return
    merged: dict = {}
    if dest.exists():
        try:
            merged = dict((json.loads(dest.read_text()).get(inner)) or {})
        except Exception:
            merged = {}
    merged.update(inc.get(inner) or {})
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"version": 1, inner: merged}, indent=2, sort_keys=True))


def _extract_characters(zf: zipfile.ZipFile, names, show_id: str) -> list[str]:
    """Unpack the bundled character library (character.json + takes/*.png) into
    SHARES/shows/<show>/characters/<key>/. Backs up an existing character.json;
    validates it parses. Path/segment guarded. Returns the keys touched."""
    touched: list[str] = []
    for n in names:
        if not n.startswith(CHARACTERS_ARC_PREFIX) or n.endswith("/"):
            continue
        parts = n[len(CHARACTERS_ARC_PREFIX):].split("/")
        try:
            key = shows_mod.safe_segment(parts[0], "character key")
            cdir = chars_mod.char_dir(show_id, key)
        except (ValueError, IndexError):
            continue
        if len(parts) == 2 and parts[1] == "character.json":
            raw = zf.read(n)
            try:
                json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            cdir.mkdir(parents=True, exist_ok=True)
            cj = cdir / "character.json"
            if cj.exists():
                ts = time.strftime("%Y%m%d-%H%M%S")
                (cdir / f"character.json.bak.{ts}").write_bytes(cj.read_bytes())
            cj.write_bytes(raw)
            if key not in touched:
                touched.append(key)
        elif len(parts) == 3 and parts[1] == "takes":
            try:
                fn = shows_mod.safe_segment(parts[2], "take file")
            except ValueError:
                continue
            if not fn.lower().endswith(".png"):
                continue
            tdir = cdir / "takes"
            tdir.mkdir(parents=True, exist_ok=True)
            (tdir / fn).write_bytes(zf.read(n))
            if key not in touched:
                touched.append(key)
    return sorted(touched)


def _extract_episode_binaries(zf: zipfile.ZipFile, names, ep_root: Path,
                              allowed: set[str]) -> dict[str, int]:
    """Unpack bundled episode stills + paid HF clips into the local episode dirs,
    merging their cache sidecars (so nothing re-bills). Only for episodes we just
    wrote/own (`allowed`). Path/slug guarded. Returns {'stills': n, 'clips': n}."""
    counts = {"stills": 0, "clips": 0}
    for n in names:
        parts = n.split("/")
        if len(parts) != 4 or parts[0] != "episodes" or n.endswith("/"):
            continue
        sub = parts[2]
        if sub not in ("stills", "clips"):
            continue
        slug = _safe_slug(parts[1])
        if not slug or slug not in allowed:
            continue
        fn = parts[3]
        if "/" in fn or "\\" in fn or ".." in fn:
            continue
        if sub == "stills" and not (fn.lower().endswith(".png") or fn == STILLS_CACHE):
            continue
        if sub == "clips" and not ((fn.startswith("hf_") and fn.lower().endswith(".mp4"))
                                   or fn == HF_CACHE):
            continue
        dest_dir = ep_root / slug / sub
        raw = zf.read(n)
        if fn in (STILLS_CACHE, HF_CACHE):
            _merge_cache_sidecar(dest_dir / fn, raw)
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / fn).write_bytes(raw)
            counts[sub] += 1
    return counts


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
    # caller offers the optional GPU re-clone step afterward. Shape matches the
    # full import response so the UI's one handler works for every kind.
    if kind == "voices":
        return {
            "ok": True,
            "show": "",
            "kind": "voices",
            "created_show": False,
            "created": [],
            "updated": [],
            "templates": [],
            "voices": _extract_voices(zf, names),
            "sfx": [],
            "music": [],
            "docs": [],
            "characters": [],
            "stills": 0,
            "clips": 0,
            "errors": [],
        }
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

    # Riff lineage: importing into a brand-new local show = a fork. Stamp each imported
    # episode's manifest with the source show id (from export.json) — unless it already
    # records one, so a riff-of-a-riff keeps the *original* origin. Merges into an existing
    # local show (round-trip / restore) are not riffs, so we leave them alone.
    if created_show:
        for slug in created + updated:
            try:
                m = manifest_mod.load(slug)
                if not m.get("riffed_from"):
                    m["riffed_from"] = show_id
                    manifest_mod.save(slug, m)
            except Exception:
                pass

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

    # Drop bundled voice reference clips (re-cloning is the optional GPU step) and the
    # SFX / music files the manifests reference (overwriting).
    voices_imported = _extract_voices(zf, names)
    sfx_imported = _extract_audio(zf, names, SFX_ARC_PREFIX, SFX_DIR)
    music_imported = _extract_audio(zf, names, MUSIC_ARC_PREFIX, MUSIC_DIR)
    docs_imported = _extract_docs(zf, names)

    # Character library + episode binaries (reference stills, paid HF clips) with
    # their cache sidecars merged so a re-import is a cache hit and never re-bills.
    chars_imported = _extract_characters(zf, names, show_id)
    ep_bins = _extract_episode_binaries(zf, names, ep_root, set(created) | set(updated))

    return {
        "ok": not errors or bool(created or updated),
        "show": show_id,
        "kind": kind,
        "created_show": created_show,
        "created": sorted(created),
        "updated": sorted(updated),
        "templates": sorted(templates),
        "voices": voices_imported,
        "sfx": sfx_imported,
        "music": music_imported,
        "docs": docs_imported,
        "characters": chars_imported,
        "stills": ep_bins["stills"],
        "clips": ep_bins["clips"],
        "errors": errors,
    }
