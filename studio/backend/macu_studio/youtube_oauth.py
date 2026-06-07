"""YouTube OAuth2 (device flow) + caption upload — the WRITE side of the YouTube
integration (the read side in youtube.py uses an API key).

`captions.insert` needs an OAuth access token with the `youtube.force-ssl` scope, which
an API key can't provide. We use the OAuth 2.0 **device flow** (a "TVs and Limited Input
devices" client): the UI shows a URL + code, the user approves on any device, and we get
a refresh token. No google client libraries — raw httpx.

Creds live at ~/.config/macu-studio/youtube_oauth.json (mode 600):
  {client_id, client_secret, refresh_token}
client_id/secret are also overridable via env (YOUTUBE_OAUTH_CLIENT_ID/SECRET).
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

import httpx

SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/captions"

_CRED_PATH = Path.home() / ".config" / "macu-studio" / "youtube_oauth.json"

# Locale code -> BCP-47 caption language. Mostly identity; our codes are already BCP-47.
LOCALE_TO_YT = {"en": "en"}  # everything else passes through unchanged


def yt_lang(locale: str) -> str:
    return LOCALE_TO_YT.get(locale, locale)


# ---- credential storage ----------------------------------------------------

def _load() -> dict:
    if _CRED_PATH.exists():
        try:
            return json.loads(_CRED_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save(data: dict) -> None:
    _CRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CRED_PATH.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(_CRED_PATH, 0o600)
    except OSError:
        pass


def _client() -> tuple[str, str]:
    d = _load()
    cid = os.environ.get("YOUTUBE_OAUTH_CLIENT_ID", "").strip() or str(d.get("client_id") or "").strip()
    sec = os.environ.get("YOUTUBE_OAUTH_CLIENT_SECRET", "").strip() or str(d.get("client_secret") or "").strip()
    return cid, sec


def save_client(client_id: str, client_secret: str) -> None:
    d = _load()
    d["client_id"] = (client_id or "").strip()
    d["client_secret"] = (client_secret or "").strip()
    _save(d)


def clear_token() -> None:
    d = _load()
    d.pop("refresh_token", None)
    _save(d)
    _token_cache.clear()


def status() -> dict:
    cid, sec = _client()
    d = _load()
    return {"has_client": bool(cid and sec), "connected": bool(d.get("refresh_token"))}


# ---- device flow -----------------------------------------------------------

# handle -> {device_code, interval, expires_at}
_pending: dict[str, dict] = {}


def device_start() -> dict:
    cid, sec = _client()
    if not (cid and sec):
        raise RuntimeError("no OAuth client configured")
    r = httpx.post(DEVICE_CODE_URL, data={"client_id": cid, "scope": SCOPE}, timeout=15)
    r.raise_for_status()
    d = r.json()
    handle = secrets.token_urlsafe(12)
    _pending[handle] = {
        "device_code": d["device_code"],
        "interval": int(d.get("interval", 5)),
        "expires_at": time.time() + int(d.get("expires_in", 1800)),
    }
    return {
        "handle": handle,
        "user_code": d["user_code"],
        "verification_url": d.get("verification_url") or d.get("verification_uri"),
        "interval": int(d.get("interval", 5)),
    }


def device_poll(handle: str) -> dict:
    p = _pending.get(handle)
    if not p:
        return {"error": "unknown or expired session"}
    if time.time() > p["expires_at"]:
        _pending.pop(handle, None)
        return {"error": "code expired — start again"}
    cid, sec = _client()
    r = httpx.post(TOKEN_URL, data={
        "client_id": cid, "client_secret": sec,
        "device_code": p["device_code"], "grant_type": DEVICE_GRANT,
    }, timeout=15)
    d = r.json()
    if "refresh_token" in d:
        creds = _load()
        creds["refresh_token"] = d["refresh_token"]
        _save(creds)
        _pending.pop(handle, None)
        _token_cache.update({"access_token": d.get("access_token"),
                             "expires_at": time.time() + int(d.get("expires_in", 3500)) - 60})
        return {"connected": True}
    err = d.get("error")
    if err in ("authorization_pending", "slow_down"):
        return {"pending": True}
    return {"error": d.get("error_description") or err or "authorization failed"}


# ---- access token ----------------------------------------------------------

_token_cache: dict = {}


def access_token() -> str:
    if _token_cache.get("access_token") and time.time() < _token_cache.get("expires_at", 0):
        return _token_cache["access_token"]
    cid, sec = _client()
    rt = _load().get("refresh_token")
    if not (cid and sec and rt):
        raise RuntimeError("not connected to YouTube")
    r = httpx.post(TOKEN_URL, data={
        "client_id": cid, "client_secret": sec,
        "refresh_token": rt, "grant_type": "refresh_token",
    }, timeout=15)
    if r.status_code >= 400:
        raise RuntimeError(f"token refresh failed ({r.status_code}): {r.text[:200]}")
    d = r.json()
    _token_cache.update({"access_token": d["access_token"],
                         "expires_at": time.time() + int(d.get("expires_in", 3500)) - 60})
    return d["access_token"]


# ---- captions --------------------------------------------------------------

def list_captions(video_id: str) -> list[dict]:
    r = httpx.get(f"{API}/captions", params={"part": "snippet", "videoId": video_id},
                  headers={"Authorization": f"Bearer {access_token()}"}, timeout=15)
    if r.status_code >= 400:
        raise RuntimeError(f"captions.list failed ({r.status_code}): {r.text[:200]}")
    out = []
    for it in r.json().get("items", []):
        sn = it.get("snippet") or {}
        out.append({"id": it.get("id"), "language": sn.get("language"),
                    "name": sn.get("name"), "track_kind": sn.get("trackKind")})
    return out


def _multipart(meta: dict, srt_bytes: bytes) -> tuple[bytes, str]:
    """Build a multipart/related body (metadata JSON + SRT media) for the media upload."""
    boundary = "----macuyt" + secrets.token_hex(8)
    parts = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps(meta) + "\r\n"
        + f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n"
    ).encode() + srt_bytes + f"\r\n--{boundary}--\r\n".encode()
    return parts, f"multipart/related; boundary={boundary}"


def upload_caption(video_id: str, language: str, name: str, srt_path: str,
                   existing_id: str | None = None) -> dict:
    """Insert (or, when existing_id is given, replace) a caption track. Returns
    {action: inserted|updated}."""
    srt_bytes = Path(srt_path).read_bytes()
    token = access_token()
    if existing_id:
        meta = {"id": existing_id, "snippet": {"videoId": video_id, "language": language,
                                               "name": name, "isDraft": False}}
        body, ctype = _multipart(meta, srt_bytes)
        r = httpx.put(UPLOAD, params={"part": "snippet", "uploadType": "multipart"},
                      headers={"Authorization": f"Bearer {token}", "Content-Type": ctype},
                      content=body, timeout=120)
        action = "updated"
    else:
        meta = {"snippet": {"videoId": video_id, "language": language,
                            "name": name, "isDraft": False}}
        body, ctype = _multipart(meta, srt_bytes)
        r = httpx.post(UPLOAD, params={"part": "snippet", "uploadType": "multipart"},
                       headers={"Authorization": f"Bearer {token}", "Content-Type": ctype},
                       content=body, timeout=120)
        action = "inserted"
    if r.status_code >= 400:
        raise RuntimeError(f"caption {action} failed ({r.status_code}): {r.text[:300]}")
    return {"action": action, "id": r.json().get("id")}
