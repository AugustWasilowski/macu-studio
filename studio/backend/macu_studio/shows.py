"""Multi-show registry + show-scoped helpers.

MACU Studio was originally hardwired for one show ("The MACU Report"). This
module wraps a thin show layer around that:

* A single git-tracked registry file ``studio/shows.json`` — a list of show
  objects ``{id, name, episodes_dir, assets_dir, title_prefix, episode_defaults}``.
  ``episode_defaults`` is the show-level config (voice/comfyui/style/subtitles/
  music/characters/broll) that every new episode's manifest is seeded from.
* The default show ``the-macu-report`` keeps its existing flat episodes dir
  (``config.EPISODES``) untouched — zero migration. New shows get their own
  ``episodes_dir`` under ``SHARES/shows/<id>/episodes``.

Slugs are kept globally unique across shows, so ``resolve_episode(slug)`` can
find an episode's owning show by scanning the registry — which lets every
existing ``/api/episodes/{slug}/...`` route stay show-agnostic with no signature
change (``episodes.episode_dir`` just resolves through here).
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

REGISTRY = config.STUDIO_ROOT / "shows.json"

# Where a whole archived show's tree is parked (sibling of SHARES/shows). Archived
# episodes live per-show under show_archive_dir() — see archive_episode().
ARCHIVED_SHOWS_ROOT = config.SHARES / "_archived-shows"
# Sidecar written into each archived container (episode-family or show). Dot-prefixed
# so it is never picked up by TEXT_FILES exports or git-sync.
ARCHIVE_SIDECAR = ".archive.json"

# Per-show canon docs seeded into docs/shows/<id>/ on show creation, copied from
# docs/_templates/show/ with {{SHOW_NAME}}/{{SHOW_ID}}/{{DATE}} substituted. See
# scaffold_show_docs(). The template dir is invisible to the Docs panel (which
# only globs _common + shows/<id>).
DOC_TEMPLATE_DIR = config.REPO_ROOT / "docs" / "_templates" / "show"
SHOW_DOCS_ROOT = config.REPO_ROOT / "docs" / "shows"

# DEFAULT_SHOW is the legacy owner-id of the flat episodes dir (config.EPISODES) on
# long-lived installs. It is NOT force-created — a fresh checkout seeds STARTER_SHOW
# instead (see load_registry). Kept as a constant so existing code/imports resolve.
DEFAULT_SHOW = "the-macu-report"
DEFAULT_SHOW_NAME = "The MACU Report"

# What a fresh-clone install seeds when shows.json is absent or empty: one neutral
# starter show with working technical defaults and NO creative content. shows.json
# and docs/shows/<id>/ are gitignored, so a clone ships none of the author's shows.
STARTER_SHOW = "example-show"
STARTER_SHOW_NAME = "Example Show"

# Show-level manifest blocks copied into a new episode's manifest. Episode-only
# blocks (cues/sfx/overlays/episode/title/season/episode_num) are NOT seeded.
_DEFAULTS_KEYS = (
    "voice", "comfyui", "style", "subtitles", "music",
    "characters", "broll", "title_assets", "render_rule",
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")

# A single safe path segment (cue id, shot/title key, composition name): letters,
# digits, dot, dash, underscore — no slash, backslash, or `..`. Use to sanitize any
# user-supplied value that becomes a filesystem path component.
_SAFE_SEG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def safe_segment(name: str, what: str = "name") -> str:
    """Validate a single path segment, or raise ValueError. Rejects `..`, slashes,
    and leading dots so the value can't escape its intended directory."""
    if (not isinstance(name, str) or ".." in name or "/" in name or "\\" in name
            or not _SAFE_SEG_RE.match(name)):
        raise ValueError(f"invalid {what}: {name!r}")
    return name


# --------------------------------------------------------------------------- #
# Portability — resolve machine-specific paths/endpoints at read time so one
# git-tracked shows.json works on any machine. The committed file holds Max-shaped
# values; on a different machine (MACU_SHARES set in .env) paths rebase to the live
# SHARES and LAN-IP service endpoints localize to loopback. Identity on Max.
# --------------------------------------------------------------------------- #

_DEFAULT_SHARES = "/mnt/storage/shares/MACU"  # the value baked into the committed shows.json
_LAN_ENDPOINT_RE = re.compile(r"^(https?)://(?:10\.0\.0\.\d+|0\.0\.0\.0)(:\d+)?(/.*)?$")


def _rebase(p: str | None) -> str | None:
    """If a stored absolute path is under the committed default SHARES, swap that
    prefix for the live config.SHARES. No-op on Max (SHARES == default)."""
    if not isinstance(p, str) or not p:
        return p
    live = str(config.SHARES)
    if p == _DEFAULT_SHARES:
        return live
    if p.startswith(_DEFAULT_SHARES + "/"):
        return live + p[len(_DEFAULT_SHARES):]
    return p


def _localize_endpoint(url: str | None) -> str | None:
    """Rewrite a stored LAN service endpoint (10.0.0.x / 0.0.0.0) to loopback;
    services run locally on whatever machine reads this. Leaves other hosts alone."""
    if not isinstance(url, str):
        return url
    m = _LAN_ENDPOINT_RE.match(url)
    if not m:
        return url
    scheme, port, path = m.group(1), m.group(2) or "", m.group(3) or ""
    return f"{scheme}://127.0.0.1{port}{path}"


def _portablize_defaults(defaults: dict[str, Any]) -> dict[str, Any]:
    """In-place: localize endpoints + rebase paths inside an episode_defaults block."""
    if not isinstance(defaults, dict):
        return defaults
    voice = defaults.get("voice")
    if isinstance(voice, dict):
        if "endpoint" in voice:
            voice["endpoint"] = _localize_endpoint(voice.get("endpoint"))
        eps = voice.get("endpoints")
        if isinstance(eps, dict):
            for k, v in list(eps.items()):
                eps[k] = _localize_endpoint(v)
    comfy = defaults.get("comfyui")
    if isinstance(comfy, dict) and "endpoint" in comfy:
        comfy["endpoint"] = _localize_endpoint(comfy.get("endpoint"))
    subs = defaults.get("subtitles")
    if isinstance(subs, dict):
        for key in ("font_file", "fontsdir"):
            if key in subs:
                subs[key] = _rebase(subs.get(key))
    music = defaults.get("music")
    if isinstance(music, dict) and "source_dir" in music:
        music["source_dir"] = _rebase(music.get("source_dir"))
    return defaults


def _portablize(show: dict[str, Any]) -> dict[str, Any]:
    """In-place: make one show entry machine-local (paths + endpoints)."""
    if not isinstance(show, dict):
        return show
    if "episodes_dir" in show:
        show["episodes_dir"] = _rebase(show.get("episodes_dir"))
    if "assets_dir" in show:
        show["assets_dir"] = _rebase(show.get("assets_dir"))
    _portablize_defaults(show.get("episode_defaults") or {})
    return show


# --------------------------------------------------------------------------- #
# Registry load / save
# --------------------------------------------------------------------------- #

def _starter_defaults() -> dict[str, Any]:
    """Built-in technical episode_defaults for a fresh install: working pipeline
    config (loopback service endpoints, the bundled B&W analog look, the Better VCR
    subtitle font) with empty creative blocks. Paths use config.SHARES so they land
    on whatever machine reads them. Ships NO show-specific cast/canon."""
    assets = config.SHARES / "assets"
    return {
        "voice": {
            "engine": "piper",
            "model": "default",
            "endpoint": "http://127.0.0.1:5050/",
            "method": "POST",
            "body": "{\"text\": \"<line>\"}",
            "format": "wav 22050Hz mono s16",
            "out_pattern": "vo/<cue_id>.wav",
        },
        "comfyui": {
            "workflow": "will-smith-modelscope-t2v",
            "checkpoint": "zeroscope_v2_576w",
            "endpoint": "http://127.0.0.1:8188/",
            "frames": 24, "width": 384, "height": 384,
            "steps": 30, "cfg": 15, "extract_fps": 8,
            "out_pattern": "clips/<shot_id>.webp",
        },
        "style": {
            "suffix": ", black and white, grainy vintage analog television footage, "
                      "1970s broadcast, retro futurism, low resolution, washed out, soft focus",
            "negative": "shutterstock, watermark, text, caption, logo, color, colour, modern, "
                        "smartphone, digital screen, hd, 4k, sharp, blurry, low quality, "
                        "distorted, deformed, mutated, extra limbs, extra fingers",
        },
        "subtitles": {
            "font": "Better VCR",
            "font_file": str(assets / "fonts" / "BetterVCR.ttf"),
            "fontsdir": str(assets / "fonts"),
            "fontsize": 18,
            "force_style": "FontName=Better VCR,Fontsize=18,PrimaryColour=&H00FFFFFF,"
                           "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
                           "MarginV=32,Alignment=2",
        },
        "music": {
            "enabled": False,
            "source_dir": str(assets / "music"),
            "clips": [], "gain": 0.16, "fade_in": 1.5, "fade_out": 2.5,
            "random": True, "beds": [],
        },
        "characters": {},
        "broll": {},
        "title_assets": {},
    }


def _starter_registry() -> list[dict[str, Any]]:
    """Seed registry for a fresh install: a single neutral example show. Its
    episodes live under SHARES/shows/example-show/episodes (not the legacy flat dir)."""
    base = config.SHARES / "shows" / STARTER_SHOW
    return [{
        "id": STARTER_SHOW,
        "name": STARTER_SHOW_NAME,
        "episodes_dir": str(base / "episodes"),
        "assets_dir": str(config.SHARES / "assets"),
        "title_prefix": "",
        "episode_defaults": _starter_defaults(),
    }]


def _seed_base_defaults() -> dict[str, Any]:
    """Technical episode_defaults a brand-new show inherits: the live default show's
    tuned blocks if that show exists (long-lived install), else the built-in starter
    config (fresh install). The caller blanks the creative blocks."""
    try:
        base = get_show(DEFAULT_SHOW).get("episode_defaults") or {}
        if base:
            return base
    except KeyError:
        pass
    return _starter_defaults()


def load_registry(raw: bool = False) -> list[dict[str, Any]]:
    """Read shows.json, auto-seeding it with the default show on first run.

    Returns values PORTABLIZED for reading — paths rebased to config.SHARES and
    LAN service endpoints localized to loopback — so the one committed file works
    on any machine. Mutators pass raw=True to get the canonical on-disk values
    (so they write canonical, not machine-local, data back)."""
    if not REGISTRY.exists():
        data = _starter_registry()
        _write_registry(data)
    else:
        try:
            data = json.loads(REGISTRY.read_text())
        except Exception:
            data = []
        if not isinstance(data, list):
            data = []
        # Seed the neutral starter only when the registry is genuinely empty. We do
        # NOT force any specific show to exist — that force-injection is what kept
        # re-creating The MACU Report on installs that had legitimately removed it.
        if not data:
            data = _starter_registry()
            _write_registry(data)
    if raw:
        return data
    return [_portablize(s) for s in data]


def _write_registry(reg: list[dict[str, Any]]) -> None:
    blob = json.dumps(reg, indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(prefix=".shows.", suffix=".json.tmp", dir=str(REGISTRY.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(blob)
        os.replace(tmp, REGISTRY)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #

def list_shows() -> list[dict[str, Any]]:
    """Registry view for the UI — id/name/episodes_dir + episode count. The big
    episode_defaults block is omitted here (fetch it via get_show)."""
    reg = load_registry()
    # The default marker falls back to the first show when the legacy default is
    # absent (fresh installs have no the-macu-report).
    eff_default = (DEFAULT_SHOW if any(s.get("id") == DEFAULT_SHOW for s in reg)
                   else (reg[0]["id"] if reg else DEFAULT_SHOW))
    out = []
    for s in reg:
        ep_dir = Path(s.get("episodes_dir", ""))
        try:
            count = sum(1 for p in ep_dir.iterdir()
                        if p.is_dir() and (p / "manifest.json").exists())
        except Exception:
            count = 0
        out.append({
            "id": s.get("id"),
            "name": s.get("name") or s.get("id"),
            "episodes_dir": s.get("episodes_dir"),
            "assets_dir": s.get("assets_dir"),
            "title_prefix": s.get("title_prefix", ""),
            "episode_count": count,
            "is_default": s.get("id") == eff_default,
        })
    return out


def get_show(show_id: str) -> dict[str, Any]:
    for s in load_registry():
        if s.get("id") == show_id:
            return s
    raise KeyError(f"unknown show: {show_id}")


def show_episodes_dir(show_id: str) -> Path:
    return Path(get_show(show_id)["episodes_dir"])


def resolve_episode(slug: str) -> tuple[str, Path]:
    """Find which show owns ``slug`` and return (show_id, episode_dir).

    Fast path: the default show's flat dir (covers all existing MACU episodes).
    Otherwise scan the registry. Raises FileNotFoundError if no show has it.
    """
    # Validate the slug before it touches the filesystem — blocks path traversal
    # (`..`, `/`) on every per-slug route, which all resolve through here. An
    # invalid slug is a clean 404 (callers map FileNotFoundError → 404).
    if not _SLUG_RE.match(slug or ""):
        raise FileNotFoundError(f"invalid episode slug: {slug!r}")
    reg = load_registry()
    # Fast path: the legacy flat dir — but only when the default show is actually
    # registered AND the dir is a real episode (has a manifest). Never short-circuit
    # a bare directory or a slug another show owns to DEFAULT_SHOW.
    if any(s.get("id") == DEFAULT_SHOW for s in reg):
        fast = config.EPISODES / slug
        if (fast / "manifest.json").exists():
            return DEFAULT_SHOW, fast
    for s in reg:
        d = Path(s.get("episodes_dir", "")) / slug
        if d.is_dir():
            return s["id"], d
    raise FileNotFoundError(f"episode dir not found in any show: {slug}")


def show_of(slug: str) -> str:
    try:
        return resolve_episode(slug)[0]
    except FileNotFoundError:
        reg = load_registry()
        if any(s.get("id") == DEFAULT_SHOW for s in reg):
            return DEFAULT_SHOW
        return reg[0]["id"] if reg else DEFAULT_SHOW


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #

def scaffold_show_docs(show_id: str, name: str) -> list[str]:
    """Seed docs/shows/<show_id>/ from docs/_templates/show/*.md, substituting
    {{SHOW_NAME}} / {{SHOW_ID}} / {{DATE}}. Idempotent: never overwrites an
    existing file. Returns the filenames created. Best-effort — the caller wraps
    this so a docs hiccup can never fail show creation."""
    created: list[str] = []
    if not DOC_TEMPLATE_DIR.is_dir():
        return created
    dest_dir = SHOW_DOCS_ROOT / show_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    date = time.strftime("%Y-%m-%d")
    for tpl in sorted(DOC_TEMPLATE_DIR.glob("*.md")):
        dest = dest_dir / tpl.name
        if dest.exists():
            continue
        text = (tpl.read_text()
                .replace("{{SHOW_NAME}}", name)
                .replace("{{SHOW_ID}}", show_id)
                .replace("{{DATE}}", date))
        dest.write_text(text)
        created.append(tpl.name)
    return created


def create_show(show_id: str, name: str) -> dict[str, Any]:
    show_id = (show_id or "").strip().lower()
    if not _SLUG_RE.match(show_id):
        raise ValueError("show id must be lowercase letters/digits/dashes (2-49 chars)")
    reg = load_registry(raw=True)
    if any(s.get("id") == show_id for s in reg):
        raise ValueError(f"show already exists: {show_id}")
    base = config.SHARES / "shows" / show_id
    episodes_dir = base / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)
    # Seed a fresh show's episode_defaults from working technical blocks
    # (comfyui/voice endpoints/subtitles) but blank the creative ones so the new
    # show isn't accidentally a clone of an existing show.
    macu = _seed_base_defaults()
    defaults: dict[str, Any] = {}
    if isinstance(macu.get("comfyui"), dict):
        defaults["comfyui"] = dict(macu["comfyui"])
    if isinstance(macu.get("subtitles"), dict):
        defaults["subtitles"] = dict(macu["subtitles"])
    voice = macu.get("voice") if isinstance(macu.get("voice"), dict) else {}
    defaults["voice"] = {
        "default": voice.get("default", {"engine": "piper"}),
        "endpoints": voice.get("endpoints", {}),
        "format": voice.get("format", "wav 24000Hz mono s16"),
        "out_pattern": voice.get("out_pattern", "vo/<cue_id>.wav"),
        "speaker_map": {},
    }
    defaults["style"] = {"suffix": "", "negative": ""}
    defaults["music"] = {"enabled": True, "source_dir": str(config.SHARES / "assets" / "music"),
                         "clips": [], "beds": []}
    defaults["characters"] = {}
    defaults["broll"] = {}
    defaults["title_assets"] = {}
    entry = {
        "id": show_id,
        "name": name.strip() or show_id,
        "episodes_dir": str(episodes_dir),
        "assets_dir": str(config.SHARES / "assets"),
        "title_prefix": f"{name.strip() or show_id} — ",
        "episode_defaults": defaults,
    }
    reg.append(entry)
    _write_registry(reg)
    # Seed the per-show canon docs from templates (best-effort — never block
    # show creation on a docs error).
    try:
        scaffold_show_docs(show_id, entry["name"])
    except Exception:
        pass
    return entry


def set_default_speaker_voice(show_id: str, speaker: str, cfg: dict[str, Any] | None) -> bool:
    """Set or clear a speaker's voice in a show's episode_defaults.voice.speaker_map
    so FUTURE episodes inherit it (create_episode deep-copies episode_defaults).
    cfg=None clears the speaker. Returns True if the show was found. Existing extra
    fields (speed/seed/...) for that speaker are preserved on update."""
    reg = load_registry(raw=True)
    for s in reg:
        if s.get("id") != show_id:
            continue
        defaults = s.setdefault("episode_defaults", {})
        voice = defaults.get("voice")
        if not isinstance(voice, dict):
            voice = {}
            defaults["voice"] = voice
        smap = voice.get("speaker_map")
        if not isinstance(smap, dict):
            smap = {}
            voice["speaker_map"] = smap
        if cfg is None:
            smap.pop(speaker, None)
        else:
            entry = dict(smap.get(speaker) or {})
            entry.update(cfg)
            smap[speaker] = entry
        _write_registry(reg)
        return True
    return False


def save_show_config(show_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Update the editable fields of a show (name/title_prefix/assets_dir +
    episode_defaults). episodes_dir and id are immutable here."""
    reg = load_registry(raw=True)
    for s in reg:
        if s.get("id") == show_id:
            for k in ("name", "title_prefix", "assets_dir"):
                if k in cfg and isinstance(cfg[k], str):
                    s[k] = cfg[k]
            if isinstance(cfg.get("episode_defaults"), dict):
                s["episode_defaults"] = cfg["episode_defaults"]
            _write_registry(reg)
            return s
    raise KeyError(f"unknown show: {show_id}")


def create_episode(show_id: str, slug: str, title: str = "") -> dict[str, Any]:
    """Scaffold episodes_dir/<slug>/{manifest.json, script.md} seeded from the
    show's episode_defaults. Slugs must be globally unique across shows."""
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError("slug must be lowercase letters/digits/dashes (2-49 chars)")
    # Global uniqueness so resolve_episode / git-sync stay unambiguous.
    try:
        resolve_episode(slug)
        raise ValueError(f"episode slug already exists: {slug}")
    except FileNotFoundError:
        pass
    show = get_show(show_id)
    ep_dir = Path(show["episodes_dir"]) / slug
    if ep_dir.exists():
        raise ValueError(f"episode dir already exists: {ep_dir}")
    ep_dir.mkdir(parents=True, exist_ok=True)

    defaults = show.get("episode_defaults") or {}
    full_title = title.strip()
    prefix = show.get("title_prefix", "")
    if full_title and prefix and not full_title.startswith(prefix):
        full_title = f"{prefix}{full_title}"
    elif not full_title:
        full_title = f"{prefix}{slug}".rstrip("— ").rstrip()

    manifest: dict[str, Any] = {
        "episode": slug,
        "title": full_title,
        "version": 1,
        "show": show_id,
    }
    for k in _DEFAULTS_KEYS:
        if k in defaults:
            manifest[k] = json.loads(json.dumps(defaults[k]))  # deep copy
    manifest["cues"] = []

    (ep_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    (ep_dir / "script.md").write_text(
        f"# {full_title}\n\n_Write the script here, then click **Generate manifest** "
        f"on the Script page to turn it into cues._\n"
    )
    return {"ok": True, "show": show_id, "slug": slug, "dir": str(ep_dir), "title": full_title}


# --------------------------------------------------------------------------- #
# Archive / unarchive — physically move episodes & shows out of (and back into)
# the active tree. The move is the source of truth; a .archive.json sidecar in
# each container carries the metadata the Settings → Archive UI lists, and (for
# shows) the registry entry needed to restore the show to shows.json.
# --------------------------------------------------------------------------- #

class SlugInUse(Exception):
    """Restore target (episode slug or show id) is taken by a live item → HTTP 409."""

    def __init__(self, name: str, owner: str):
        self.name = name
        self.owner = owner
        super().__init__(f"already in use by '{owner}': {name}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def show_archive_dir(show_id: str) -> Path:
    """Where archived episode-families for a show live: ``SHARES/shows/<id>/archived/``.

    A sibling of the show's ``episodes_dir`` for registry shows; namespaced under
    ``shows/<id>/`` for the legacy flat default show (whose episodes_dir is the bare
    ``SHARES/episodes``). Crucially NEVER inside ``episodes_dir`` — otherwise
    ``list_episodes`` would re-discover archived items.
    """
    ep_dir = show_episodes_dir(show_id)  # live (rebased) path
    if ep_dir.name == "episodes" and ep_dir.parent.name == show_id:
        return ep_dir.parent / "archived"
    return config.SHARES / "shows" / show_id / "archived"


def _read_sidecar(container: Path) -> dict[str, Any]:
    f = container / ARCHIVE_SIDECAR
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def _episode_title(ep_dir: Path) -> str:
    try:
        data = json.loads((ep_dir / "manifest.json").read_text())
        return str(data.get("title") or ep_dir.name)
    except Exception:
        return ep_dir.name


def _relativize_family_symlinks(item_dir: Path, old_parent: Path, new_parent: Path) -> None:
    """After moving a localized variant, repoint any top-level symlink that pointed at
    the (now-moved) parent episode dir via an ABSOLUTE path so the family stays
    self-contained. Relative links between siblings survive the move untouched."""
    try:
        children = list(item_dir.iterdir())
    except OSError:
        return
    for child in children:
        if not child.is_symlink():
            continue
        target = os.readlink(child)
        if not os.path.isabs(target):
            continue
        try:
            rel_inside = Path(target).relative_to(old_parent)
        except ValueError:
            continue  # absolute, but not into the old parent — leave it
        new_target = os.path.relpath(new_parent / rel_inside, item_dir)
        child.unlink()
        os.symlink(new_target, child)


def archive_episode(slug: str) -> dict[str, Any]:
    """Physically move an episode — and its localization family — out of the show's
    episodes_dir into ``SHARES/shows/<show>/archived/<slug>/`` (a container holding
    the episode dir, any variant dirs, and recreated alias symlinks, plus the
    sidecar). Frees the slug for reuse.

    Raises FileNotFoundError (unknown slug → 404), ValueError (variant/alias slug → 400).
    """
    from . import episodes as ep_mod  # lazy: episodes imports shows

    if ep_mod._VARIANT_RE.match(slug):
        raise ValueError(
            f"{slug} is a localized variant — archive its parent episode instead")
    show_id, ep_dir = resolve_episode(slug)  # FileNotFoundError → 404
    if ep_dir.is_symlink():
        raise ValueError(f"{slug} is an alias — archive the canonical episode instead")
    ep_root = ep_dir.parent
    variants, aliases = ep_mod.episode_variants(ep_root, slug)

    arch_root = show_archive_dir(show_id)
    arch_root.mkdir(parents=True, exist_ok=True)
    container = arch_root / slug
    if container.exists():
        container = container.with_name(f"{slug}.archived-{_ts()}")
    container.mkdir(parents=True)

    moved = [slug]
    shutil.move(str(ep_dir), str(container / slug))  # same-fs rename, keeps symlinks
    variant_names: list[str] = []
    for v in variants:
        shutil.move(str(v), str(container / v.name))
        variant_names.append(v.name)
        moved.append(v.name)
    alias_names: list[str] = []
    for a in aliases:
        target = os.readlink(a)
        a.unlink()
        os.symlink(Path(target).name, container / a.name)  # relative, inside container
        alias_names.append(a.name)
    for vn in variant_names:
        _relativize_family_symlinks(container / vn, ep_dir, container / slug)

    sidecar = {
        "kind": "episode",
        "slug": slug,
        "show": show_id,
        "title": _episode_title(container / slug),
        "original_path": str(ep_dir),
        "archived_at": time.time(),
        "archived_at_iso": _now_iso(),
        "variants": variant_names,
        "aliases": alias_names,
    }
    (container / ARCHIVE_SIDECAR).write_text(json.dumps(sidecar, indent=2, ensure_ascii=False))
    return {"ok": True, "show": show_id, "slug": slug, "archived": moved, "path": str(container)}


def unarchive_episode(show_id: str, name: str, new_slug: str | None = None) -> dict[str, Any]:
    """Restore an archived episode-family (``name`` = its container dir name) back into
    its show's episodes_dir. ``new_slug`` restores under a different slug when the
    original is taken.

    Raises FileNotFoundError (404), ValueError (bad slug → 400), SlugInUse (409).
    """
    safe_segment(name, "archive name")
    container = show_archive_dir(show_id) / name
    if not container.is_dir():
        raise FileNotFoundError(f"archived episode not found: {name}")
    sidecar = _read_sidecar(container)
    orig_slug = sidecar.get("slug") or name
    dest_slug = (new_slug or orig_slug).strip().lower()
    if not _SLUG_RE.match(dest_slug):
        raise ValueError("slug must be lowercase letters/digits/dashes (2-49 chars)")

    try:
        owner, _ = resolve_episode(dest_slug)
        raise SlugInUse(dest_slug, owner)
    except FileNotFoundError:
        pass

    target_show = sidecar.get("show") or show_id
    try:
        ep_root = show_episodes_dir(target_show)
    except KeyError:
        target_show = show_id
        ep_root = show_episodes_dir(show_id)
    ep_root.mkdir(parents=True, exist_ok=True)

    parent_src = container / orig_slug
    if not parent_src.is_dir():
        # Sidecar lost/corrupt — fall back to the lone real (non-symlink, non-variant) dir.
        from . import episodes as ep_mod
        cands = [p for p in container.iterdir()
                 if p.is_dir() and not p.is_symlink() and not ep_mod._VARIANT_RE.match(p.name)]
        if len(cands) != 1:
            raise FileNotFoundError(f"cannot locate the episode dir inside {name}")
        parent_src = cands[0]
        orig_slug = parent_src.name

    shutil.move(str(parent_src), str(ep_root / dest_slug))
    restored = [dest_slug]
    # Move variants + aliases back as siblings; repoint them if the slug changed.
    for entry in sorted(container.iterdir(), key=lambda p: p.name):
        if entry.name == ARCHIVE_SIDECAR:
            continue
        dst = ep_root / entry.name
        if entry.is_symlink():  # alias: recreate pointing at the restored slug
            entry.unlink()
            if not dst.exists():
                os.symlink(dest_slug, dst)
            restored.append(entry.name)
            continue
        shutil.move(str(entry), str(dst))
        restored.append(entry.name)
        if dest_slug != orig_slug:
            _repoint_variant(dst, orig_slug, dest_slug)
    shutil.rmtree(container, ignore_errors=True)
    return {"ok": True, "show": target_show, "slug": dest_slug, "restored": restored}


def _repoint_variant(variant_dir: Path, old_base: str, new_base: str) -> None:
    """Rewrite a restored variant's top-level symlinks that referenced the parent's
    OLD slug dir (``../<old_base>/...``) to the new slug — for the rare restore-under-
    a-new-slug case."""
    try:
        children = list(variant_dir.iterdir())
    except OSError:
        return
    for child in children:
        if not child.is_symlink():
            continue
        target = os.readlink(child)
        parts = target.split("/")
        if old_base in parts:
            new_target = "/".join(new_base if p == old_base else p for p in parts)
            child.unlink()
            os.symlink(new_target, child)


def archive_show(show_id: str) -> dict[str, Any]:
    """Physically move a whole show's tree (``SHARES/shows/<id>/``) into
    ``SHARES/_archived-shows/<id>/`` and drop it from shows.json. The raw registry
    entry is preserved in the sidecar so unarchive restores episode_defaults verbatim.

    Raises KeyError (unknown → 404), ValueError (guarded show → 400).
    """
    reg = load_registry(raw=True)
    entry = next((s for s in reg if s.get("id") == show_id), None)
    if entry is None:
        raise KeyError(f"unknown show: {show_id}")
    eff_default = (DEFAULT_SHOW if any(s.get("id") == DEFAULT_SHOW for s in reg)
                   else (reg[0]["id"] if reg else DEFAULT_SHOW))
    if show_id == DEFAULT_SHOW or show_id == eff_default:
        raise ValueError("cannot archive the default show")
    if len(reg) <= 1:
        raise ValueError("cannot archive the only remaining show")

    live_ep_dir = show_episodes_dir(show_id)
    if live_ep_dir.name == "episodes" and live_ep_dir.parent.name == show_id:
        base = live_ep_dir.parent
    else:
        base = config.SHARES / "shows" / show_id
    if not base.is_dir():
        raise FileNotFoundError(f"show directory not found: {base}")

    try:
        count = sum(1 for p in live_ep_dir.iterdir()
                    if p.is_dir() and (p / "manifest.json").exists())
    except OSError:
        count = 0

    ARCHIVED_SHOWS_ROOT.mkdir(parents=True, exist_ok=True)
    dest = ARCHIVED_SHOWS_ROOT / show_id
    if dest.exists():
        dest = dest.with_name(f"{show_id}.archived-{_ts()}")
    shutil.move(str(base), str(dest))

    sidecar = {
        "kind": "show",
        "show": show_id,
        "name": entry.get("name") or show_id,
        "original_path": str(base),
        "archived_at": time.time(),
        "archived_at_iso": _now_iso(),
        "episode_count": count,
        "registry_entry": entry,  # raw/canonical — restores episode_defaults byte-for-byte
    }
    (dest / ARCHIVE_SIDECAR).write_text(json.dumps(sidecar, indent=2, ensure_ascii=False))
    _write_registry([s for s in reg if s.get("id") != show_id])
    return {"ok": True, "show": show_id, "path": str(dest), "episode_count": count}


def unarchive_show(name: str) -> dict[str, Any]:
    """Restore an archived show (``name`` = its container dir name in _archived-shows)
    back to ``SHARES/shows/<id>/`` and re-append its entry to shows.json.

    Raises FileNotFoundError (404), ValueError (400), SlugInUse (409).
    """
    safe_segment(name, "archive name")
    container = ARCHIVED_SHOWS_ROOT / name
    if not container.is_dir():
        raise FileNotFoundError(f"archived show not found: {name}")
    sidecar = _read_sidecar(container)
    entry = sidecar.get("registry_entry") if isinstance(sidecar.get("registry_entry"), dict) else None
    show_id = (entry or {}).get("id") or sidecar.get("show") or name

    reg = load_registry(raw=True)
    if any(s.get("id") == show_id for s in reg):
        raise SlugInUse(show_id, show_id)

    dest = config.SHARES / "shows" / show_id
    if dest.exists():
        raise ValueError(f"destination already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(container), str(dest))
    sc = dest / ARCHIVE_SIDECAR
    if sc.exists():
        sc.unlink()

    if not entry:  # sidecar lost the registry entry — reconstruct a minimal one
        entry = {
            "id": show_id,
            "name": sidecar.get("name") or show_id,
            "episodes_dir": str(dest / "episodes"),
            "assets_dir": str(config.SHARES / "assets"),
            "title_prefix": f"{sidecar.get('name') or show_id} — ",
            "episode_defaults": {},
        }
    reg.append(entry)
    _write_registry(reg)
    return {"ok": True, "show": show_id, "path": str(dest)}


def list_archived() -> dict[str, Any]:
    """Everything archived: episode-families grouped by their (still-registered) show,
    plus whole archived shows. Drives the Settings → Archive panel."""
    episodes: dict[str, list[dict[str, Any]]] = {}
    for show in load_registry():
        sid = show.get("id")
        if not sid:
            continue
        arch = show_archive_dir(sid)
        if not arch.is_dir():
            continue
        items: list[dict[str, Any]] = []
        for c in sorted(arch.iterdir(), key=lambda p: p.name):
            if not c.is_dir():
                continue
            sc = _read_sidecar(c)
            if not sc:
                continue
            items.append({
                "name": c.name,
                "slug": sc.get("slug") or c.name,
                "title": sc.get("title") or sc.get("slug") or c.name,
                "show": sid,
                "archived_at_iso": sc.get("archived_at_iso"),
                "variants": sc.get("variants") or [],
            })
        if items:
            episodes[sid] = items

    shows_out: list[dict[str, Any]] = []
    if ARCHIVED_SHOWS_ROOT.is_dir():
        for c in sorted(ARCHIVED_SHOWS_ROOT.iterdir(), key=lambda p: p.name):
            if not c.is_dir():
                continue
            sc = _read_sidecar(c)
            if not sc:
                continue
            shows_out.append({
                "name": c.name,
                "show": sc.get("show") or c.name,
                "display_name": sc.get("name") or sc.get("show") or c.name,
                "archived_at_iso": sc.get("archived_at_iso"),
                "episode_count": sc.get("episode_count", 0),
            })
    return {"episodes": episodes, "shows": shows_out}
