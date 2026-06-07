"""Manual git-sync route (Phase H).

POST an episode's text files (script.md / manifest.json / youtube.txt) into the
tracked ``episode_meta/<slug>/`` path and commit + push on demand.
"""
from fastapi import APIRouter, Body

from . import gitsync

router = APIRouter()


@router.post("/api/episodes/{slug}/git-sync")
def git_sync(slug: str, body: dict = Body(default={})):
    # Optional commit message — lets a per-version revision sync label the commit
    # (e.g. "awb-001 v2 (writers' room)") so the git log / Studio script-diff
    # picker reads cleanly. The frontend button sends none → default message.
    message = (body or {}).get("message") if isinstance(body, dict) else None
    return gitsync.sync(slug, message=message)
