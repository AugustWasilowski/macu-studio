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


@router.post("/api/voices/start")
async def post_voices_start():
    """Start the OmniVoice container (consumer-lifecycle, GPU) and wait until it
    answers. Returns the live roster. Use before casting/validating when the engine
    is idle — the TTS probe in /api/engines/probe shows whether it's up."""
    try:
        await run_in_threadpool(voices.ensure_up)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return voices.list_profiles_safe()


@router.post("/api/voices/import")
async def post_voices_import(body: dict = Body(default={})):
    """Import a voices export into the LOCAL OmniVoice. `zip_path` (server-local)
    is unpacked into refs/ first; omit it to (re)clone reference clips already on
    disk. `names` limits to a subset; `show` rebinds that show's speaker_map entries
    (by voice_name) to the freshly minted profile_ids. Clones run one at a time
    (GPU). Returns {imported:{name:id}, rebound:{name:n}, failed:[{name,error}]}."""
    zip_path = (body.get("zip_path") or "").strip()
    only = body.get("names") or None
    show = (body.get("show") or "").strip() or None

    def _do_import() -> dict:
        names: list[str] = []
        # 1) unpack the zip's reference clips into refs/ (if a zip was given).
        if zip_path:
            p = Path(zip_path)
            if not p.is_file():
                raise FileNotFoundError(f"no zip at {zip_path}")
            with zipfile.ZipFile(p) as zf:
                meta_names = []
                if "export.json" in zf.namelist():
                    try:
                        meta = json.loads(zf.read("export.json"))
                        meta_names = [v.get("name") for v in (meta.get("voices") or [])
                                      if v.get("name")]
                    except Exception:
                        meta_names = []
                # map slug -> raw bytes for every bundled clip
                slug_bytes = {Path(n).stem: zf.read(n) for n in zf.namelist()
                              if n.startswith("voices/") and n.lower().endswith(".wav")}
                # Prefer export.json's real (cased) names; fall back to slugs.
                cand = meta_names or list(slug_bytes)
                for nm in cand:
                    data = slug_bytes.get(voices._slug(nm))
                    if data is None:
                        continue
                    voices.import_ref(nm, data)
                    names.append(nm)
        else:
            names = list(voices.all_refs().keys())
        if only:
            wanted = set(only)
            names = [n for n in names if n in wanted]
        if not names:
            return {"imported": {}, "rebound": {}, "failed": [],
                    "note": "no reference clips found to import"}
        # 2) clone each into OmniVoice (serial — the engine is single-model).
        imported: dict[str, str] = {}
        rebound: dict[str, int] = {}
        failed: list[dict] = []
        for nm in names:
            try:
                res = voices.clone_ref(nm)
                pid = res.get("id")
                if not pid:
                    failed.append({"name": nm, "error": "no profile_id returned"})
                    continue
                imported[nm] = pid
                if show:
                    rebound[nm] = _rebind_voice(show, nm, pid)
            except Exception as e:  # noqa: BLE001
                failed.append({"name": nm, "error": str(e)[:300]})
        return {"imported": imported, "rebound": rebound, "failed": failed,
                "count": len(imported)}

    try:
        return await run_in_threadpool(_do_import)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@router.get("/api/episodes/{slug}/cast/validate")
def get_cast_validate(slug: str):
    """Cast doctor: cross-check every speaker the script uses against the running
    OmniVoice roster, BEFORE a render. Flags speakers cast to OmniVoice whose
    profile_id is stale (but recoverable by voice_name → self-heals at render) and
    those that resolve by neither (would render a fallback voice → fix the cast or
    import the voice). Speakers with no map entry use the default robot voice."""
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    sm = (m.get("voice") or {}).get("speaker_map") or {}
    used = []
    seen = set()
    for c in (m.get("cues") or []):
        s = c.get("speaker")
        if s and s not in seen and c.get("hold_seconds") is None and (c.get("vo") or "").strip():
            seen.add(s); used.append(s)

    roster = voices.list_profiles_safe()
    live_ids = {p.get("id") for p in roster.get("profiles") or []}
    live_names = {p.get("name") for p in roster.get("profiles") or []}

    speakers, problems = [], []
    for s in used:
        v = sm.get(s)
        if not isinstance(v, dict) or v.get("engine") != "omnivoice":
            speakers.append({"speaker": s, "engine": (v or {}).get("engine") or "default",
                             "status": "default_voice"})
            continue
        pid, vname = v.get("profile_id"), v.get("voice_name")
        if pid and pid in live_ids:
            status = "ok"
        elif vname and vname in live_names:
            status = "self_heal"   # id stale but resolves by name at render
        else:
            status = "missing"; problems.append(s)
        speakers.append({"speaker": s, "engine": "omnivoice",
                         "voice_name": vname, "profile_id": pid, "status": status})

    return {"slug": slug, "engine_running": roster.get("running", False),
            "profiles_loaded": len(live_ids),
            "ok": not problems and roster.get("running", False),
            "missing": problems, "speakers": speakers,
            "hint": ("Import/clone the missing voices (import_voices) so they resolve by "
                     "name, then re-render." if problems else
                     ("Start OmniVoice (start_voice_engine) to confirm against the live roster."
                      if not roster.get("running") else "All cast voices resolve."))}


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
