"""Voice-clone routes (the Audio page "Create Voice" button).

GET    /api/voices                 → {running, profiles:[{id,name}]} (never starts the container)
POST   /api/voices                 → multipart {name, language?, test_text?, file} → clone via OmniVoice
DELETE /api/voices/{pid}           → delete a cloned profile
GET    /api/voices/sample/{name}   → stream a generated test clip (wav)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from . import voices

router = APIRouter()


@router.get("/api/voices")
def get_voices():
    return voices.list_profiles_safe()


@router.post("/api/voices")
async def post_voice(
    name: str = Form(...),
    language: str = Form("English"),
    test_text: str = Form(""),
    file: UploadFile = File(...),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty upload")
    suffix = Path(file.filename or "").suffix or ".bin"
    fd, tmp = tempfile.mkstemp(prefix="voiceup.", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        # Heavy: container start (up to ~180s) + ffmpeg + OmniVoice — off the loop.
        result = await run_in_threadpool(
            voices.create_from_upload, name, language, test_text, Path(tmp)
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return {"ok": True, **result}


@router.delete("/api/voices/{pid}")
async def delete_voice(pid: str):
    try:
        return await run_in_threadpool(voices.delete_profile, pid)
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@router.get("/api/voices/sample/{name}")
def get_voice_sample(name: str):
    try:
        p = voices.test_clip_path(name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not p.exists():
        raise HTTPException(404, "sample not found")
    return FileResponse(str(p), media_type="audio/wav")
