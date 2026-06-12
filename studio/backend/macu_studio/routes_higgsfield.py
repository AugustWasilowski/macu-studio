"""Higgsfield.ai routes — OAuth connect lifecycle + account/catalog reads.

The generation broker routes (media upload / generate / job polling, used by
pipeline stage 2b) live here too once the cloud stage lands; auth + reads come
first so the Settings tab can connect.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import higgsfield as hf

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
