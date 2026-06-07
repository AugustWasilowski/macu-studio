"""Voice-clone routes (the Audio page "Create Voice" button).

GET    /api/voices                 → {running, profiles:[{id,name}]} (never starts the container)
POST   /api/voices                 → multipart {name, language?, test_text?, file} → clone via OmniVoice
DELETE /api/voices/{pid}           → delete a cloned profile
GET    /api/voices/sample/{name}   → stream a generated test clip (wav)
GET    /api/voices/export[?name=]  → zip of all reference clips (or one), for moving voices between machines
POST   /api/voices/clone-ref       → {name, show?} re-clone an imported ref into OmniVoice + rebind a show (GPU)
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from . import voices
from . import shows as shows_mod
from . import episodes as ep_mod
from . import manifest as manifest_mod

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


@router.get("/api/voices/export")
def export_voices(name: str | None = None):
    """Zip of voice reference clips — all of them, or one (?name=). Import via the
    project menu re-clones them into the receiving machine's OmniVoice."""
    refs = voices.refs_for_names([name]) if name else voices.all_refs()
    if not refs:
        raise HTTPException(404, f"no reference clip for voice {name!r}" if name else "no voices to export")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("export.json", json.dumps({
            "kind": "voices",
            "voices": [{"name": n, "language": "English"} for n in refs],
            "version": 1,
        }, indent=2))
        for n, p in refs.items():
            zf.write(p, f"voices/{p.name}")
    buf.seek(0)
    fn = f"voice-{voices._slug(name)}.zip" if name else "voices-all.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


def _rebind_voice(show: str, voice_name: str, new_id: str) -> int:
    """Point every speaker_map entry whose voice_name matches at new_id — across the
    show's episode manifests AND its episode_defaults. Returns the entries changed."""
    count = 0
    try:
        for ep in ep_mod.list_episodes(show):
            try:
                m = manifest_mod.load(ep.slug)
            except Exception:
                continue
            sm = (m.get("voice") or {}).get("speaker_map") or {}
            changed = False
            for v in sm.values():
                if (isinstance(v, dict) and v.get("engine") == "omnivoice"
                        and v.get("voice_name") == voice_name and v.get("profile_id") != new_id):
                    v["profile_id"] = new_id
                    changed = True
                    count += 1
            if changed:
                manifest_mod.save(ep.slug, m)
    except Exception:
        pass
    try:
        reg = shows_mod.load_registry(raw=True)
        for s in reg:
            if s.get("id") != show:
                continue
            sm = ((s.get("episode_defaults") or {}).get("voice") or {}).get("speaker_map") or {}
            ch = False
            for v in sm.values():
                if isinstance(v, dict) and v.get("voice_name") == voice_name and v.get("profile_id") != new_id:
                    v["profile_id"] = new_id
                    ch = True
            if ch:
                shows_mod._write_registry(reg)
            break
    except Exception:
        pass
    return count


@router.post("/api/voices/clone-ref")
async def post_clone_ref(body: dict = Body(...)):
    """Re-clone one imported reference clip into the local OmniVoice (starts the
    container — GPU) and, if a show is given, rebind that show's speaker_map entries
    for this voice to the fresh profile_id. Called once per voice so the UI can show
    a progress bar."""
    name = (body.get("name") or "").strip()
    show = (body.get("show") or "").strip() or None
    if not name:
        raise HTTPException(400, "name required")
    try:
        result = await run_in_threadpool(voices.clone_ref, name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    rebound = 0
    if show and result.get("id"):
        rebound = await run_in_threadpool(_rebind_voice, show, name, result["id"])
    return {"ok": True, "rebound": rebound, **result}
