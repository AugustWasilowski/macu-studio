"""CoWork job-board routes — REST CRUD over the in-process store (cowork_jobs).

The SSA-133 hand-off queue between CoWork (browser generation, free) and
Studio/Leo (API harvest + placement). This is the raw store surface used by the
queue UI, Leo, and debugging; CoWork itself drives the queue through Max's
``cowork_*`` MCP tools (which call cowork_jobs directly and add placement-on-done).

No auth here, same as the rest of Studio — front it with Max's token gate before
any LAN/CoWork exposure; do NOT expose :8774 to untrusted networks.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from . import cowork_jobs as jobs

router = APIRouter()


@router.get("/api/cowork/jobs")
def list_jobs(episode: str | None = None, status: str | None = None,
              kind: str | None = None):
    return {"jobs": jobs.list_jobs(episode=episode, status=status, kind=kind)}


@router.get("/api/cowork/jobs/stats")
def jobs_stats(episode: str | None = None):
    return jobs.stats(episode=episode)


@router.post("/api/cowork/jobs")
def create_jobs(body: dict = Body(...)):
    """Single job (kind/target/...) or a batch ({"episode": ..., "jobs": [...]})."""
    try:
        if isinstance(body.get("jobs"), list):
            episode = body.get("episode") or ""
            created = jobs.bulk_create(episode, body["jobs"])
            return {"created": created, "count": len(created)}
        job = jobs.create_job(
            body.get("episode") or "", body.get("kind"), body.get("target"),
            prompt=body.get("prompt", ""), model=body.get("model", ""),
            params=body.get("params"), note=body.get("note", ""))
        return job
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))


@router.post("/api/cowork/jobs/claim")
def claim_job(body: dict = Body(default={})):
    """Atomically claim the oldest pending job (optional episode / kinds filter)."""
    job = jobs.claim_next(episode=body.get("episode"), kinds=body.get("kinds"),
                          by=body.get("by") or "cowork")
    if job is None:
        raise HTTPException(404, "no pending jobs match")
    return job


@router.post("/api/cowork/jobs/clear")
def clear_jobs(body: dict = Body(default={})):
    removed = jobs.clear(episode=body.get("episode"))
    return {"removed": removed}


@router.get("/api/cowork/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    return job


@router.patch("/api/cowork/jobs/{job_id}")
def patch_job(job_id: str, body: dict = Body(...)):
    """Partial update. params/result shallow-merge; claimed_by only changes if
    the key is present (pass null to un-claim)."""
    kwargs: dict = {}
    for k in ("status", "result_gen_ids", "result", "note", "error", "params"):
        if k in body:
            kwargs[k] = body[k]
    if "claimed_by" in body:
        kwargs["claimed_by"] = body["claimed_by"]
    try:
        return jobs.update_job(job_id, **kwargs)
    except KeyError:
        raise HTTPException(404, f"no such job: {job_id}")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/api/cowork/jobs/{job_id}")
def delete_job(job_id: str):
    if not jobs.delete_job(job_id):
        raise HTTPException(404, f"no such job: {job_id}")
    return {"deleted": job_id}
