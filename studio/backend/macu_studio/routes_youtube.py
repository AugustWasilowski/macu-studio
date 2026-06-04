"""YouTube landing-page routes (Feature F2).

GET /api/youtube/uploads  → channel uploads (cached, [] when unconfigured)
GET /api/youtube/matches  → {slug: upload | None} fuzzy-matched to episodes
"""
from __future__ import annotations

from fastapi import APIRouter

from . import youtube
from .episodes import list_episodes

router = APIRouter()


@router.get("/api/youtube/uploads")
async def get_uploads():
    return {"uploads": await youtube.uploads()}


@router.get("/api/youtube/matches")
async def get_matches():
    ups = await youtube.uploads()
    eps = list_episodes()
    matches = youtube.match_episodes(ups, eps)
    # surface slug+title alongside the match so the UI doesn't need a 2nd fetch
    episodes = [{"slug": e.slug, "title": e.title} for e in eps]
    return {"matches": matches, "episodes": episodes}
