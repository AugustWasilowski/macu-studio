"""Higgsfield.ai routes — OAuth connect lifecycle, account/catalog reads, and
the per-episode cost estimate.

The generation broker routes (media upload / generate / job polling, used by
pipeline stage 2b) live here too once the cloud stage lands.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from . import engines
from . import higgsfield as hf
from . import hfcache as hfc
from . import manifest as manifest_mod
from . import still_engines
from . import stilljobs
from .config import SHARES
from .episodes import episode_dir

router = APIRouter()


def _callback_uri(request: Request) -> str:
    """The redirect URI we register with Higgsfield's OAuth server.

    Their authorize endpoint only accepts http for *localhost hosts (everything
    else must be https), so:
    1. MACU_HIGGSFIELD_REDIRECT_URI env wins — set it to an https URL that
       reaches Studio (e.g. a Tailscale Serve port) for a zero-friction connect.
    2. An https request base is used as-is.
    3. Otherwise fall back to http://localhost:<port>/... — authorize accepts
       it; if the browser isn't on the Studio box the redirect lands on a dead
       localhost page, but the code+state are in its address bar and the
       Settings panel's paste-the-redirect-URL fallback completes the connect.
    """
    override = os.environ.get("MACU_HIGGSFIELD_REDIRECT_URI", "").strip()
    if override:
        return override
    base = str(request.base_url).rstrip("/")
    if base.startswith("https://"):
        return f"{base}/api/higgsfield/oauth/callback"
    port = request.base_url.port or 8774
    return f"http://localhost:{port}/api/higgsfield/oauth/callback"


@router.get("/api/higgsfield/auth")
async def get_auth():
    st = hf.status()
    out: dict = {**st, "plan": None, "credits": None}
    if st["connected"]:
        try:
            bal = await hf.balance()
            out["credits"] = bal.get("credits")
            out["plan"] = bal.get("subscription_plan_type")
        except hf.NotConnectedError:
            # Tokens on disk but unusable (revoked / refresh failed).
            out["connected"] = False
        except Exception as e:
            out["balance_error"] = str(e)
    return out


@router.post("/api/higgsfield/auth/start")
async def post_auth_start(request: Request, body: dict = Body(default={})):
    redirect_uri = (body.get("redirect_uri") or "").strip() or _callback_uri(request)
    try:
        return await hf.auth_start(redirect_uri)
    except Exception as e:
        raise HTTPException(400, f"could not start Higgsfield OAuth: {e}")


@router.post("/api/higgsfield/auth/poll")
def post_auth_poll(body: dict = Body(...)):
    handle = (body.get("handle") or "").strip()
    if not handle:
        raise HTTPException(400, "handle required")
    return hf.connect_status(handle)


@router.get("/api/higgsfield/oauth/callback")
def get_oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        msg = f"Authorization failed: {error}"
    elif not code:
        msg = "Authorization failed: no code in callback"
    else:
        r = hf.oauth_callback(code, state or None)
        msg = "Connected to Higgsfield — you can close this tab." if r.get("ok") \
            else f"Could not complete: {r.get('error')}"
    return HTMLResponse(
        "<html><body style='font-family:system-ui;background:#111;color:#eee;"
        "display:flex;align-items:center;justify-content:center;height:100vh'>"
        f"<div style='text-align:center'><h2>MACU Studio</h2><p>{msg}</p></div>"
        "</body></html>"
    )


@router.post("/api/higgsfield/auth/manual")
def post_auth_manual(body: dict = Body(...)):
    url = (body.get("redirect_url") or "").strip()
    if not url:
        raise HTTPException(400, "redirect_url required")
    r = hf.auth_manual(url)
    if r.get("error"):
        raise HTTPException(400, r["error"])
    return r


@router.post("/api/higgsfield/auth/disconnect")
def post_auth_disconnect():
    hf.disconnect()
    return hf.status()


@router.get("/api/higgsfield/balance")
async def get_balance(force: bool = False):
    try:
        return await hf.balance(force=force)
    except hf.NotConnectedError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"balance failed: {e}")


@router.get("/api/higgsfield/models")
async def get_models(refresh: bool = False):
    try:
        return await hf.models(refresh=refresh)
    except hf.NotConnectedError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"models failed: {e}")


# ---- cost estimate ------------------------------------------------------------

# Cost is parameter-shaped, not prompt-shaped: one get_cost preflight per
# (model, duration, resolution, aspect_ratio) shape covers every shot with that
# shape. Process-cached 1h so the Assembly dialog renders instantly.
_cost_cache: dict[str, dict] = {}
_COST_TTL = 3600


def _extract_credits(res) -> float | None:
    if isinstance(res, (int, float)):
        return float(res)
    if isinstance(res, dict):
        for k in ("cost", "credits", "total_cost", "total_credits", "price", "amount"):
            v = res.get(k)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, dict):
                inner = _extract_credits(v)
                if inner is not None:
                    return inner
    return None


async def _shape_cost(shape: dict) -> float | None:
    key = json.dumps(shape, sort_keys=True)
    e = _cost_cache.get(key)
    if e and e["at"] > time.time() - _COST_TTL:
        return e["credits"]
    res = await hf.get_cost({**shape, "prompt": "cost preflight"})
    credits = _extract_credits(res)
    _cost_cache[key] = {"at": time.time(), "credits": credits}
    return credits


@router.post("/api/higgsfield/cost")
async def post_cost(body: dict = Body(...)):
    """One get_cost preflight for an arbitrary generation shape (the Settings
    model browser's per-model price check). Never submits a job. body:
    {model, duration?, resolution?, aspect_ratio?}."""
    model = (body.get("model") or "").strip()
    if not model:
        raise HTTPException(400, "model required")
    shape = {"model": model}
    for k in ("duration", "resolution", "aspect_ratio"):
        if body.get(k):
            shape[k] = body[k]
    try:
        credits = await _shape_cost(shape)
    except hf.NotConnectedError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"cost preflight failed: {e}")
    return {"model": model, "shape": shape, "credits": credits}


@router.get("/api/episodes/{slug}/higgsfield/estimate")
async def get_estimate(slug: str):
    """Credit cost of rendering this episode's NON-CACHED cloud shots.
    Cached (hash-fresh) shots are free; crop/trim edits never re-bill."""
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown episode {slug}")
    ep = episode_dir(slug)
    cached = hfc.load_sidecar(hfc.clips_sidecar_path(ep), "shots")
    lipsync_engine = engines.route("lipsync")

    shots_out: list[dict] = []
    total = 0.0
    unknown = 0
    try:
        for cue, shot in hfc.cloud_shots(m):
            st = hfc.shot_state(shot, cue, m, ep, cached, lipsync_engine=lipsync_engine)
            kind = shot.get("kind")
            row: dict = {"id": shot.get("id"), "cue": cue.get("id"), "kind": kind,
                         "cached": st["fresh"], "credits": 0.0, "segments": 1, "note": None}
            if not st["fresh"]:
                params = hfc.shot_params(shot, m)
                if kind == "lipsync" and lipsync_engine != "higgsfield":
                    # Local/remote engines don't bill — listed, priced zero.
                    row["note"] = ("local ComfyUI engine — free"
                                   if lipsync_engine == "local_wan"
                                   else "remote render engine — free")
                elif kind == "lipsync":
                    vo = ep / "vo" / f"{cue.get('id')}.wav"
                    dur = manifest_mod._wav_dur(vo)
                    if dur is None:
                        row["credits"] = None
                        row["note"] = "vo wav missing — run stage 1 first to price this lipsync"
                        unknown += 1
                    else:
                        nseg = max(1, math.ceil(dur / hfc.CHUNK_MAX_S))
                        seg_dur = min(15, max(1, math.ceil(dur / nseg)))
                        per = await _shape_cost({**params, "duration": seg_dur})
                        row["segments"] = nseg
                        row["credits"] = round(per * nseg, 2) if per is not None else None
                        if per is None:
                            unknown += 1
                else:
                    c = await _shape_cost(params)
                    row["credits"] = c
                    if c is None:
                        unknown += 1
                if row["credits"]:
                    total += row["credits"]
            shots_out.append(row)
    except hf.NotConnectedError as e:
        raise HTTPException(409, str(e))

    # Character stills referenced by cloud shots (image gen; cost not preflighted —
    # image models are cheap and often plan-unlimited, so they're listed, not priced).
    stills_out: list[dict] = []
    scache = hfc.load_sidecar(hfc.stills_sidecar_path(ep), "stills")
    chars = m.get("characters") or {}
    for who in hfc.referenced_stills(m):
        char = chars.get(who) if isinstance(chars.get(who), dict) else {}
        h = hfc.still_hash(char, m)
        p = hfc.still_path(ep, who)
        fresh = p.exists() and (scache.get(who) is None or scache.get(who) == h)
        stills_out.append({"who": who, "cached": fresh,
                           "has_prompt": bool(char.get("still_prompt"))})

    bal = None
    try:
        bal = await hf.balance()
    except Exception:
        pass
    credits_avail = (bal or {}).get("credits")
    # tri-state: True/False when we can actually judge, None when balance or any
    # per-shot cost is unknown (UI shows a "verify on higgsfield.ai" hint then).
    sufficient = None
    if credits_avail is not None and unknown == 0:
        sufficient = credits_avail >= total
    return {
        "shots": shots_out,
        "stills": stills_out,
        "total_credits": round(total, 2),
        "unknown_costs": unknown,
        "balance": credits_avail,
        "plan": (bal or {}).get("subscription_plan_type"),
        "sufficient": sufficient,
    }


# ---- character stills (cloud image gen) -----------------------------------------

# Still jobs live in the shared registry (stilljobs.py) — same keys as before
# ("<slug>:<who>"), so the status route's responses are unchanged.
STILL_JOBS = stilljobs.JOBS
_png_normalize = stilljobs.png_normalize


async def _gen_still(slug: str, who: str, key: str) -> None:
    job = STILL_JOBS[key]
    try:
        m = manifest_mod.load(slug)
        ep = episode_dir(slug)
        chars = m.get("characters") or {}
        char = chars.get(who) if isinstance(chars.get(who), dict) else {}
        prompt = (char.get("still_prompt") or "").strip()
        if not prompt:
            raise RuntimeError(f"character '{who}' has no still_prompt — set one first")
        blk = hfc.hf_block(m)
        # Honors Settings → Engines routing (local Z-Image / Higgsfield / remote).
        engine = still_engines.resolve_engine()
        job["state"] = "generating"
        job["engine"] = engine
        dest = hfc.still_path(ep, who)
        params = {"model": char.get("still_model") or blk["image_model"]} \
            if engine == "higgsfield" else {}
        await still_engines.generate_one(engine, prompt, None, params, dest,
                                         name=f"{slug}-{who}")
        if engine == "comfy_zimage":
            from . import comfy_stills
            await comfy_stills.free_vram()
        # Stamp the sidecar so derive/estimate can prove freshness.
        sc_path = hfc.stills_sidecar_path(ep)
        entries = hfc.load_sidecar(sc_path, "stills")
        entries[who] = hfc.still_hash(char, m)
        hfc.save_sidecar(sc_path, "stills", entries)
        job["state"] = "done"
    except Exception as e:
        job["state"] = "error"
        job["error"] = str(e)


@router.post("/api/episodes/{slug}/characters/{who}/still/regen")
async def post_still_regen(slug: str, who: str):
    """(Re)generate a character's still via Higgsfield image gen. Async — poll
    the matching /still/status. Drops the cache entry first so a re-run after
    a prompt edit regenerates."""
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown episode {slug}")
    chars = m.get("characters") or {}
    if who not in chars:
        raise HTTPException(404, f"unknown character {who}")
    not_ready = still_engines.check_ready(still_engines.resolve_engine())
    if not_ready:
        raise HTTPException(409, not_ready)
    key = f"{slug}:{who}"
    if stilljobs.is_active(key):
        raise HTTPException(409, f"a still generation for {who} is already running")
    ep = episode_dir(slug)
    sc_path = hfc.stills_sidecar_path(ep)
    entries = hfc.load_sidecar(sc_path, "stills")
    if who in entries:
        entries.pop(who)
        hfc.save_sidecar(sc_path, "stills", entries)
    stilljobs.start(key, "higgsfield", 1, lambda job: _gen_still(slug, who, key))
    return {"ok": True, "key": key}


@router.get("/api/episodes/{slug}/characters/{who}/still/status")
async def get_still_status(slug: str, who: str):
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown episode {slug}")
    ep = episode_dir(slug)
    chars = m.get("characters") or {}
    char = chars.get(who) if isinstance(chars.get(who), dict) else {}
    p = hfc.still_path(ep, who)
    entries = hfc.load_sidecar(hfc.stills_sidecar_path(ep), "stills")
    fresh = p.exists() and (entries.get(who) is None or entries.get(who) == hfc.still_hash(char, m))
    job = STILL_JOBS.get(f"{slug}:{who}") or {}
    return {"exists": p.exists(), "fresh": fresh,
            "mtime": p.stat().st_mtime if p.exists() else None,
            "has_prompt": bool(char.get("still_prompt")),
            "job": {"state": job.get("state"), "error": job.get("error")} if job else None}


@router.get("/api/episodes/{slug}/still/{who}")
async def get_still(slug: str, who: str):
    p = hfc.still_path(episode_dir(slug), who)
    if not p.exists():
        raise HTTPException(404, "no still")
    return FileResponse(str(p), media_type="image/png")


# ---- generation broker (used by pipeline stage 2b) -------------------------------

def _confine(path_str: str) -> Path:
    """Reject paths outside the shares root (same rule as serve.py episodes_dir)."""
    p = Path(path_str).resolve()
    if not str(p).startswith(str(Path(SHARES).resolve()) + "/"):
        raise HTTPException(400, f"path must live under {SHARES}")
    if not p.exists():
        raise HTTPException(404, f"no such file: {p}")
    return p


@router.post("/api/higgsfield/media/upload")
async def post_media_upload(body: dict = Body(...)):
    """Local file (under the shares root) → confirmed Higgsfield media_id."""
    p = _confine(str(body.get("path") or ""))
    try:
        return {"media_id": await hf.upload_media(p)}
    except hf.NotConnectedError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"upload failed: {e}")


@router.post("/api/higgsfield/generate")
async def post_generate(body: dict = Body(...)):
    """Submit a generation. body: {tool: generate_video|generate_image, params: {...}}."""
    tool = body.get("tool") or "generate_video"
    if tool not in ("generate_video", "generate_image"):
        raise HTTPException(400, "tool must be generate_video or generate_image")
    params = body.get("params")
    if not isinstance(params, dict) or not params.get("model"):
        raise HTTPException(400, "params object with a model is required")
    try:
        return await hf.generate(tool, params)
    except hf.NotConnectedError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"generate failed: {e}")


@router.get("/api/higgsfield/jobs/{job_id}")
async def get_job(job_id: str, sync: bool = False):
    """job_status passthrough. Result-media URLs are surfaced as `urls` so the
    pipeline can download without knowing the payload shape."""
    try:
        res = await hf.call("job_status", {"jobId": job_id, "sync": bool(sync)}, timeout=90)
    except hf.NotConnectedError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"job_status failed: {e}")
    out = res if isinstance(res, dict) else {"raw": res}
    out.setdefault("urls", hf.find_media_urls(res))
    return out


# ---- per-shot regeneration -----------------------------------------------------------

@router.post("/api/episodes/{slug}/shot/{shot_id}/higgsfield/regen")
async def post_cloud_shot_regen(slug: str, shot_id: str):
    """Force-regenerate ONE cloud shot: drop its cache entry + clip, then queue
    stage 2 (which skips everything still cached, so only this clip re-bills).
    Explicit user action — estimate the cost first (estimate endpoint/tool)."""
    from . import pipeline as pipeline_mod  # late import (pipeline pulls config/shows)
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown episode {slug}")
    target = next(((c, s) for c, s in hfc.cloud_shots(m) if s.get("id") == shot_id), None)
    if target is None:
        raise HTTPException(404, f"no cloud shot '{shot_id}' in {slug} "
                                 f"(only kind higgsfield/lipsync shots can be regenerated here)")
    if not hf.status()["connected"]:
        raise HTTPException(409, "Higgsfield not connected — connect in Settings → Higgsfield")
    ep = episode_dir(slug)
    sc_path = hfc.clips_sidecar_path(ep)
    entries = hfc.load_sidecar(sc_path, "shots")
    if shot_id in entries:
        entries.pop(shot_id)
        hfc.save_sidecar(sc_path, "shots", entries)
    clip = hfc.clip_path(ep, shot_id)
    if clip.exists():
        clip.unlink()
    # Lipsync chain intermediates are fingerprint-guarded, but a forced regen
    # means "give me a different take" — clear them so the chain restarts.
    work = ep / ".work" / f"hf_{shot_id}"
    if work.exists():
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    return await pipeline_mod.submit(slug, only=2)
