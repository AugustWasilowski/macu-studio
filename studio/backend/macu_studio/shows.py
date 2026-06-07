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
from pathlib import Path
from typing import Any

from . import config

REGISTRY = config.STUDIO_ROOT / "shows.json"

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
            "model": "hal",
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
