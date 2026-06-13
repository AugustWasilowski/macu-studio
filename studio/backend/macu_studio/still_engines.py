"""Routed still generation — one entry point for all three engines.

Used by the Characters library (takes) AND the episode still regen route, so
both honor Settings → Engines routing. No module here imports still_engines,
so it can import all the engine impls without cycles.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from . import comfy_stills
from . import engines
from . import higgsfield as hf
from . import remote_render
from . import stilljobs

STILL_ENGINES = ("comfy_zimage", "higgsfield", "remote_render")


def resolve_engine(requested: str = "") -> str:
    engine = (requested or "").strip() or engines.route("stills")
    if engine not in STILL_ENGINES:
        raise ValueError(f"engine must be one of {', '.join(STILL_ENGINES)}")
    return engine


def check_ready(engine: str) -> str | None:
    """None when usable, else a human reason (the routes turn it into a 409)."""
    if engine == "higgsfield" and not hf.status()["connected"]:
        return "Higgsfield not connected — connect in Settings → Higgsfield"
    if engine == "remote_render" and not engines.remote_url():
        return "remote render service not configured — Settings → Engines"
    return None


async def generate_one(engine: str, prompt: str, seed: int | None, params: dict,
                       dest: Path, name: str = "macu-still") -> dict:
    """Generate one still → PNG at dest. Returns {seed, params, model}."""
    if engine == "comfy_zimage":
        return await comfy_stills.generate_one(prompt, seed, params, dest)
    if engine == "remote_render":
        return await remote_render.generate_one(prompt, seed, params, dest, name=name)
    if engine == "higgsfield":
        model = (params or {}).get("model") or "soul_2"
        g = await hf.generate("generate_image", {
            "model": model, "prompt": prompt, "aspect_ratio": "1:1", "count": 1,
        })
        res = await hf.wait_job(g["job_id"], timeout=600)
        urls = hf.find_media_urls(res, exts=(".png", ".jpg", ".jpeg", ".webp")) \
            or hf.find_media_urls(res)
        if not urls:
            raise RuntimeError(f"Higgsfield job finished but returned no image: {str(res)[:200]}")
        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as t:
            raw = Path(t.name)
        try:
            await hf.download(urls[0], raw)
            stilljobs.png_normalize(raw, dest)
        finally:
            raw.unlink(missing_ok=True)
        return {"seed": seed, "params": {}, "model": model}
    raise RuntimeError(f"unknown still engine: {engine}")
