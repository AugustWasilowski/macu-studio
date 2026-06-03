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


SLUG_PATTERN = "ep"  # heuristic; we also include anything with a manifest


@dataclass
class EpisodeSummary:
    slug: str
    title: str
    modified_iso: str
    done_stages: int  # 0..5 (UI tab stages, not pipeline stages)


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def list_episodes() -> list[EpisodeSummary]:
    out: list[EpisodeSummary] = []
    if not EPISODES.exists():
        return out
    for entry in sorted(EPISODES.iterdir(), key=lambda p: p.name):
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
        out.append(
            EpisodeSummary(
                slug=entry.name,
                title=str(title),
                modified_iso=_utc_iso(manifest.stat().st_mtime),
                done_stages=_done_stages(entry, data),
            )
        )
    return out


def episode_dir(slug: str) -> Path:
    p = EPISODES / slug
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
