"""Character library routes — roster CRUD, takes, generation, episode sync."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import characters as chars
from . import config
from . import shows as shows_mod
from . import still_engines
from . import stilljobs

router = APIRouter()


def _enrich_takes(show: str, key: str, c: dict) -> dict:
    """Surface a fetchable image URL + local path on each take so a HEADLESS client
    (e.g. Leo over MCP) can pull the bytes to preview, instead of screenshotting the
    Characters page. `url`/`thumb_url` are absolute when MACU_STUDIO_PUBLIC_URL is set,
    else relative to the Studio host the caller is already on. Mutates the response
    dict only (chars.load returns a fresh parse — nothing is written back to disk)."""
    for t in c.get("takes") or []:
        tid = t.get("id")
        if not tid:
            continue
        base = f"/api/shows/{show}/characters/{key}/takes/{tid}"
        t["url"] = config.asset_url(base)
        t["thumb_url"] = config.asset_url(base + "?thumb=true")
        t["path"] = str(chars.take_path(show, key, tid))
    dt = c.get("default_take")
    if dt:
        base = f"/api/shows/{show}/characters/{key}/takes/{dt}"
        c["default_take_url"] = config.asset_url(base)
        c["default_take_thumb_url"] = config.asset_url(base + "?thumb=true")
    return c


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
    show = _check_show(show)
    c = _enrich_takes(show, key, _404(chars.load, show, key))
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

@router.post("/api/shows/{show}/characters/{key}/generate")
async def post_generate(show: str, key: str, body: dict = Body(default={})):
    """Generate 1-4 takes. body: {engine?, prompt?, seed?, count?, params?{model,
    width,height,steps,cfg,shift}}. engine defaults to the routed stills engine."""
    _check_show(show)
    c = _404(chars.load, show, key)
    try:
        engine = still_engines.resolve_engine(body.get("engine") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    not_ready = still_engines.check_ready(engine)
    if not_ready:
        raise HTTPException(409, not_ready)
    prompt = (body.get("prompt") or "").strip() or (c.get("still_prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, f"no prompt — set still_prompt on '{key}' or pass one")
    seed = body.get("seed")
    count = max(1, min(4, int(body.get("count") or 1)))
    params = body.get("params") or {}
    # The show look (B&W suffix + negative) so library takes match the episode aesthetic.
    style = (shows_mod.get_show(show).get("episode_defaults") or {}).get("style")
    jkey = f"lib:{show}:{key}"

    async def runner(job: dict) -> None:
        for i in range(count):
            job["state"] = "generating"
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
                tmp = Path(t.name)
            tmp.unlink()  # engine writes it
            use_seed = (int(seed) + i) if seed not in (None, "") else None
            info = await still_engines.generate_one(engine, prompt, use_seed, params, tmp,
                                                    name=f"{show}-{key}", style=style)
            chars.add_take(show, key, tmp, engine=engine, model=info.get("model"),
                           prompt=prompt, seed=info.get("seed"),
                           params=info.get("params"))
            job["progress"]["done"] = i + 1
        if engine == "comfy_zimage":
            from . import comfy_stills
            await comfy_stills.free_vram()

    try:
        stilljobs.start(jkey, engine, count, runner)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "key": jkey, "engine": engine, "count": count}


@router.get("/api/shows/{show}/characters/{key}/generate/status")
def get_generate_status(show: str, key: str):
    show = _check_show(show)
    job = stilljobs.get(f"lib:{show}:{key}")
    c = _enrich_takes(show, key, _404(chars.load, show, key))
    return {"job": job, "take_count": len(c.get("takes") or []),
            "takes": c.get("takes") or [], "default_take": c.get("default_take"),
            "default_take_url": c.get("default_take_url")}


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
