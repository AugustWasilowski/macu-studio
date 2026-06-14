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

# Non-Soul one-off character reference still. Soul-family models (soul/soul_2)
# without a trained soul_id give an arbitrary identity, so a general image model
# is the right default until Soul IDs are first-class (SSA-129). Overridable via
# the manifest higgsfield.image_model / a character's still_model.
HF_DEFAULT_STILL_MODEL = "nano_banana_pro"


def apply_style(prompt: str, style: dict | None) -> tuple[str, str]:
    """Fold a show/episode style block into a still prompt.

    Returns (prompt_with_suffix, negative). Idempotent on the suffix so callers
    that already append it (the b-roll seed-still path) aren't doubled. This is
    what gives Higgsfield stills the show's monochrome look — without it the HF
    path emitted COLOR stills that violated the B&W rule (SSA-128 bug 2)."""
    suffix = ((style or {}).get("suffix") or "").strip()
    negative = ((style or {}).get("negative") or "").strip()
    base = (prompt or "").strip()
    if suffix and not base.endswith(suffix):
        base = f"{base}{', ' if base and not suffix.startswith(',') else ''}{suffix}".strip()
    return base, negative


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
                       dest: Path, name: str = "macu-still",
                       style: dict | None = None) -> dict:
    """Generate one still → PNG at dest. Returns {seed, params, model}.

    `style` is the routed show/episode style block ({suffix, negative}); it's
    folded into the prompt (and the negative, for the local engines) so every
    engine honors the show look — Higgsfield included (was the B&W-drop bug)."""
    prompt, negative = apply_style(prompt, style)
    if engine == "comfy_zimage":
        params = {**(params or {}), **({"negative": negative} if negative else {})}
        return await comfy_stills.generate_one(prompt, seed, params, dest)
    if engine == "remote_render":
        return await remote_render.generate_one(prompt, seed, params, dest, name=name)
    if engine == "higgsfield":
        # No negative_prompt on HF's generate_image — the B&W suffix in the prompt
        # carries the monochrome look instead.
        model = (params or {}).get("model") or HF_DEFAULT_STILL_MODEL
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
