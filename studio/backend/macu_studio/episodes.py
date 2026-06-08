"""Episode discovery + per-episode pipeline status snapshot.

An episode is a directory under MACU_EPISODES containing a manifest.json.
"""
from __future__ import annotations
import json, os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import EPISODES
from . import shows as shows_mod


SLUG_PATTERN = "ep"  # heuristic; we also include anything with a manifest


@dataclass
class EpisodeSummary:
    slug: str
    title: str
    modified_iso: str
    done_stages: int  # 0..5 (UI tab stages, not pipeline stages)
    season: int | None = None
    episode_num: int | None = None
    se_label: str | None = None  # "S01-E1" or None (pre-series / non-ep slugs)
    synced: bool = True  # working text files match the tracked episode_meta copy
    show: str = shows_mod.DEFAULT_SHOW  # owning show id
    published: bool = False  # manifest `published` flag → public on macu-web (else hidden draft)
    youtube_id: str | None = None  # video id parsed from youtube.txt (drives the macu-web embed)


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def season_episode(slug: str) -> tuple[int, int] | None:
    """Derive (season, episode) from an ep-### slug. Releases are 5/week (M–F) = a
    Season, anchored at ep-006 = S01-E1. Returns None for non-ep slugs or N<6
    (ep-005 and earlier are pre-series)."""
    if not slug.startswith("ep-"):
        return None
    try:
        n = int(slug.split("-", 1)[1])
    except (ValueError, IndexError):
        return None
    if n < 6:
        return None
    return (n - 6) // 5 + 1, (n - 6) % 5 + 1


def se_label(season: int, episode: int) -> str:
    return f"S{season:02d}-E{episode}"


import re as _re

_VID_LINE = _re.compile(r"^\s*video_id\s*:\s*([A-Za-z0-9_-]{11})\s*$", _re.M)
_VID_URL = _re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def youtube_id_of(ep_dir: Path) -> str | None:
    """The YouTube video id from an episode's youtube.txt (a `video_id:` line or a YT URL)."""
    f = ep_dir / "youtube.txt"
    if not f.exists():
        return None
    t = f.read_text(errors="ignore")
    m = _VID_LINE.search(t) or _VID_URL.search(t)
    return m.group(1) if m else None


def extract_video_id(val: str) -> str | None:
    """Pull an 11-char id out of a pasted YouTube URL or bare id; None if not parseable."""
    val = (val or "").strip()
    if not val:
        return None
    m = _VID_URL.search(val)
    if m:
        return m.group(1)
    return val if _re.fullmatch(r"[A-Za-z0-9_-]{11}", val) else None


def list_episodes(show: str | None = None) -> list[EpisodeSummary]:
    """Episodes for one show (default: the-macu-report → the existing flat dir)."""
    show = show or shows_mod.DEFAULT_SHOW
    out: list[EpisodeSummary] = []
    try:
        ep_root = shows_mod.show_episodes_dir(show)
    except KeyError:
        return out
    if not ep_root.exists():
        return out
    # One git ls-tree for the whole list; each episode's sync dot is measured
    # against what's pushed to the remote (lazy import avoids a module cycle).
    from . import gitsync
    pushed = gitsync.pushed_tree()
    for entry in sorted(ep_root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        manifest = entry / "manifest.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text())
        except Exception:
            continue
        title = data.get("title") or entry.name
        # Prefer the manifest's stored season/episode_num; fall back to the slug formula.
        season = data.get("season")
        episode_num = data.get("episode_num")
        if season is None or episode_num is None:
            derived = season_episode(entry.name)
            if derived:
                season, episode_num = derived
        label = se_label(season, episode_num) if season and episode_num else None
        out.append(
            EpisodeSummary(
                slug=entry.name,
                title=str(title),
                modified_iso=_utc_iso(manifest.stat().st_mtime),
                done_stages=_done_stages(entry, data),
                season=season,
                episode_num=episode_num,
                se_label=label,
                synced=gitsync.sync_status(entry.name, pushed),
                show=show,
                published=data.get("published") is True,
                youtube_id=(data.get("youtube") or {}).get("video_id") or youtube_id_of(entry),
            )
        )
    return out


def episode_dir(slug: str) -> Path:
    """Resolve an episode dir by slug across all registered shows.

    The default show's flat dir is the fast path (covers every existing MACU
    episode); other shows are found by scanning the registry. This is what keeps
    all the per-slug routes show-agnostic."""
    _show, p = shows_mod.resolve_episode(slug)
    if not p.is_dir():
        raise FileNotFoundError(f"episode dir not found: {p}")
    return p


def manifest_path(slug: str) -> Path:
    return episode_dir(slug) / "manifest.json"


def _done_stages(ep: Path, manifest: dict) -> int:
    """How many of the 5 UI 'tab' stages are 'done' for badging.

    Heuristic — script done if script.md exists; audio done if all VO wavs exist;
    graphics done if all per-episode title mp4s exist; video done if all
    masters exist; assembly done if final/<slug>.mp4 exists.
    """
    score = 0
    if (ep / "script.md").exists():
        score += 1
    cues = manifest.get("cues") or []
    vo_needed = {c["id"] for c in cues if c.get("vo")}
    vo_present = {p.stem for p in (ep / "vo").glob("*.wav")} if (ep / "vo").exists() else set()
    if vo_needed and vo_needed.issubset(vo_present):
        score += 1
    titles_needed = set()
    for k, v in (manifest.get("title_assets") or {}).items():
        if isinstance(v, str) and v.startswith("episodes/"):
            titles_needed.add(k)
    titles_present = {p.stem for p in (ep / "titles").glob("*.mp4")} if (ep / "titles").exists() else set()
    if titles_needed and titles_needed.issubset(titles_present):
        score += 1
    elif not titles_needed:
        # nothing custom needed — auto-resolved title assets count as "done"
        # only if at least the master video can be built
        pass
    chars = set((manifest.get("characters") or {}).keys())
    broll = set((manifest.get("broll") or {}).keys())
    keys_needed = chars | broll
    clips_present = {p.name.replace("_master.zs.webp", "") for p in (ep / "clips").glob("*_master.zs.webp")} if (ep / "clips").exists() else set()
    if keys_needed and keys_needed.issubset(clips_present):
        score += 1
    final = ep / "final" / f"{ep.name}.mp4"
    if final.exists():
        score += 1
    return score
