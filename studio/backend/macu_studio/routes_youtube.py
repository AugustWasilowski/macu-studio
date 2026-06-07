"""YouTube routes.

Read side (API key): uploads + episode→video matching.
Write side (OAuth device flow): connect + upload Localize caption tracks to a matched video.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Body, HTTPException

from . import youtube
from . import youtube_oauth as yt_oauth
from .episodes import list_episodes, episode_dir

router = APIRouter()


@router.get("/api/youtube/uploads")
async def get_uploads():
    return {"uploads": await youtube.uploads()}


@router.get("/api/youtube/matches")
async def get_matches():
    ups = await youtube.uploads()
    eps = list_episodes()
    matches = youtube.match_episodes(ups, eps)
    # surface slug+title alongside the match so the UI doesn't need a 2nd fetch
    episodes = [{"slug": e.slug, "title": e.title} for e in eps]
    return {"matches": matches, "episodes": episodes}


# ---- OAuth (device flow) ---------------------------------------------------

@router.get("/api/youtube/auth")
def get_auth():
    return yt_oauth.status()


@router.post("/api/youtube/auth/client")
def post_auth_client(body: dict = Body(...)):
    cid = (body.get("client_id") or "").strip()
    sec = (body.get("client_secret") or "").strip()
    if not (cid and sec):
        raise HTTPException(400, "client_id and client_secret are required")
    yt_oauth.save_client(cid, sec)
    return yt_oauth.status()


@router.post("/api/youtube/auth/start")
def post_auth_start():
    try:
        return yt_oauth.device_start()
    except Exception as e:
        raise HTTPException(400, f"could not start device flow: {e}")


@router.post("/api/youtube/auth/poll")
def post_auth_poll(body: dict = Body(...)):
    handle = (body.get("handle") or "").strip()
    if not handle:
        raise HTTPException(400, "handle required")
    return yt_oauth.device_poll(handle)


@router.post("/api/youtube/auth/disconnect")
def post_auth_disconnect():
    yt_oauth.clear_token()
    return yt_oauth.status()


# ---- caption tracks --------------------------------------------------------

async def _matched_video_id(slug: str):
    ups = await youtube.uploads()
    eps = list_episodes()
    m = youtube.match_episodes(ups, eps).get(slug)
    return (m or {}).get("video_id"), (m or {}).get("title")


def _available_srts(slug: str) -> list[dict]:
    """English + each translated SRT present for the episode."""
    fdir = episode_dir(slug) / "final"
    out = []
    en = fdir / f"{slug}.srt"
    if en.exists():
        out.append({"lang": "en", "srt": str(en)})
    if fdir.exists():
        for f in sorted(fdir.iterdir()):
            mm = re.match(rf"^{re.escape(slug)}\.([a-zA-Z][a-zA-Z-]{{1,8}})\.srt$", f.name)
            if mm and not mm.group(1)[0].isdigit():
                out.append({"lang": mm.group(1), "srt": str(f)})
    return out


@router.get("/api/episodes/{slug}/youtube/captions")
async def get_captions(slug: str):
    st = yt_oauth.status()
    video_id, title = await _matched_video_id(slug)
    available = [{"lang": a["lang"]} for a in _available_srts(slug)]
    existing: list[dict] = []
    err = None
    if st["connected"] and video_id:
        try:
            existing = yt_oauth.list_captions(video_id)
        except Exception as e:
            err = str(e)
    return {"connected": st["connected"], "has_client": st["has_client"],
            "video_id": video_id, "matched_title": title,
            "available": available, "existing": existing, "error": err}


@router.post("/api/episodes/{slug}/youtube/captions")
async def post_captions(slug: str, body: dict = Body(default={})):
    if not yt_oauth.status()["connected"]:
        raise HTTPException(409, "not connected to YouTube")
    video_id, _title = await _matched_video_id(slug)
    if not video_id:
        raise HTTPException(409, "no matched YouTube video for this episode")
    want = body.get("languages")
    avail = _available_srts(slug)
    if want:
        avail = [a for a in avail if a["lang"] in set(want)]
    if not avail:
        raise HTTPException(400, "no subtitle tracks available to upload")
    try:
        existing = yt_oauth.list_captions(video_id)
    except Exception as e:
        raise HTTPException(502, f"captions.list failed: {e}")
    results = []
    for a in avail:
        ytlang = yt_oauth.yt_lang(a["lang"])
        # Replace only a STANDARD same-language track (never an ASR/auto one).
        prev = next((c for c in existing if c.get("language") == ytlang
                     and (c.get("track_kind") or "standard") != "ASR"), None)
        try:
            r = yt_oauth.upload_caption(video_id, ytlang, "", a["srt"],
                                        existing_id=prev.get("id") if prev else None)
            results.append({"lang": a["lang"], "action": r["action"]})
        except Exception as e:
            results.append({"lang": a["lang"], "action": "error", "error": str(e)})
    return {"ok": True, "results": results}
