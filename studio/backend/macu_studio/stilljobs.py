"""Unified in-memory registry for still-generation jobs.

One registry for every still engine (local ComfyUI Z-Image, Higgsfield image
models, remote render service) and every caller (episode character stills,
library takes). Keys:
  episode stills   "<slug>:<who>"          (pre-existing shape — API-compatible)
  library takes    "lib:<show>:<key>"

A job is one user action; a multi-take request loops inside the single job,
appending each finished artifact immediately so partial success survives an
error or a backend restart (the registry itself is in-memory and lost on
restart — finished files are not).
"""
from __future__ import annotations

import asyncio
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Awaitable, Callable

ACTIVE = ("queued", "generating", "downloading")

# key -> {state, engine, error, started, progress: {done, total}, job_id?}
JOBS: dict[str, dict] = {}


def get(key: str) -> dict | None:
    return JOBS.get(key)


def is_active(key: str) -> bool:
    return JOBS.get(key, {}).get("state") in ACTIVE


def start(key: str, engine: str, total: int,
          runner: Callable[[dict], Awaitable[None]]) -> dict:
    """Register + launch a job task. `runner(job)` owns the work and must set
    job["state"] to done/error itself (helpers below). Raises RuntimeError if
    the key already has an active job."""
    if is_active(key):
        raise RuntimeError(f"a generation for {key} is already running")
    job: dict = {"state": "queued", "engine": engine, "error": None,
                 "started": time.time(), "progress": {"done": 0, "total": total}}
    JOBS[key] = job

    async def wrap() -> None:
        try:
            await runner(job)
            if job["state"] in ACTIVE:
                job["state"] = "done"
        except Exception as e:
            job["state"] = "error"
            job["error"] = str(e) or e.__class__.__name__

    asyncio.get_running_loop().create_task(wrap())
    return job


def png_normalize(src: Path, dest: Path) -> None:
    """Whatever format an engine returned → PNG at dest (ffmpeg, atomic)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", dir=dest.parent, delete=False) as t:
        tmp = Path(t.name)
    try:
        subprocess.run(["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", str(tmp)],
                       check=True, capture_output=True, timeout=60)
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
