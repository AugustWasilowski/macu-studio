"""Publish a show's text bundle to its macu-web (mayorawesome.com) git repo, plus the
one-paste "connect" flow and per-episode publish-state toggle."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from . import publish as publish_mod
from . import manifest as manifest_mod

router = APIRouter()

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
    """Is Studio connected to a macu-web instance? (base only — never the token.)"""
    c = _read_creds()
    return {"connected": bool(c.get("base") and c.get("token")), "base": c.get("base")}


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
        if not base or not token:
            raise ValueError("empty base/token")
    except Exception as e:
        raise HTTPException(400, f"invalid connect token: {e}")
    CREDS.parent.mkdir(parents=True, exist_ok=True)
    CREDS.write_text(json.dumps({"base": base, "token": token}, indent=2))
    try:
        CREDS.chmod(0o600)
    except OSError:
        pass
    return {"ok": True, "base": base}


@router.post("/api/shows/{show}/publish")
def post_publish(show: str, body: dict = Body(default={})):
    return publish_mod.publish(show, (body or {}).get("message"))


@router.post("/api/episodes/{slug}/macu-web/youtube")
def set_video_id(slug: str, body: dict = Body(...)):
    """Set/clear the episode's YouTube video id in youtube.txt (accepts a bare id or a pasted
    YouTube URL). Drives the macu-web embed after the next publish. Empty value clears it."""
    import re
    from . import episodes as ep_mod
    raw = str((body or {}).get("video_id") or "").strip()
    vid = ep_mod.extract_video_id(raw) if raw else None
    if raw and vid is None:
        raise HTTPException(400, "not a valid YouTube video id or URL")
    try:
        d = ep_mod.episode_dir(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    f = d / "youtube.txt"
    text = f.read_text() if f.exists() else ""
    lines = [ln for ln in text.splitlines() if not re.match(r"^\s*video_id\s*:", ln, re.I)]
    if vid:
        lines.append(f"video_id: {vid}")
    out = "\n".join(lines).strip()
    f.write_text(out + "\n" if out else "")
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
