"""Routes for the 'send to writers' room' feature (fire-and-forget critique loop)."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from . import writers_room

router = APIRouter()


@router.post("/api/episodes/{slug}/writers-room")
async def post_writers_room(slug: str):
    try:
        return await writers_room.kick(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@router.get("/api/episodes/{slug}/writers-room")
def get_writers_room(slug: str):
    try:
        return writers_room.read_notes(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
