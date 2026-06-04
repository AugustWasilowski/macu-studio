"""YouTube Data API v3 client for the landing page.

Fetches the channel's uploads (title, thumbnail, view count) and fuzzy-matches
them against the local episode list. Everything degrades gracefully: with no
creds we return [], and any API/network error falls back to the on-disk cache
(or []). Results are cached to ~/.config/macu-studio/youtube_cache.json with a
~6h TTL so the page is snappy and we don't burn quota on every load.
"""
from __future__ import annotations

import json
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

import httpx

from . import config
from . import gen_manifest

_API = "https://www.googleapis.com/youtube/v3"
_CACHE_PATH = Path.home() / ".config" / "macu-studio" / "youtube_cache.json"
_CACHE_TTL = 6 * 3600  # seconds
_MATCH_THRESHOLD = 0.5


def _read_cache() -> Optional[dict]:
    if not _CACHE_PATH.exists():
        return None
    try:
        return json.loads(_CACHE_PATH.read_text())
    except Exception:
        return None


def _write_cache(uploads: list[dict]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps({"ts": time.time(), "uploads": uploads}, indent=2))
    except Exception:
        pass


async def _fetch_uploads() -> list[dict]:
    """One full round-trip to the Data API. Raises on any HTTP/parse error so the
    caller can fall back to cache."""
    api_key = config.YOUTUBE_API_KEY
    channel_id = config.YOUTUBE_CHANNEL_ID
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. channel → uploads playlist id
        r = await client.get(f"{_API}/channels", params={
            "part": "contentDetails", "id": channel_id, "key": api_key,
        })
        r.raise_for_status()
        items = r.json().get("items") or []
        if not items:
            return []
        uploads_pl = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # 2. playlistItems → snippets (title, videoId, thumbnails)
        snippets: list[dict] = []
        page_token = None
        while True:
            params: dict[str, Any] = {
                "part": "snippet", "playlistId": uploads_pl,
                "maxResults": 50, "key": api_key,
            }
            if page_token:
                params["pageToken"] = page_token
            r = await client.get(f"{_API}/playlistItems", params=params)
            r.raise_for_status()
            data = r.json()
            snippets.extend(data.get("items") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # 3. videos → statistics (viewCount), batched 50 ids at a time
        video_ids = [
            s["snippet"]["resourceId"]["videoId"]
            for s in snippets
            if s.get("snippet", {}).get("resourceId", {}).get("videoId")
        ]
        stats: dict[str, dict] = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            r = await client.get(f"{_API}/videos", params={
                "part": "statistics", "id": ",".join(batch), "key": api_key,
            })
            r.raise_for_status()
            for v in r.json().get("items") or []:
                stats[v["id"]] = v.get("statistics") or {}

    out: list[dict] = []
    for s in snippets:
        sn = s.get("snippet") or {}
        vid = (sn.get("resourceId") or {}).get("videoId")
        if not vid:
            continue
        thumbs = sn.get("thumbnails") or {}
        thumb = (
            (thumbs.get("medium") or thumbs.get("high") or thumbs.get("default") or {}).get("url")
            or ""
        )
        view_count = int((stats.get(vid) or {}).get("viewCount") or 0)
        out.append({
            "video_id": vid,
            "title": sn.get("title") or "",
            "thumbnail": thumb,
            "view_count": view_count,
            "published_at": sn.get("publishedAt") or "",
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return out


async def uploads() -> list[dict]:
    """Cached, graceful list of channel uploads. Returns [] when unconfigured."""
    if not (config.YOUTUBE_API_KEY and config.YOUTUBE_CHANNEL_ID):
        return []
    cache = _read_cache()
    if cache and (time.time() - float(cache.get("ts") or 0)) < _CACHE_TTL:
        return cache.get("uploads") or []
    try:
        ups = await _fetch_uploads()
        _write_cache(ups)
        return ups
    except Exception:
        # network/quota/parse error — serve stale cache if we have it, else []
        if cache:
            return cache.get("uploads") or []
        return []


def match_episodes(ups: list[dict], eps: list) -> dict[str, Optional[dict]]:
    """Fuzzy-match each episode title to its best upload by normalized title.

    `eps` is a list of EpisodeSummary dataclasses (slug + title). Returns
    {slug: upload | None}; a match must clear _MATCH_THRESHOLD."""
    norm_ups = [(gen_manifest._norm(u.get("title") or ""), u) for u in ups]
    out: dict[str, Optional[dict]] = {}
    for e in eps:
        slug = getattr(e, "slug", None) if not isinstance(e, dict) else e.get("slug")
        title = getattr(e, "title", "") if not isinstance(e, dict) else e.get("title", "")
        target = gen_manifest._norm(title or "")
        best: Optional[dict] = None
        best_ratio = 0.0
        if target:
            for nu, u in norm_ups:
                if not nu:
                    continue
                ratio = SequenceMatcher(None, target, nu).ratio()
                if ratio > best_ratio:
                    best_ratio, best = ratio, u
        out[slug] = best if best_ratio >= _MATCH_THRESHOLD else None
    return out
