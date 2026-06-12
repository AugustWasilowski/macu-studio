"""Client for a remote MACU render service (the leo-render :8779 API).

Contract (see the leo-render skill / deploy-lipsync README on the render box):
  POST /render-image {name, prompt, params{width,height,steps,cfg,shift,seed}} → {job_id}
  GET  /status/<id> → {status: queued|running|done|error, output, output_size, error?}
  GET  /result/<id> → result bytes (fallback when `output` isn't a readable path here)
  POST /render {name, image_path, audio_path, params{frames,steps,audio_cfg_scale}}
       (talking-head — typed here as the seam for the future local-lipsync round)

The service queues jobs FIFO on a single GPU; first render after a service start
is slow (one-time kernel compile, ~70s for an image).
"""
from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

import httpx

from . import engines
from . import stilljobs

POLL_S = 5.0
IMAGE_TIMEOUT_S = 420.0   # cold start ≈ 70s + queue room


def _url() -> str:
    u = engines.remote_url()
    if not u:
        raise RuntimeError("remote render service is not configured — set + enable "
                           "its URL in Settings → Engines")
    return u


async def generate_one(prompt: str, seed: int | None, params: dict, dest: Path,
                       name: str = "macu-still") -> dict:
    """Generate one still on the remote service → PNG at dest."""
    base = _url()
    p = {"width": 1024, "height": 1024, "steps": 8, "cfg": 1.0, "shift": 3.0}
    p.update({k: v for k, v in (params or {}).items()
              if k in ("width", "height", "steps", "cfg", "shift")})
    if seed is not None:
        p["seed"] = seed
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(f"{base}/render-image",
                         json={"name": name, "prompt": prompt, "params": p})
        if r.status_code >= 400:
            raise RuntimeError(f"remote render rejected the job ({r.status_code}): {r.text[:300]}")
        job_id = r.json().get("job_id")
        if not job_id:
            raise RuntimeError(f"no job_id from remote render: {r.text[:200]}")

        deadline = time.time() + IMAGE_TIMEOUT_S
        output = None
        while True:
            await asyncio.sleep(POLL_S)
            st = (await c.get(f"{base}/status/{job_id}")).json()
            status = st.get("status")
            if status == "done":
                output = st.get("output")
                break
            if status == "error":
                raise RuntimeError(f"remote render failed: {st.get('error') or 'unknown error'}")
            if time.time() > deadline:
                raise TimeoutError(f"remote render still '{status}' after {int(IMAGE_TIMEOUT_S)}s "
                                   "(cold start takes ~70s; a queue ahead adds more)")

        # The service reports a share path translated for THIS side; use it when
        # readable, else pull the bytes (mandatory for installs without the share).
        src = Path(output) if output else None
        if src and src.exists():
            await asyncio.to_thread(stilljobs.png_normalize, src, dest)
        else:
            r = await c.get(f"{base}/result/{job_id}")
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as t:
                raw = Path(t.name)
                t.write(r.content)
            try:
                await asyncio.to_thread(stilljobs.png_normalize, raw, dest)
            finally:
                raw.unlink(missing_ok=True)
    return {"seed": p.get("seed"), "params": p, "model": "remote_render"}


async def render_talking_head(image_path: str, audio_path: str, name: str,
                              params: dict | None = None) -> str:
    """Talking-head seam (unused this round — local-lipsync wiring lands later).
    Returns the job_id; callers poll /status themselves."""
    base = _url()
    body = {"name": name, "image_path": image_path, "audio_path": audio_path,
            "params": params or {"frames": 89, "steps": 10, "audio_cfg_scale": 3.0}}
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(f"{base}/render", json=body)
        r.raise_for_status()
        return r.json()["job_id"]
