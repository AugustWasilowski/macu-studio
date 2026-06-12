"""Higgsfield.ai MCP client — Streamable HTTP + OAuth (DCR + PKCE).

Studio is the ONLY process that holds Higgsfield tokens; the render pipeline
brokers through Studio's /api/higgsfield/* routes instead of speaking MCP
itself (two processes refreshing one rotated refresh token is a race).

Tokens + registered-client info live at ~/.config/macu-studio/higgsfield.json
(mode 600), mirroring youtube_oauth.py. The model catalog is cached at
~/.config/macu-studio/higgsfield_models.json (24h TTL).

Connection model: one OAuthClientProvider shared across per-call MCP sessions.
The SDK runs every request under the provider's internal context lock, so all
Higgsfield traffic is serialized — fine for a single-operator Studio, and it
makes refresh-token rotation safe by construction.

SDK quirk we work around (mcp 1.27): `_initialize()` loads stored tokens but
never sets `token_expiry_time`, so after a Studio restart a stale access token
would be sent as-is → 401 → the SDK jumps to FULL interactive OAuth instead of
a silent refresh. Our storage persists an absolute `expires_at` and hands the
SDK an empty access_token once it's stale, which routes it down the
proactive-refresh path (refresh_token + client_info is all that needs).
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

MCP_URL = os.environ.get("MACU_HIGGSFIELD_MCP_URL", "https://mcp.higgsfield.ai/mcp").rstrip("/")

_CRED_PATH = Path.home() / ".config" / "macu-studio" / "higgsfield.json"
_MODELS_CACHE = Path.home() / ".config" / "macu-studio" / "higgsfield_models.json"
_MODELS_TTL = 24 * 3600
_BALANCE_TTL = 60
_EXPIRY_SLOP = 60  # treat tokens expiring within a minute as already stale


class NotConnectedError(RuntimeError):
    """Raised when a call would need interactive OAuth (no/invalid tokens)."""


# ---- credential storage ------------------------------------------------------

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


class _FileTokenStorage(TokenStorage):
    async def get_tokens(self) -> OAuthToken | None:
        d = _load()
        t = d.get("tokens")
        if not t:
            return None
        tok = OAuthToken.model_validate(t)
        expires_at = d.get("expires_at")
        if expires_at and time.time() > float(expires_at) - _EXPIRY_SLOP:
            # Stale access token: blank it so the SDK's is_token_valid() fails
            # and it refreshes instead of sending it (see module docstring).
            if tok.refresh_token:
                tok = tok.model_copy(update={"access_token": ""})
            else:
                return None
        return tok

    async def set_tokens(self, tokens: OAuthToken) -> None:
        d = _load()
        d["tokens"] = tokens.model_dump(exclude_none=True)
        d["expires_at"] = time.time() + int(tokens.expires_in or 3600)
        _save(d)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        d = _load()
        c = d.get("client_info")
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        d = _load()
        d["client_info"] = json.loads(client_info.model_dump_json(exclude_none=True))
        _save(d)


def status() -> dict:
    d = _load()
    t = d.get("tokens") or {}
    return {"connected": bool(t.get("refresh_token") or t.get("access_token"))}


def disconnect() -> None:
    d = _load()
    d.pop("tokens", None)
    d.pop("expires_at", None)
    # Keep client_info: the DCR registration stays valid and reconnecting with
    # the same redirect URI can reuse it.
    _save(d)
    _reset_provider()
    _balance_cache.clear()


# ---- OAuth provider ----------------------------------------------------------

async def _no_interactive_redirect(_url: str) -> None:
    raise NotConnectedError("Higgsfield not connected — connect in Settings → Higgsfield")


async def _no_interactive_callback() -> tuple[str, str | None]:
    raise NotConnectedError("Higgsfield not connected — connect in Settings → Higgsfield")


def _client_metadata(redirect_uri: str | None) -> OAuthClientMetadata:
    return OAuthClientMetadata.model_validate({
        "client_name": "MACU Studio",
        "redirect_uris": [redirect_uri] if redirect_uri else ["http://127.0.0.1:8774/api/higgsfield/oauth/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    })


_provider: OAuthClientProvider | None = None


def _get_provider() -> OAuthClientProvider:
    """Shared non-interactive provider for normal API calls."""
    global _provider
    if _provider is None:
        stored = _load().get("client_info") or {}
        redirect = (stored.get("redirect_uris") or [None])[0]
        _provider = OAuthClientProvider(
            server_url=MCP_URL,
            client_metadata=_client_metadata(str(redirect) if redirect else None),
            storage=_FileTokenStorage(),
            redirect_handler=_no_interactive_redirect,
            callback_handler=_no_interactive_callback,
        )
    return _provider


def _reset_provider() -> None:
    global _provider
    _provider = None


# ---- MCP calls ----------------------------------------------------------------

def _parse_result(res) -> Any:
    """CallToolResult → python object. Prefer structuredContent; else parse the
    text content as JSON, falling back to the raw string."""
    if getattr(res, "isError", False):
        texts = [c.text for c in (res.content or []) if getattr(c, "text", None)]
        raise RuntimeError("; ".join(texts) or "Higgsfield tool error")
    sc = getattr(res, "structuredContent", None)
    if sc is not None:
        # FastMCP-style servers wrap plain values as {"result": ...}
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    texts = [c.text for c in (res.content or []) if getattr(c, "text", None)]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except Exception:
        return joined


async def call(tool: str, args: dict | None = None, *, timeout: float = 120.0,
               auth: OAuthClientProvider | None = None) -> Any:
    """One tool call on a fresh session (shared auth provider serializes token
    handling across concurrent callers)."""
    provider = auth or _get_provider()
    try:
        async with streamablehttp_client(MCP_URL, auth=provider, timeout=timeout) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                res = await asyncio.wait_for(session.call_tool(tool, args or {}), timeout)
                return _parse_result(res)
    except NotConnectedError:
        raise
    except BaseException as e:  # anyio wraps failures in ExceptionGroups
        nce = _find_exc(e, NotConnectedError)
        if nce:
            raise nce from None
        raise


def _find_exc(e: BaseException, typ: type) -> BaseException | None:
    if isinstance(e, typ):
        return e
    for sub in getattr(e, "exceptions", []) or []:
        found = _find_exc(sub, typ)
        if found:
            return found
    return None


# ---- connect flow (interactive OAuth, driven by REST) --------------------------

# handle -> {auth_url, code_fut, task, status: pending|connected|error, error}
_connect: dict[str, dict] = {}
_active_handle: str | None = None


async def auth_start(redirect_uri: str) -> dict:
    """Kick off interactive OAuth. Returns {handle, auth_url} (or
    {handle, connected: true} when stored tokens already work)."""
    global _active_handle
    # Drop any prior unfinished attempt.
    if _active_handle and (prev := _connect.get(_active_handle)):
        if not prev["task"].done():
            prev["task"].cancel()
        _connect.pop(_active_handle, None)

    # Re-register the client when the redirect URI changes (e.g. localhost vs
    # LAN IP) — the stored registration pins the old URI.
    stored = _load().get("client_info") or {}
    if stored and redirect_uri not in [str(u) for u in stored.get("redirect_uris", [])]:
        d = _load()
        d.pop("client_info", None)
        _save(d)
    _reset_provider()

    loop = asyncio.get_running_loop()
    handle = secrets.token_urlsafe(12)
    entry: dict = {"auth_url": None, "code_fut": loop.create_future(),
                   "url_fut": loop.create_future(), "status": "pending", "error": None}

    async def redirect_handler(url: str) -> None:
        entry["auth_url"] = url
        if not entry["url_fut"].done():
            entry["url_fut"].set_result(url)

    async def callback_handler() -> tuple[str, str | None]:
        return await asyncio.wait_for(entry["code_fut"], timeout=600)

    provider = OAuthClientProvider(
        server_url=MCP_URL,
        client_metadata=_client_metadata(redirect_uri),
        storage=_FileTokenStorage(),
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    async def run() -> None:
        try:
            await call("balance", auth=provider, timeout=900)
            entry["status"] = "connected"
            _reset_provider()  # rebuild the shared provider on fresh tokens
            _balance_cache.clear()
        except asyncio.CancelledError:
            entry["status"] = "error"
            entry["error"] = "cancelled"
            raise
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e) or e.__class__.__name__
            if not entry["url_fut"].done():
                entry["url_fut"].set_exception(RuntimeError(entry["error"]))

    entry["task"] = asyncio.create_task(run())
    _connect[handle] = entry
    _active_handle = handle

    # Either the SDK asks for interactive auth (we get the URL) or the stored
    # tokens still work and the probe completes without it.
    done, _pending = await asyncio.wait(
        [entry["url_fut"], entry["task"]], timeout=30, return_when=asyncio.FIRST_COMPLETED
    )
    if entry["status"] == "connected":
        return {"handle": handle, "connected": True}
    if entry["status"] == "error":
        raise RuntimeError(entry["error"] or "connect failed")
    if entry["url_fut"].done():
        return {"handle": handle, "auth_url": entry["url_fut"].result()}
    entry["task"].cancel()
    raise RuntimeError("timed out waiting for the Higgsfield authorization URL")


def oauth_callback(code: str, state: str | None) -> dict:
    """Resolve the pending connect flow with the authorization code."""
    entry = _connect.get(_active_handle or "")
    if not entry or entry["code_fut"].done():
        return {"error": "no pending Higgsfield connect — start again from Settings"}
    entry["code_fut"].set_result((code, state))
    return {"ok": True}


def auth_manual(redirect_url: str) -> dict:
    """Paste-the-redirect-URL fallback: extract code/state and resolve."""
    q = parse_qs(urlparse(redirect_url.strip()).query)
    code = (q.get("code") or [""])[0]
    state = (q.get("state") or [None])[0]
    if not code:
        return {"error": "no ?code= found in that URL"}
    return oauth_callback(code, state)


def connect_status(handle: str) -> dict:
    entry = _connect.get(handle)
    if not entry:
        return {"status": "error", "error": "unknown or expired connect session"}
    return {"status": entry["status"], "error": entry["error"],
            "auth_url": entry["auth_url"]}


# ---- cached account/catalog calls ----------------------------------------------

_balance_cache: dict = {}


async def balance(force: bool = False) -> dict:
    if not force and _balance_cache.get("at", 0) > time.time() - _BALANCE_TTL:
        return _balance_cache["data"]
    data = await call("balance", timeout=30)
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected balance payload: {data!r}")
    _balance_cache.update({"at": time.time(), "data": data})
    return data


async def models(refresh: bool = False) -> dict:
    """Full model catalog (video + image + audio), disk-cached 24h."""
    if not refresh and _MODELS_CACHE.exists():
        try:
            cached = json.loads(_MODELS_CACHE.read_text())
            if cached.get("at", 0) > time.time() - _MODELS_TTL:
                return cached["data"]
        except Exception:
            pass
    items: list = []
    after: str | None = None
    while True:
        args: dict = {"action": "list", "limit": 100}
        if after:
            args["after"] = after
        page = await call("models_explore", args, timeout=60)
        if not isinstance(page, dict):
            raise RuntimeError(f"unexpected models payload: {page!r}")
        items.extend(page.get("items", []))
        if not page.get("has_more") or not page.get("next_page_token"):
            break
        after = str(page["next_page_token"])
    data = {"items": items}
    _MODELS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _MODELS_CACHE.write_text(json.dumps({"at": time.time(), "data": data}))
    return data


async def get_cost(params: dict) -> Any:
    """Preflight a generate_video call's credit cost without submitting."""
    return await call("generate_video", {"params": {**params, "get_cost": True}}, timeout=60)
