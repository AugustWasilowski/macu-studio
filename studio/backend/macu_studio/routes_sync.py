"""Studio↔Studio sync routes (see studiosync.py)."""
from __future__ import annotations

import anyio
from fastapi import APIRouter, Body, HTTPException

from . import studiosync

router = APIRouter()


@router.get("/api/shows/{show}/sync/status")
def get_sync_status(show: str):
    return studiosync.status(show)


@router.get("/api/shows/{show}/sync/plan")
async def get_sync_plan(show: str):
    try:
        # git fetch + hashing can take seconds — keep the event loop free.
        return await anyio.to_thread.run_sync(studiosync.plan, show)
    except KeyError:
        raise HTTPException(404, f"unknown show {show}")
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@router.post("/api/shows/{show}/sync/apply")
async def post_sync_apply(show: str, body: dict = Body(default={})):
    try:
        msg = (body.get("message") or "").strip() or None
        return await anyio.to_thread.run_sync(studiosync.apply, show, msg)
    except KeyError:
        raise HTTPException(404, f"unknown show {show}")
    except RuntimeError as e:
        raise HTTPException(409, str(e))
