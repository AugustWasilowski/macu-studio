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


@router.get("/api/integrations/claude")
def get_claude_integration():
    """Claude Code CLI status for the Engines tab's connector card."""
    import subprocess
    path = engines.claude_path()
    version = None
    if path:
        try:
            r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
            version = (r.stdout or r.stderr).strip().splitlines()[0][:60] or None
        except Exception:
            pass
    return {"installed": bool(path), "path": path, "version": version}
