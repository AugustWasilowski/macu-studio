"""Character library routes — roster CRUD, takes, generation, episode sync."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import characters as chars
from . import comfy_stills
from . import engines
from . import higgsfield as hf
from . import remote_render
from . import shows as shows_mod
from . import stilljobs

router = APIRouter()

STILL_ENGINES = ("comfy_zimage", "higgsfield", "remote_render")


def _check_show(show: str) -> str:
    try:
        shows_mod.get_show(show)
        return shows_mod.safe_segment(show, "show id")
    except (KeyError, ValueError, FileNotFoundError):
        raise HTTPException(404, f"unknown show {show}")


def _404(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/shows/{show}/characters")
def get_roster(show: str):
    return {"characters": chars.list_chars(_check_show(show))}


@router.post("/api/shows/{show}/characters")
def post_character(show: str, body: dict = Body(...)):
    key = (body.get("key") or "").strip()
    if not key:
        raise HTTPException(400, "key required")
    return _404(chars.create, _check_show(show), key, body)


@router.get("/api/shows/{show}/characters/{key}")
def get_character(show: str, key: str):
    c = _404(chars.load, _check_show(show), key)
    job = stilljobs.get(f"lib:{show}:{key}")
    return {**c, "job": {"state": job["state"], "error": job["error"],
                         "progress": job["progress"]} if job else None}


@router.put("/api/shows/{show}/characters/{key}")
def put_character(show: str, key: str, body: dict = Body(...)):
    return _404(chars.update, _check_show(show), key, body)


@router.delete("/api/shows/{show}/characters/{key}")
def delete_character(show: str, key: str):
    _404(chars.delete, _check_show(show), key)
    return {"ok": True}


# ---- takes -----------------------------------------------------------------------

@router.get("/api/shows/{show}/characters/{key}/takes/{take}")
def get_take(show: str, key: str, take: str, thumb: bool = False):
    _check_show(show)
    p = _404(chars.thumb_path if thumb else chars.take_path, show, key, take)
    if not thumb and not p.exists():
        raise HTTPException(404, "no such take")
    media = "image/jpeg" if p.suffix == ".jpg" else "image/png"
    return FileResponse(str(p), media_type=media)


@router.delete("/api/shows/{show}/characters/{key}/takes/{take}")
def delete_take(show: str, key: str, take: str):
    return _404(chars.delete_take, _check_show(show), key, take)


@router.post("/api/shows/{show}/characters/{key}/takes/{take}/default")
def post_default_take(show: str, key: str, take: str):
    return _404(chars.set_default_take, _check_show(show), key, take)


@router.post("/api/shows/{show}/characters/{key}/takes/upload")
async def post_upload_take(show: str, key: str, file: UploadFile):
    _check_show(show)
    c = _404(chars.load, show, key)
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as t:
        raw = Path(t.name)
        t.write(await file.read())
    png = raw.with_suffix(".png")
    try:
        stilljobs.png_normalize(raw, png)
        rec = chars.add_take(show, key, png, engine="upload", model=None,
                             prompt="", seed=None, params=None)
    finally:
        raw.unlink(missing_ok=True)
        png.unlink(missing_ok=True)
    return {"ok": True, "take": rec, "default_take": chars.load(show, key)["default_take"],
            "name": c.get("name")}


# ---- generation -------------------------------------------------------------------

async def _gen_one(engine: str, prompt: str, seed: int | None, params: dict,
                   dest: Path, name: str) -> dict:
    if engine == "comfy_zimage":
        return await comfy_stills.generate_one(prompt, seed, params, dest)
    if engine == "remote_render":
        return await remote_render.generate_one(prompt, seed, params, dest, name=name)
    if engine == "higgsfield":
        blk_model = (params or {}).get("model") or "soul_2"
        g = await hf.generate("generate_image", {
            "model": blk_model, "prompt": prompt, "aspect_ratio": "1:1", "count": 1,
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
        return {"seed": seed, "params": {}, "model": blk_model}
    raise RuntimeError(f"unknown still engine: {engine}")


@router.post("/api/shows/{show}/characters/{key}/generate")
async def post_generate(show: str, key: str, body: dict = Body(default={})):
    """Generate 1-4 takes. body: {engine?, prompt?, seed?, count?, params?{model,
    width,height,steps,cfg,shift}}. engine defaults to the routed stills engine."""
    _check_show(show)
    c = _404(chars.load, show, key)
    engine = (body.get("engine") or "").strip() or engines.route("stills")
    if engine not in STILL_ENGINES:
        raise HTTPException(400, f"engine must be one of {', '.join(STILL_ENGINES)}")
    if engine == "higgsfield" and not hf.status()["connected"]:
        raise HTTPException(409, "Higgsfield not connected — connect in Settings → Higgsfield")
    if engine == "remote_render" and not engines.remote_url():
        raise HTTPException(409, "remote render service not configured — Settings → Engines")
    prompt = (body.get("prompt") or "").strip() or (c.get("still_prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, f"no prompt — set still_prompt on '{key}' or pass one")
    seed = body.get("seed")
    count = max(1, min(4, int(body.get("count") or 1)))
    params = body.get("params") or {}
    jkey = f"lib:{show}:{key}"

    async def runner(job: dict) -> None:
        for i in range(count):
            job["state"] = "generating"
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
                tmp = Path(t.name)
            tmp.unlink()  # engine writes it
            use_seed = (int(seed) + i) if seed not in (None, "") else None
            info = await _gen_one(engine, prompt, use_seed, params, tmp,
                                  name=f"{show}-{key}")
            chars.add_take(show, key, tmp, engine=engine, model=info.get("model"),
                           prompt=prompt, seed=info.get("seed"),
                           params=info.get("params"))
            job["progress"]["done"] = i + 1

    try:
        stilljobs.start(jkey, engine, count, runner)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "key": jkey, "engine": engine, "count": count}


@router.get("/api/shows/{show}/characters/{key}/generate/status")
def get_generate_status(show: str, key: str):
    _check_show(show)
    job = stilljobs.get(f"lib:{show}:{key}")
    c = _404(chars.load, show, key)
    return {"job": job, "take_count": len(c.get("takes") or []),
            "takes": c.get("takes") or [], "default_take": c.get("default_take")}


# ---- episode sync ------------------------------------------------------------------

@router.post("/api/shows/{show}/characters/{key}/use")
def post_use(show: str, key: str, body: dict = Body(...)):
    slug = (body.get("slug") or "").strip()
    if not slug:
        raise HTTPException(400, "slug required")
    return _404(chars.use_in_episode, _check_show(show), key, slug,
                take_id=(body.get("take") or None),
                overwrite_still=bool(body.get("overwrite_still")))


@router.get("/api/shows/{show}/characters/{key}/usage")
def get_usage(show: str, key: str):
    return {"usage": _404(chars.usage, _check_show(show), key)}


@router.post("/api/shows/{show}/characters/import-episode")
def post_import_episode(show: str, body: dict = Body(...)):
    slug = (body.get("slug") or "").strip()
    if not slug:
        raise HTTPException(400, "slug required")
    return _404(chars.import_episode, _check_show(show), slug)
