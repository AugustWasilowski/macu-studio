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
from pathlib import Path
from typing import Any

from . import config

REGISTRY = config.STUDIO_ROOT / "shows.json"
DEFAULT_SHOW = "the-macu-report"
DEFAULT_SHOW_NAME = "The MACU Report"

# Show-level manifest blocks copied into a new episode's manifest. Episode-only
# blocks (cues/sfx/overlays/episode/title/season/episode_num) are NOT seeded.
_DEFAULTS_KEYS = (
    "voice", "comfyui", "style", "subtitles", "music",
    "characters", "broll", "title_assets", "render_rule",
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")


# --------------------------------------------------------------------------- #
# Registry load / save
# --------------------------------------------------------------------------- #

def _seed_macu_defaults() -> dict[str, Any]:
    """Build the-macu-report's episode_defaults from a representative manifest
    (the highest-numbered ep-### with a manifest). Best-effort: returns {} if
    none is found, so a fresh checkout still works."""
    if not config.EPISODES.exists():
        return {}
    candidates = sorted(
        (p for p in config.EPISODES.iterdir()
         if p.is_dir() and (p / "manifest.json").exists()),
        key=lambda p: p.name,
    )
    if not candidates:
        return {}
    try:
        data = json.loads((candidates[-1] / "manifest.json").read_text())
    except Exception:
        return {}
    out: dict[str, Any] = {}
    for k in _DEFAULTS_KEYS:
        if k in data:
            out[k] = data[k]
    # Episode-specific cast lists shouldn't ride along as a "default" — keep the
    # voice endpoints/default but blank the per-episode speaker_map.
    if isinstance(out.get("voice"), dict):
        out["voice"] = dict(out["voice"])
        if "speaker_map" in out["voice"]:
            out["voice"]["speaker_map"] = {}
    return out


def _default_registry() -> list[dict[str, Any]]:
    return [{
        "id": DEFAULT_SHOW,
        "name": DEFAULT_SHOW_NAME,
        "episodes_dir": str(config.EPISODES),
        "assets_dir": str(config.SHARES / "assets"),
        "title_prefix": f"{DEFAULT_SHOW_NAME} — ",
        "episode_defaults": _seed_macu_defaults(),
    }]


def load_registry() -> list[dict[str, Any]]:
    """Read shows.json, auto-seeding it with the default show on first run."""
    if not REGISTRY.exists():
        reg = _default_registry()
        _write_registry(reg)
        return reg
    try:
        data = json.loads(REGISTRY.read_text())
    except Exception:
        data = []
    if not isinstance(data, list):
        data = []
    # Guarantee the default show is always present (even if the file got hand-edited).
    if not any(s.get("id") == DEFAULT_SHOW for s in data):
        data = _default_registry() + data
        _write_registry(data)
    return data


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
    out = []
    for s in load_registry():
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
            "is_default": s.get("id") == DEFAULT_SHOW,
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
    fast = config.EPISODES / slug
    if (fast / "manifest.json").exists() or fast.is_dir():
        return DEFAULT_SHOW, fast
    for s in load_registry():
        d = Path(s.get("episodes_dir", "")) / slug
        if d.is_dir():
            return s["id"], d
    raise FileNotFoundError(f"episode dir not found in any show: {slug}")


def show_of(slug: str) -> str:
    try:
        return resolve_episode(slug)[0]
    except FileNotFoundError:
        return DEFAULT_SHOW


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #

def create_show(show_id: str, name: str) -> dict[str, Any]:
    show_id = (show_id or "").strip().lower()
    if not _SLUG_RE.match(show_id):
        raise ValueError("show id must be lowercase letters/digits/dashes (2-49 chars)")
    reg = load_registry()
    if any(s.get("id") == show_id for s in reg):
        raise ValueError(f"show already exists: {show_id}")
    base = config.SHARES / "shows" / show_id
    episodes_dir = base / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)
    # Seed a fresh show's episode_defaults from the default show's technical
    # blocks (comfyui/voice endpoints/subtitles) but blank the creative ones so
    # the new show isn't accidentally a MACU clone.
    macu = get_show(DEFAULT_SHOW).get("episode_defaults", {})
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
    return entry


def save_show_config(show_id: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Update the editable fields of a show (name/title_prefix/assets_dir +
    episode_defaults). episodes_dir and id are immutable here."""
    reg = load_registry()
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
