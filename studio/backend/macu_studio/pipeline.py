"""Proxy to the macu-render serve.py on :8773.

We delegate all job execution to it (it owns the GPU queue + persistent state)
and re-stream its SSE to the browser.
"""
from __future__ import annotations
import asyncio, json, time
from typing import Any, AsyncIterator
import httpx

from . import config
from .config import RENDER_URL
from . import shows as shows_mod
from .runtime_state import remember_job

TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=10.0, pool=10.0)


async def submit(slug: str, *, from_stage: int | None = None, only: int | None = None) -> dict:
    body: dict[str, Any] = {"slug": slug}
    if from_stage and from_stage > 1:
        body["from_stage"] = int(from_stage)
    if only:
        body["only"] = int(only)
    # Tell the render server where this episode lives ONLY when it's not the
    # default show's flat dir — so the proven MACU render path is byte-identical
    # (no episodes_dir → serve.py uses its built-in default).
    try:
        _show, ep_dir = shows_mod.resolve_episode(slug)
        ep_root = str(ep_dir.parent)
        if ep_root != str(config.EPISODES):
            body["episodes_dir"] = ep_root
    except FileNotFoundError:
        pass
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(f"{RENDER_URL}/render", json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"upstream render returned {r.status_code}: {r.text}")
    data = r.json()
    job_id = data.get("job_id")
    if job_id:
        remember_job(job_id, slug)
    return data


async def status(job_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{RENDER_URL}/status/{job_id}")
    if r.status_code == 404:
        return {"error": "job not found"}
    return r.json()


async def jobs_list() -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{RENDER_URL}/jobs")
    return r.json()


async def stream(job_id: str, since: int = 0) -> AsyncIterator[bytes]:
    """Proxy SSE stream from upstream. Yields raw bytes for the client.

    We inject keep-alive comments every 15s so intermediaries (and our own
    fastapi StreamingResponse) don't time the connection out.
    """
    url = f"{RENDER_URL}/events/{job_id}?since={since}"
    yield f": macu-studio sse open job={job_id} ts={time.time():.0f}\n\n".encode()
    last_send = time.time()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            async with client.stream("GET", url) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    yield f"event: error\ndata: {json.dumps({'status': r.status_code, 'body': body.decode(errors='replace')})}\n\n".encode()
                    return
                async for chunk in r.aiter_bytes():
                    if not chunk:
                        continue
                    yield chunk
                    last_send = time.time()
                    if time.time() - last_send > 15:
                        yield b": ping\n\n"
        except (httpx.RemoteProtocolError, httpx.ReadError, asyncio.CancelledError):
            return
    yield b"event: end\ndata: {}\n\n"
