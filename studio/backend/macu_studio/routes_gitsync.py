"""Manual git-sync route (Phase H).

POST an episode's text files (script.md / manifest.json / youtube.txt) into the
tracked ``episode_meta/<slug>/`` path and commit + push on demand.
"""
from fastapi import APIRouter

from . import gitsync

router = APIRouter()


@router.post("/api/episodes/{slug}/git-sync")
def git_sync(slug: str):
    return gitsync.sync(slug)
