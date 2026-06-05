"""MACU Studio FastAPI app.

Endpoints under /api ; SPA mounted at /. Runs as `uvicorn macu_studio.main:app`.
"""
from __future__ import annotations
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import episodes as ep_mod
from . import manifest as manifest_mod
from . import gen_manifest as genman_mod
from . import script as script_mod
from . import scriptdiff as scriptdiff_mod
from . import srt as srt_mod
from . import pipeline as pipeline_mod
from . import media as media_mod
from . import regen as regen_mod
from . import sfx as sfx_mod
from . import agen as agen_mod
from . import assets as assets_mod
from . import sysstat as sysstat_mod
from . import hyperframes as hf_mod
from . import chat as chat_mod
from . import shotgen as shotgen_mod
from . import activity as activity_mod
from . import routes_assets, routes_graphics, routes_writers, routes_youtube, routes_docs, routes_gitsync
from .config import EPISODES, FRONTEND_DIST, CORS_DEV_ORIGINS, CHAT_WEBHOOK_TOKEN, SHARES


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[macu-studio] EPISODES={EPISODES} FRONTEND_DIST={FRONTEND_DIST}")
    yield


app = FastAPI(title="MACU Studio", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_DEV_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "episodes_dir": str(EPISODES), "render_url": pipeline_mod.RENDER_URL}


@app.get("/api/sysstat")
async def get_sysstat():
    """CPU % + GPU % + GPU RAM for the topbar readout (poll ~every 2s)."""
    return await sysstat_mod.snapshot()


_STAGE_LABEL = {
    "vo": "Rendering audio", "masters": "Rendering video", "rife": "Rendering video",
    "assemble": "Assembling video", "graphics": "Rendering graphics", "music": "Rendering music",
    "whisper": "Transcribing", "srt": "Subtitles", "burn": "Burning subtitles",
}


async def _render_label(job: dict) -> str:
    """Friendly label for a running render job — its current stage if we can read it."""
    try:
        st = await pipeline_mod.status(job["id"])
        cur = None
        for e in (st.get("last_events") or []):
            if e.get("kind") == "stage.started":
                cur = e.get("name")
            elif e.get("kind") == "stage.done" and e.get("name") == cur:
                cur = None
        if cur:
            return _STAGE_LABEL.get(cur, f"Rendering ({cur})")
    except Exception:
        pass
    return f"Rendering {job.get('slug', '')}"


@app.get("/api/activity")
async def get_activity():
    """What the box is processing right now, for the topbar job indicator. Aggregates
    the render server's jobs, HyperFrames jobs, and the synchronous-job activity slot.
    Poll ~every 2s. Returns {state: idle|running|error, label}."""
    # 1) render-server job (the heavy, multi-minute work)
    try:
        jobs = (await pipeline_mod.jobs_list()).get("jobs", [])
    except Exception:
        jobs = []
    running = next((j for j in jobs if j.get("state") == "running"), None)
    if running:
        return {"state": "running", "label": await _render_label(running)}
    recent = max((j for j in jobs if j.get("finished_at")), key=lambda j: j["finished_at"], default=None)
    if recent and recent.get("state") == "error" and (time.time() - recent["finished_at"]) < 8:
        return {"state": "error", "label": f"Render failed: {recent.get('slug', '')}"}
    # 2) HyperFrames (title/graphics) jobs
    for job in list(hf_mod.JOBS.values()):
        if getattr(job, "state", None) == "running":
            return {"state": "running", "label": f"Rendering graphics: {job.key}"}
    # 3) synchronous studio jobs (agen sfx/music, shot-gen)
    s = activity_mod.get()
    if s["state"] != "idle":
        return s
    return {"state": "idle", "label": ""}


# ---------- Episodes ----------

@app.get("/api/episodes")
def list_episodes():
    return {"episodes": [e.__dict__ for e in ep_mod.list_episodes()]}


@app.get("/api/episodes/{slug}/manifest")
def get_manifest(slug: str):
    try:
        return manifest_mod.load(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.put("/api/episodes/{slug}/manifest")
async def put_manifest(slug: str, body: dict = Body(...)):
    try:
        return manifest_mod.save(slug, body)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/script")
def get_script(slug: str):
    try:
        return script_mod.read(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.put("/api/episodes/{slug}/script")
async def put_script(slug: str, request: Request):
    body = (await request.body()).decode("utf-8")
    try:
        return script_mod.write(slug, body)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/script/versions")
def get_script_versions(slug: str):
    """Version history of script.md (git sync commits + live working copy)."""
    return {"versions": scriptdiff_mod.versions(slug)}


@app.get("/api/episodes/{slug}/script/diff")
def get_script_diff(slug: str, base: str, target: str):
    """Line-level diff between two script versions (base=older, target=newer)."""
    return scriptdiff_mod.diff(slug, base, target)


@app.post("/api/episodes/{slug}/manifest/from-script")
async def post_manifest_from_script(slug: str, body: dict = Body(default={})):
    """Regenerate manifest.cues from script.md, merging into the existing manifest.

    Default is a dry run returning {summary, cues}. With {"apply": true} it writes
    the merged manifest (after a timestamped manifest.json.bak)."""
    try:
        if bool(body.get("apply")):
            return genman_mod.apply(slug)
        prev = genman_mod.preview(slug)
        return {"summary": prev["summary"], "cues": prev["cues"]}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/cues")
def get_cues(slug: str):
    try:
        return {"cues": manifest_mod.derive_cues(slug)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/shots")
def get_shots(slug: str):
    try:
        return {"shots": manifest_mod.derive_shots(slug)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/titles")
def get_titles(slug: str):
    try:
        return {"titles": manifest_mod.derive_titles(slug)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/pipeline")
def get_pipeline_status(slug: str):
    return {"stages": manifest_mod.episode_pipeline_status(slug)}


@app.get("/api/episodes/{slug}/pipeline/active")
async def get_pipeline_active(slug: str):
    """The currently-running render job id for this episode (or null) — lets the
    Assembly tab re-attach to an in-progress render after a reload / from another
    tab and rebuild its log tail by streaming the job's events."""
    try:
        jobs = (await pipeline_mod.jobs_list()).get("jobs", [])
    except Exception:
        jobs = []
    running = next((j for j in jobs if j.get("slug") == slug and j.get("state") == "running"), None)
    return {"job_id": running["id"] if running else None}


@app.get("/api/episodes/{slug}/final")
def get_final_info(slug: str):
    return manifest_mod.final_info(slug)


@app.get("/api/episodes/{slug}/srt")
def get_srt(slug: str):
    return srt_mod.read(slug)


@app.put("/api/episodes/{slug}/srt")
async def put_srt(slug: str, body: dict = Body(...)):
    return srt_mod.write(slug, body.get("entries") or [])


# ---------- Media streaming ----------

@app.get("/api/episodes/{slug}/cue/{cue_id}/audio")
def get_cue_audio(slug: str, cue_id: str, request: Request):
    p = ep_mod.episode_dir(slug) / "vo" / f"{cue_id}.wav"
    return media_mod.stream_file(request, p, content_type="audio/wav")


@app.get("/api/episodes/{slug}/shot/{key}/preview")
def get_shot_preview(slug: str, key: str, request: Request):
    ep = ep_mod.episode_dir(slug)
    candidates = [
        ep / "clips" / f"{key}_master.zs.webp",
        ep / "clips" / f"broll_{key}.zs.webp",
    ]
    if key == "safe":
        candidates.insert(0, ep / "clips" / "safe_master.zs.webp")
    if key == "empty_room":
        candidates.insert(0, ep / "clips" / "c09_s1.zs.webp")
    for p in candidates:
        if p.exists():
            return media_mod.stream_file(request, p, content_type="image/webp")
    raise HTTPException(404, f"no preview for shot {key}")


@app.get("/api/episodes/{slug}/title/{key}/preview")
def get_title_preview(slug: str, key: str, request: Request):
    if "/" in key or ".." in key:
        raise HTTPException(400, "bad key")
    p = ep_mod.episode_dir(slug) / "titles" / f"{key}.mp4"
    if not p.exists():
        p = SHARES / "assets" / "titles" / f"{key}.mp4"  # shared fallback (stage-4 resolution)
    return media_mod.stream_file(request, p, content_type="video/mp4")


@app.get("/api/episodes/{slug}/final/video")
def get_final_video(slug: str, request: Request):
    p = ep_mod.episode_dir(slug) / "final" / f"{slug}.mp4"
    return media_mod.stream_file(request, p, content_type="video/mp4")


@app.get("/api/episodes/{slug}/final/thumb")
def get_final_thumb(slug: str, request: Request):
    p = ep_mod.episode_dir(slug) / "final" / f"{slug}_thumbs.jpg"
    return media_mod.stream_file(request, p, content_type="image/jpeg")


# ---------- Pipeline ----------

@app.post("/api/episodes/{slug}/pipeline/run")
async def post_run(slug: str, body: dict = Body(default={})):
    try:
        return await pipeline_mod.submit(slug,
                                          from_stage=body.get("from_stage"),
                                          only=body.get("only"))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"upstream render: {e}")


@app.post("/api/episodes/{slug}/cue/{cue_id}/regen")
async def post_cue_regen(slug: str, cue_id: str):
    return await regen_mod.regen_cue(slug, cue_id)


@app.post("/api/episodes/{slug}/shot/{key}/regen")
async def post_shot_regen(slug: str, key: str):
    return await regen_mod.regen_shot(slug, key)


@app.post("/api/episodes/{slug}/title/{key}/regen")
async def post_title_regen(slug: str, key: str):
    """Queue a HyperFrames render for title_assets[key]. Returns {job_id}."""
    try:
        job_id = await hf_mod.submit(slug, key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"job_id": job_id, "queued": True,
            "events_url": f"/api/hf/jobs/{job_id}/stream",
            "status_url": f"/api/hf/jobs/{job_id}"}


@app.get("/api/hf/jobs/{job_id}")
def get_hf_job(job_id: str):
    s = hf_mod.status(job_id)
    if not s:
        raise HTTPException(404, "hyperframes job not found")
    return s


@app.get("/api/hf/jobs/{job_id}/stream")
async def get_hf_job_stream(job_id: str, since: int = 0):
    return StreamingResponse(
        hf_mod.stream(job_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/api/episodes/{slug}/sfx/fetch")
async def post_sfx_fetch(slug: str, body: dict = Body(...)):
    """Run freesound_fetch.py for `query` and pin the result to manifest.sfx[]."""
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "query required")
    cue_id = body.get("cue_id")
    at = body.get("at") or "start"
    if at not in ("start", "end"):
        raise HTTPException(400, "at must be 'start' or 'end'")
    duration_max = float(body.get("duration_max") or 4.0)
    basename = body.get("basename") or None
    gain_db = float(body.get("gain_db") if body.get("gain_db") is not None else -6.0)
    fade_s = float(body.get("fade_s") if body.get("fade_s") is not None else 0.5)
    license_mode = body.get("license") or "cc0"
    return await sfx_mod.fetch_and_pin(
        slug, query, cue_id=cue_id, at=at,
        duration_max=duration_max, basename=basename,
        gain_db=gain_db, fade_s=fade_s, license_mode=license_mode,
    )


@app.delete("/api/episodes/{slug}/sfx")
async def del_sfx(slug: str, file: str):
    return sfx_mod.remove(slug, file)


@app.put("/api/episodes/{slug}/sfx")
async def put_sfx(slug: str, body: dict = Body(...)):
    """Replace manifest.sfx[] wholesale — the single mutation for the Audio-page
    timeline (add-from-library / reorder / move / delay-recompute)."""
    sfx = body.get("sfx")
    if not isinstance(sfx, list):
        raise HTTPException(400, "sfx must be a list")
    m = manifest_mod.load(slug)
    m["sfx"] = sfx
    manifest_mod.save(slug, m)
    return {"ok": True, "count": len(sfx)}


@app.put("/api/episodes/{slug}/overlays")
async def put_overlays(slug: str, body: dict = Body(...)):
    """Replace manifest.overlays[] wholesale — the single mutation for the Graphics
    dope sheet (drag-to-place) and the Video-page timeline (drag/resize/edit/delete
    spanning title-card placements)."""
    overlays = body.get("overlays")
    if not isinstance(overlays, list):
        raise HTTPException(400, "overlays must be a list")
    m = manifest_mod.load(slug)
    m["overlays"] = overlays
    manifest_mod.save(slug, m)
    return {"ok": True, "count": len(overlays)}


@app.put("/api/episodes/{slug}/music/beds")
async def put_music_beds(slug: str, body: dict = Body(...)):
    """Replace manifest.music.beds[] wholesale — the single mutation for the Video
    timeline's MUSIC track (drag-to-place / drag-resize cue-spanning beds). Leaves
    music.clips[] (the file pool) and other music settings untouched."""
    beds = body.get("beds")
    if not isinstance(beds, list):
        raise HTTPException(400, "beds must be a list")
    m = manifest_mod.load(slug)
    music = m.get("music")
    if not isinstance(music, dict):
        music = {}
    music["beds"] = beds
    m["music"] = music
    manifest_mod.save(slug, m)
    return {"ok": True, "count": len(beds)}


# ---------- LLM shot-list generation (Ollama on-demand) ----------

@app.post("/api/episodes/{slug}/shots/generate")
def post_shots_generate(slug: str):
    """Dry run: ask the local LLM to propose the shot list (reuse vs mint + per-cue
    shots). 409 if the GPU is busy (a render is active). Sync def → runs in the
    threadpool so the long model call doesn't block the event loop."""
    busy, free = agen_mod.gpu_busy()
    if busy:
        raise HTTPException(409, f"GPU busy ({free} MiB free) — a render is active; try again when idle")
    activity_mod.set_running("Generating shot list", ttl=180)
    try:
        out = shotgen_mod.generate(slug)
        activity_mod.clear()
        return out
    except FileNotFoundError as e:
        activity_mod.clear()
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        activity_mod.set_error("Shot-gen failed")
        raise HTTPException(500, f"shot-gen failed: {e}")


@app.post("/api/episodes/{slug}/shots/apply")
async def post_shots_apply(slug: str, body: dict = Body(...)):
    """Merge an approved proposal (from /shots/generate, possibly edited) into the
    manifest — write new character/broll defs and set each planned cue's shots[]."""
    proposal = body.get("proposal")
    if not isinstance(proposal, dict):
        raise HTTPException(400, "proposal object required")
    try:
        return shotgen_mod.apply(slug, proposal)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# ---------- Asset library (assets/sfx, assets/music) ----------

@app.get("/api/assets/{kind}")
def get_assets(kind: str):
    if kind not in assets_mod.KINDS:
        raise HTTPException(404, f"unknown asset kind: {kind}")
    return {"assets": assets_mod.list_assets(kind)}


@app.get("/api/assets/{kind}/{file}/audio")
def get_asset_audio(kind: str, file: str, request: Request):
    p = assets_mod.asset_path(kind, file)
    if not p:
        raise HTTPException(404, "asset not found")
    ctype = "audio/mpeg" if p.suffix.lower() == ".mp3" else "audio/wav"
    return media_mod.stream_file(request, p, content_type=ctype)


@app.post("/api/episodes/{slug}/music/add-bed")
async def post_music_add_bed(slug: str, body: dict = Body(...)):
    """Add a library music file to manifest.music.clips[] (a bed)."""
    file = (body.get("file") or "").strip()
    if not file:
        raise HTTPException(400, "file required")
    m = manifest_mod.load(slug)
    music = m.get("music")
    if not isinstance(music, dict):
        music = {}
    clips = music.get("clips")
    if not isinstance(clips, list):
        clips = []
    added = file not in clips
    if added:
        clips.append(file)
    music["clips"] = clips
    music.setdefault("source_dir", str(assets_mod.KINDS["music"]))
    m["music"] = music
    manifest_mod.save(slug, m)
    return {"ok": True, "added": added, "clips": clips}


# ---------- agen (local music/SFX generation) ----------

@app.get("/api/agen/status")
def get_agen_status():
    busy, free = agen_mod.gpu_busy()
    return {"busy": busy, "gpu_free_mib": free, "min_free_mib": agen_mod.MIN_FREE_MIB}


@app.post("/api/episodes/{slug}/sfx/gen")
async def post_sfx_gen(slug: str, body: dict = Body(...)):
    """Generate an SFX one-shot with agen (AudioGen), normalize to kit, pin to manifest.sfx[]."""
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt required")
    at = body.get("at") or "start"
    if at not in ("start", "end"):
        raise HTTPException(400, "at must be 'start' or 'end'")
    activity_mod.set_running("Rendering SFX", ttl=120)
    res = await agen_mod.gen_sfx_and_pin(
        slug, prompt, cue_id=body.get("cue_id"), at=at,
        duration=float(body.get("duration") or 3.0),
        seed=body.get("seed"), basename=body.get("basename") or None,
        gain_db=float(body.get("gain_db") if body.get("gain_db") is not None else -6.0),
        fade_s=float(body.get("fade_s") if body.get("fade_s") is not None else 0.5),
    )
    activity_mod.set_error("SFX gen busy") if res.get("busy") else activity_mod.clear()
    if res.get("busy"):
        raise HTTPException(409, res.get("hint") or "GPU busy")
    return res


@app.post("/api/episodes/{slug}/music/gen")
async def post_music_gen(slug: str, body: dict = Body(...)):
    """Generate a music bed with agen (MusicGen/Riffusion) and add it to manifest.music.clips[]."""
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt required")
    activity_mod.set_running("Rendering music", ttl=180)
    res = await agen_mod.gen_music(
        slug, prompt, engine=body.get("engine") or "music",
        duration=float(body.get("duration") or 20.0),
        seed=body.get("seed"), basename=body.get("basename") or None,
        add_to_clips=bool(body.get("add_to_clips", True)),
    )
    activity_mod.set_error("Music gen busy") if res.get("busy") else activity_mod.clear()
    if res.get("busy"):
        raise HTTPException(409, res.get("hint") or "GPU busy")
    return res


@app.get("/api/jobs")
async def get_jobs():
    return await pipeline_mod.jobs_list()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    return await pipeline_mod.status(job_id)


@app.get("/api/jobs/{job_id}/stream")
async def get_job_stream(job_id: str, since: int = 0):
    return StreamingResponse(
        pipeline_mod.stream(job_id, since=since),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------- Chat (ss-chat-channel → always-on Max session) ----------

@app.post("/api/episodes/{slug}/chat")
async def post_chat(slug: str, body: dict = Body(...)):
    msg = (body.get("message") or "").strip()
    if not msg:
        raise HTTPException(400, "empty message")
    session_id = body.get("session_id") or None
    try:
        result = await chat_mod.send(slug, msg, session_id=session_id)
    except TimeoutError as e:
        raise HTTPException(504, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return result


@app.post("/api/chat/reply")
async def post_chat_reply(request: Request, body: dict = Body(...)):
    """Callback hit by ss-chat-channel when Max calls ss_chat_reply. Token-gated
    by the same SS_CHAT_WEBHOOK_TOKEN the channel signs outbound replies with."""
    presented = (request.headers.get("x-webhook-token") or "").strip()
    if not CHAT_WEBHOOK_TOKEN or presented != CHAT_WEBHOOK_TOKEN:
        raise HTTPException(403, "forbidden")
    request_id = body.get("request_id")
    text = body.get("text")
    if not request_id or not isinstance(text, str):
        raise HTTPException(400, "request_id and text required")
    delivered = chat_mod.deliver(str(request_id), text)
    return {"ok": delivered, "request_id": request_id}


# ---------- Feature routers (versioning, graphics, writers' room, youtube, docs, git-sync) ----------

app.include_router(routes_assets.router)
app.include_router(routes_graphics.router)
app.include_router(routes_writers.router)
app.include_router(routes_youtube.router)
app.include_router(routes_docs.router)
app.include_router(routes_gitsync.router)


# ---------- SPA static mount (last, after API routes) ----------

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
else:
    @app.get("/")
    def _no_spa():
        return JSONResponse(
            {"warning": "frontend not built — run `cd studio/frontend && npm run build`",
             "dist": str(FRONTEND_DIST)},
            status_code=200,
        )
