"""Local ComfyUI still engine — Z-Image-Turbo via the workflow registry.

Async submit/poll against engines.comfy_url(). The result image is fetched
through ComfyUI's /view endpoint (NOT a shared-filesystem read like stage 2
does) so a routed remote ComfyUI works identically to a local one.
"""
from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

import httpx

from . import engines
from . import stilljobs
from . import workflows

POLL_S = 2.0
STALL_S = 120.0   # no history entry yet (cold unet load can take ~60s)
HARD_S = 600.0


async def generate_one(prompt: str, seed: int | None, params: dict, dest: Path,
                       workflow_id: str = "z_image_turbo") -> dict:
    """Generate one still → PNG at dest. Returns {seed, params, workflow}."""
    base = engines.comfy_url()
    graph, applied = workflows.bind(
        workflow_id,
        prompt=prompt,
        seed=seed,
        unet=engines.zimage_unet(),
        **{k: v for k, v in (params or {}).items()
           if k in ("negative", "width", "height", "steps", "cfg")},
    )
    out_node = workflows.load(workflow_id)["meta"]["output_node"]

    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{base}/prompt",
                         json={"prompt": graph, "client_id": "macu-studio-stills"})
        if r.status_code >= 400:
            raise RuntimeError(f"ComfyUI rejected the workflow ({r.status_code}): "
                               f"{r.text[:400]}")
        pid = r.json().get("prompt_id")
        if not pid:
            raise RuntimeError(f"no prompt_id from ComfyUI: {r.text[:200]}")

        start = time.time()
        images = None
        while True:
            await asyncio.sleep(POLL_S)
            try:
                h = (await c.get(f"{base}/history/{pid}")).json()
            except Exception:
                h = {}
            entry = h.get(pid)
            if entry and entry.get("status", {}).get("completed"):
                images = (entry.get("outputs", {}).get(out_node, {}) or {}).get("images") or []
                if not images:
                    raise RuntimeError("ComfyUI finished but produced no image "
                                       f"(node {out_node}); check the workflow/models")
                break
            if entry and entry.get("status", {}).get("status_str") == "error":
                msgs = [m for m in entry.get("status", {}).get("messages", [])
                        if m and m[0] == "execution_error"]
                detail = (msgs[0][1].get("exception_message") if msgs else "") or "execution error"
                raise RuntimeError(f"ComfyUI error: {detail[:400]}")
            elapsed = time.time() - start
            if elapsed > HARD_S:
                raise TimeoutError(f"ComfyUI still not done after {int(HARD_S)}s")
            if elapsed > STALL_S and not entry:
                # not even in history → likely dropped (restart) or queue wedged
                try:
                    q = (await c.get(f"{base}/queue")).json()
                    busy = bool(q.get("queue_running") or q.get("queue_pending"))
                except Exception:
                    busy = False
                if not busy:
                    raise RuntimeError("ComfyUI lost the job (idle queue, no history) — "
                                       "it likely crashed or was restarted")

        img = images[0]
        r = await c.get(f"{base}/view", params={
            "filename": img["filename"],
            "subfolder": img.get("subfolder", ""),
            "type": img.get("type", "output"),
        })
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as t:
            raw = Path(t.name)
            t.write(r.content)
    try:
        await asyncio.to_thread(stilljobs.png_normalize, raw, dest)
    finally:
        raw.unlink(missing_ok=True)
    return {"seed": applied.get("seed"), "params": {k: applied[k] for k in
            ("width", "height", "steps", "cfg") if k in applied},
            "workflow": workflow_id, "model": applied.get("unet")}
