"""Engine routing routes — the Settings → Engines tab's backend."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from . import engines

router = APIRouter()


@router.get("/api/engines")
def get_engines():
    return engines.get_config()


@router.put("/api/engines")
def put_engines(body: dict = Body(...)):
    try:
        return engines.save_config(body)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/engines/probe")
async def get_probe():
    return await engines.probe()
