"""Graphics-tab routes: HyperFrames templates, new title cards, YouTube thumbnail.

HF job status/stream is served by main.py's /api/hf/jobs/{job_id}[/stream] — these
routes only kick jobs off (returning the same events_url/status_url shape) and serve
the rendered thumbnail back.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Body, HTTPException

from . import hyperframes, media, versions
from .episodes import episode_dir

router = APIRouter()


@router.get("/api/hf/templates")
def get_hf_templates():
    return {"templates": hyperframes.list_templates()}


@router.get("/api/hf/templates/{composition}/fields")
def get_hf_template_fields(composition: str):
    """The editable ‹PLACEHOLDER› field set for a composition, so the New/Edit modal can
    scaffold the JSON when the layout changes (no LLM needed)."""
    return hyperframes.template_fields(composition)


@router.post("/api/episodes/{slug}/title/new")
async def post_title_new(slug: str, body: dict = Body(...)):
    key = (body.get("key") or "").strip()
    composition = (body.get("composition") or "").strip()
    fields = body.get("fields") or {}
    if not key:
        raise HTTPException(400, "key required")
    if not composition:
        raise HTTPException(400, "composition required")
    try:
        job_id = await hyperframes.submit_new(slug, key, composition, fields)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"job_id": job_id, "queued": True,
            "events_url": f"/api/hf/jobs/{job_id}/stream",
            "status_url": f"/api/hf/jobs/{job_id}"}


@router.post("/api/episodes/{slug}/ythumb/regen")
async def post_ythumb_regen(slug: str, body: dict = Body(default={})):
    fields = body.get("fields") or {}
    composition = (body.get("composition") or "youtube_thumb").strip()
    try:
        job_id = await hyperframes.submit_thumb(slug, fields, composition=composition)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"job_id": job_id, "queued": True,
            "events_url": f"/api/hf/jobs/{job_id}/stream",
            "status_url": f"/api/hf/jobs/{job_id}"}


@router.get("/api/episodes/{slug}/ythumb/preview")
def get_ythumb_preview(slug: str, request: Request):
    p = episode_dir(slug) / "final" / f"{slug}_thumb.png"
    if not p.exists():
        raise HTTPException(404, f"no thumbnail for {slug}")
    return media.stream_file(request, p, content_type="image/png")
