"""Higgsfield.ai routes — OAuth connect lifecycle, account/catalog reads, and
the per-episode cost estimate.

The generation broker routes (media upload / generate / job polling, used by
pipeline stage 2b) live here too once the cloud stage lands.
"""
from __future__ import annotations

import json
import math
import time

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import higgsfield as hf
from . import hfcache as hfc
from . import manifest as manifest_mod
from .episodes import episode_dir

router = APIRouter()


def _callback_uri(request: Request) -> str:
    # The user's browser resolves this, so a LAN host header works fine.
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/higgsfield/oauth/callback"


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

    shots_out: list[dict] = []
    total = 0.0
    unknown = 0
    try:
        for cue, shot in hfc.cloud_shots(m):
            st = hfc.shot_state(shot, cue, m, ep, cached)
            kind = shot.get("kind")
            row: dict = {"id": shot.get("id"), "cue": cue.get("id"), "kind": kind,
                         "cached": st["fresh"], "credits": 0.0, "segments": 1, "note": None}
            if not st["fresh"]:
                params = hfc.shot_params(shot, m)
                if kind == "lipsync":
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
