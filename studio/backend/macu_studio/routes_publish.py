"""Publish a show's text bundle to its macu-web (mayorawesome.com) git repo, plus the
one-paste "connect" flow and per-episode publish-state toggle."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from . import publish as publish_mod
from . import manifest as manifest_mod
from . import validate as validate_mod

router = APIRouter()


def _web_call(method: str, path: str, body: dict | None = None) -> dict:
    """Proxy a call to the connected macu-web instance (Bearer PAT). Studio's frontend can't hit
    macu-web cross-origin, so the backend does it server-side."""
    c = _read_creds()
    web, token = c.get("web"), c.get("token")
    if not web or not token:
        raise HTTPException(400, "not connected to macu-web (re-paste the connect token to get the web URL)")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{web}{path}", data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # Cloudflare bot-fight 403s the default Python-urllib UA — present a normal one.
            "User-Agent": "Mozilla/5.0 (MACU Studio)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise HTTPException(e.code, e.read().decode()[:200])
    except Exception as e:
        raise HTTPException(502, f"macu-web unreachable: {e}")

CREDS = Path.home() / ".config" / "macu-studio" / "macu-web.json"


def _read_creds() -> dict:
    if os.environ.get("MACU_WEB_GIT_BASE") and os.environ.get("MACU_WEB_TOKEN"):
        return {"base": os.environ["MACU_WEB_GIT_BASE"].rstrip("/"), "token": os.environ["MACU_WEB_TOKEN"]}
    if CREDS.exists():
        try:
            return json.loads(CREDS.read_text())
        except Exception:
            return {}
    return {}


@router.get("/api/macu-web/status")
def macu_web_status():
    """Is Studio connected to a macu-web instance? (base/web only — never the token.)"""
    c = _read_creds()
    return {"connected": bool(c.get("base") and c.get("token")), "base": c.get("base"), "web": c.get("web")}


@router.post("/api/macu-web/connect")
def macu_web_connect(body: dict = Body(...)):
    """Accept a one-paste connect token (`macu-connect.<base64url({base,token})>`) from the
    macu-web Manage page and write the push credentials — no git commands for the user."""
    raw = str((body or {}).get("token") or "").strip()
    if raw.startswith("macu-connect."):
        raw = raw[len("macu-connect."):]
    try:
        pad = raw + "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(pad).decode("utf-8"))
        base = str(data["base"]).rstrip("/")
        token = str(data["token"])
        web = str(data.get("web") or "").rstrip("/")
        if not base or not token:
            raise ValueError("empty base/token")
    except Exception as e:
        raise HTTPException(400, f"invalid connect token: {e}")
    CREDS.parent.mkdir(parents=True, exist_ok=True)
    CREDS.write_text(json.dumps({"base": base, "web": web, "token": token}, indent=2))
    try:
        CREDS.chmod(0o600)
    except OSError:
        pass
    return {"ok": True, "base": base, "web": web}


@router.post("/api/shows/{show}/publish")
def post_publish(show: str, body: dict = Body(default={})):
    res = publish_mod.publish(show, (body or {}).get("message"))
    # Explicitly trigger the macu-web reindex after a push. The bare repo's own post-receive
    # hook can be stale/misconfigured (esp. across hosts), so don't rely on it — call the
    # reindex endpoint with our PAT (owner-scoped). Never fail the publish if this errors.
    if res.get("pushed"):
        try:
            res["reindex"] = _web_call("POST", f"/api/reindex/{show}")
        except HTTPException as e:
            res["reindex_error"] = getattr(e, "detail", str(e))
    return res


@router.post("/api/episodes/{slug}/macu-web/youtube")
def set_video_id(slug: str, body: dict = Body(...)):
    """Set/clear the episode's hosted-video id in manifest.youtube.video_id (accepts a bare id or
    a pasted YouTube URL). Drives the macu-web embed after the next publish. Empty value clears it."""
    from . import episodes as ep_mod
    raw = str((body or {}).get("video_id") or "").strip()
    vid = ep_mod.extract_video_id(raw) if raw else None
    if raw and vid is None:
        raise HTTPException(400, "not a valid YouTube video id or URL")
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    yt = dict(m.get("youtube") or {})
    if vid:
        yt["video_id"] = vid
    else:
        yt.pop("video_id", None)
    if yt:
        m["youtube"] = yt
    else:
        m.pop("youtube", None)
    manifest_mod.save(slug, m)
    return {"ok": True, "slug": slug, "video_id": vid}


@router.post("/api/episodes/{slug}/macu-web/published")
def set_published(slug: str, body: dict = Body(...)):
    """Set/clear the manifest `published` flag — controls public visibility on macu-web
    (published=true → shown; false/absent → pushed but hidden draft)."""
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    pub = bool((body or {}).get("published"))
    if pub:
        m["published"] = True
    else:
        m.pop("published", None)
    manifest_mod.save(slug, m)
    return {"ok": True, "slug": slug, "published": pub}


@router.post("/api/episodes/{slug}/macu-web/meta")
def set_meta(slug: str, body: dict = Body(...)):
    """Patch episode metadata in the manifest (title / notes=description / season / episode_num)."""
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    # Clamp text fields to macu-web's limits so what you save matches what the web will store.
    text_limit = {"title": validate_mod.LIMITS["title"], "notes": validate_mod.LIMITS["synopsis"]}
    for key in ("title", "notes"):
        if key in body:
            v = validate_mod.clamp_text(body[key], text_limit[key])
            if v:
                m[key] = v
            else:
                m.pop(key, None)
    for key in ("season", "episode_num"):
        if key in body:
            v = body[key]
            if v in (None, ""):
                m.pop(key, None)
            else:
                try:
                    m[key] = int(v)
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{key} must be a number")
    manifest_mod.save(slug, m)
    return {"ok": True, "slug": slug}


@router.get("/api/episodes/{slug}/macu-web/episode")
def macuweb_episode_status(slug: str):
    """Live visibility/public/url for this episode on the connected macu-web."""
    return _web_call("GET", f"/api/episode/{slug}/visibility")


@router.post("/api/episodes/{slug}/macu-web/visibility")
def macuweb_set_visibility(slug: str, body: dict = Body(...)):
    """Set the episode's macu-web visibility (PUBLIC/UNLISTED/PRIVATE) from Studio."""
    return _web_call("POST", f"/api/episode/{slug}/visibility", {"visibility": (body or {}).get("visibility")})
