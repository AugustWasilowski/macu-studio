"""MACU Studio FastAPI app.

Endpoints under /api ; SPA mounted at /. Runs as `uvicorn macu_studio.main:app`.
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import episodes as ep_mod
from . import manifest as manifest_mod
from . import script as script_mod
from . import srt as srt_mod
from . import pipeline as pipeline_mod
from . import media as media_mod
from . import regen as regen_mod
from . import sfx as sfx_mod
from .config import EPISODES, FRONTEND_DIST, CORS_DEV_ORIGINS


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


@app.get("/api/episodes/{slug}/cues")
def get_cues(slug: str):
    return {"cues": manifest_mod.derive_cues(slug)}


@app.get("/api/episodes/{slug}/shots")
def get_shots(slug: str):
    return {"shots": manifest_mod.derive_shots(slug)}


@app.get("/api/episodes/{slug}/titles")
def get_titles(slug: str):
    return {"titles": manifest_mod.derive_titles(slug)}


@app.get("/api/episodes/{slug}/pipeline")
def get_pipeline_status(slug: str):
    return {"stages": manifest_mod.episode_pipeline_status(slug)}


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
    p = ep_mod.episode_dir(slug) / "titles" / f"{key}.mp4"
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
    raise HTTPException(501,
        "title regen not implemented in v0; build the HyperFrames composition "
        "with `npx hyperframes render` and drop the mp4 in titles/")


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


# ---------- Stub chat (v0) ----------

@app.post("/api/episodes/{slug}/chat")
async def post_chat(slug: str, body: dict = Body(...)):
    msg = (body.get("message") or "").strip()
    if not msg:
        raise HTTPException(400, "empty message")
    return {
        "reply": "Max here. The chat bridge isn't wired up yet in v0 — your "
                 "message was received but no real model saw it. "
                 f"(slug={slug}, len={len(msg)})",
        "stub": True,
    }


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
