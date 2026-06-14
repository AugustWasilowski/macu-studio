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
import mimetypes
import os
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
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
    handling across concurrent callers).

    The whole body is bounded by `timeout` — NOT just `call_tool`. All HF traffic
    serializes through the shared OAuthClientProvider's lock, so if a predecessor
    wedges while holding it (a stalled status poll / token refresh), a later call
    would otherwise block forever acquiring the lock / setting up the client /
    initializing, before any HTTP request fires (the "generate hangs at 0/1" bug).
    Wrapping everything in wait_for surfaces that as a timeout AND cancels the
    wedged context managers, which releases the lock for the next caller."""
    provider = auth or _get_provider()

    async def _run() -> Any:
        async with streamablehttp_client(MCP_URL, auth=provider, timeout=timeout) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                res = await session.call_tool(tool, args or {})
                return _parse_result(res)

    try:
        return await asyncio.wait_for(_run(), timeout)
    except NotConnectedError:
        raise
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"Higgsfield call '{tool}' timed out after {int(timeout)}s with no response "
            "(a prior request may have wedged the shared session — retry)"
        ) from None
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


# ---- generation helpers ---------------------------------------------------------

async def upload_media(path: Path) -> str:
    """Local file → confirmed media_id (media_upload → PUT bytes → media_confirm)."""
    ct = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    res = await call("media_upload", {"filename": path.name, "content_type": ct}, timeout=60)
    up = res
    if isinstance(res, dict):
        for k in ("uploads", "files", "results"):
            if isinstance(res.get(k), list) and res[k]:
                up = res[k][0]
                break
    media_id = (up or {}).get("media_id") or (up or {}).get("id")
    upload_url = (up or {}).get("upload_url") or (up or {}).get("url")
    if not (media_id and upload_url):
        raise RuntimeError(f"unexpected media_upload payload: {res!r}")
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.put(upload_url, content=path.read_bytes(), headers={"Content-Type": ct})
        r.raise_for_status()
    mtype = ct.split("/")[0]
    if mtype not in ("image", "video", "audio"):
        mtype = "file"
    await call("media_confirm", {"media_id": media_id, "type": mtype}, timeout=60)
    return str(media_id)


def _find_job_id(obj: Any) -> str | None:
    if isinstance(obj, dict):
        for k in ("job_id", "jobId", "id"):
            v = obj.get(k)
            if isinstance(v, str) and len(v) >= 32 and "-" in v:
                return v
        for v in obj.values():
            found = _find_job_id(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_job_id(v)
            if found:
                return found
    return None


def find_media_urls(obj: Any, exts: tuple[str, ...] = (".mp4", ".webm", ".mov", ".png",
                                                       ".jpg", ".jpeg", ".webp", ".gif")) -> list[str]:
    """Recursively collect result-media URLs from a job payload (shape-tolerant)."""
    out: list[str] = []

    def walk(o: Any, key: str = "") -> None:
        if isinstance(o, str):
            if o.startswith("http") and (
                any(o.split("?")[0].lower().endswith(e) for e in exts)
                or key in ("url", "video_url", "image_url", "media_url", "download_url")
            ):
                out.append(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)

    walk(obj)
    # de-dupe, keep order
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


async def generate(tool: str, params: dict) -> dict:
    """Submit a generation; returns {job_id, raw}. tool ∈ generate_video|generate_image."""
    res = await call(tool, {"params": params}, timeout=300)
    job_id = _find_job_id(res)
    if not job_id:
        raise RuntimeError(f"no job id in {tool} response: {str(res)[:400]}")
    return {"job_id": job_id, "raw": res}


_TERMINAL_OK = ("completed", "succeeded", "success", "done")
_TERMINAL_BAD = ("failed", "error", "nsfw", "canceled", "cancelled", "rejected")


async def wait_job(job_id: str, timeout: float = 900.0) -> dict:
    """Poll job_status until terminal; honors the server's poll_after_seconds hint."""
    deadline = time.time() + timeout
    while True:
        res = await call("job_status", {"jobId": job_id, "sync": True}, timeout=90)
        st = str((res or {}).get("status") or (res or {}).get("state") or "").lower()
        if any(s in st for s in _TERMINAL_OK):
            return res
        if any(s in st for s in _TERMINAL_BAD):
            detail = (res or {}).get("error") or (res or {}).get("detail") or st
            raise RuntimeError(f"Higgsfield job {job_id} {st}: {detail}")
        if time.time() > deadline:
            raise TimeoutError(f"Higgsfield job {job_id} still {st or 'pending'} after {int(timeout)}s")
        hint = (res or {}).get("poll_after_seconds")
        try:
            delay = min(max(float(hint), 2.0), 30.0) if hint else 5.0
        except (TypeError, ValueError):
            delay = 5.0
        await asyncio.sleep(delay)


async def download(url: str, dest: Path) -> Path:
    """Streaming download to dest via a .part tmp + atomic replace."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        async with httpx.AsyncClient(timeout=600, follow_redirects=True) as c:
            async with c.stream("GET", url) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    async for chunk in r.aiter_bytes(1 << 20):
                        f.write(chunk)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


# ---- Soul characters / Elements / account / provenance (SSA-129) ----------------
# Leo owns this client layer; Studio UI (Max) consumes the shapes. All thin
# passthroughs over call() so the response shapes match the live HF MCP tools.

async def soul_list(status: str | None = None, type_: str = "soul_2",
                    size: int = 100) -> dict:
    """Trained Soul characters. status ∈ ready|training|failed (None = all).
    Returns {items:[{id, name, status, type}], next_cursor}."""
    args: dict = {"action": "list", "type": type_, "size": size}
    if status:
        args["status"] = status
    res = await call("show_characters", args, timeout=60)
    return res if isinstance(res, dict) else {"items": res}


async def soul_train(name: str, images: list[str], type_: str = "soul_2") -> dict:
    """Start Soul training (5-20 ref images: media_id / job_id / https URLs).
    Non-blocking — poll soul_status(soul_id). Returns the new character record."""
    if not name or not images:
        raise RuntimeError("soul_train needs a name and 5-20 reference images")
    return await call("show_characters",
                      {"action": "train", "type": type_, "name": name, "images": images},
                      timeout=120)


async def soul_status(soul_id: str, type_: str = "soul_2") -> dict:
    return await call("show_characters",
                      {"action": "status", "type": type_, "soul_id": soul_id}, timeout=60)


async def elements_list(size: int = 100) -> dict:
    """Reusable reference Elements (instant single-image identity refs).
    Returns {items:[...], next_cursor}."""
    res = await call("show_reference_elements", {"action": "list", "size": size}, timeout=60)
    return res if isinstance(res, dict) else {"items": res}


async def element_get(element_id: str) -> dict:
    return await call("show_reference_elements",
                      {"action": "get", "element_id": element_id}, timeout=60)


async def element_create(medias: list[dict], name: str | None = None,
                         category: str = "character", description: str | None = None) -> dict:
    """Create an Element from already-uploaded media. medias: [{id, url, type}].
    Use element_from_file() to go straight from a local still."""
    if not medias:
        raise RuntimeError("element_create needs at least one media {id, url}")
    args: dict = {"action": "create", "medias": medias, "category": category}
    if name:
        args["name"] = name
    if description:
        args["description"] = description
    return await call("show_reference_elements", args, timeout=120)


async def upload_media_ref(path: Path) -> dict:
    """Like upload_media but also returns the media's public Higgsfield URL —
    Elements/reference creation needs {id, url}, not just the id."""
    ct = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    res = await call("media_upload", {"filename": path.name, "content_type": ct}, timeout=60)
    up = res
    if isinstance(res, dict):
        for k in ("uploads", "files", "results"):
            if isinstance(res.get(k), list) and res[k]:
                up = res[k][0]
                break
    media_id = (up or {}).get("media_id") or (up or {}).get("id")
    upload_url = (up or {}).get("upload_url") or (up or {}).get("url")
    if not (media_id and upload_url):
        raise RuntimeError(f"unexpected media_upload payload: {res!r}")
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.put(upload_url, content=path.read_bytes(), headers={"Content-Type": ct})
        r.raise_for_status()
    mtype = ct.split("/")[0]
    if mtype not in ("image", "video", "audio"):
        mtype = "file"
    await call("media_confirm", {"media_id": media_id, "type": mtype}, timeout=60)
    # The PUT target's path (minus the signed query) is the media's public origin URL.
    public_url = (up or {}).get("public_url") or (up or {}).get("media_url") \
        or str(upload_url).split("?")[0]
    return {"media_id": str(media_id), "url": public_url}


async def element_from_file(path: Path, name: str | None = None,
                            category: str = "character") -> dict:
    """Upload a local still and register it as a reusable Element in one step."""
    ref = await upload_media_ref(path)
    return await element_create(
        [{"id": ref["media_id"], "url": ref["url"], "type": "media_input"}],
        name=name, category=category)


async def transactions(size: int = 20, cursor: int | None = None) -> dict:
    """Credit transactions, newest first. Real per-generation costs live here.
    Returns {items:[{display_name, credits, action, created_at}], next_cursor}."""
    args: dict = {"size": size}
    if cursor is not None:
        args["cursor"] = cursor
    res = await call("transactions", args, timeout=30)
    return res if isinstance(res, dict) else {"items": res}


async def plans() -> dict:
    """Plans + credits + unlimited entitlements (show_plans_and_credits).
    NB: once on the top plan the API returns plans:[] (only top-ups), so
    parse_unlimited() yields [] for those accounts."""
    return await call("show_plans_and_credits", {"intent": "general"}, timeout=30)


def parse_unlimited(plans_payload: dict) -> list[dict]:
    """Flatten unlimited/free entitlements from a show_plans_and_credits payload
    into [{plan, period, group, model, badges, note}]. Empty when on the top plan."""
    out: list[dict] = []
    for plan in (plans_payload or {}).get("plans") or []:
        pricing = plan.get("pricing") or {}
        for period in ("monthly", "annual"):
            pd = pricing.get(period) or {}
            blocks = [pd.get("unlimitedAccess") or {}]
            blocks.extend((pd.get("customSections") or {}).values())
            for blk in blocks:
                title = (blk or {}).get("title")
                for f in (blk or {}).get("features") or []:
                    out.append({
                        "plan": plan.get("id"), "period": period, "group": title,
                        "model": f.get("text"),
                        "badges": [b.get("label") for b in (f.get("badges") or [])],
                        "note": f.get("tooltip"),
                    })
    seen: set = set()
    uniq: list[dict] = []
    for e in out:
        k = (e["model"], e["group"], e["period"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq


def gen_metadata(tool: str, model_requested: str, job_result: Any,
                 *, credits_spent: float | None = None) -> dict:
    """Stable provenance dict for a Higgsfield generation (SSA-129). Built from a
    job_status result + the model we requested. Studio UI / take-records consume
    this verbatim — keep the keys stable."""
    g = (job_result.get("generation") if isinstance(job_result, dict) else None) or \
        (job_result if isinstance(job_result, dict) else {})
    p = (g or {}).get("params") or {}
    r = (g or {}).get("results") or {}
    urls = find_media_urls(job_result)
    return {
        "provider": "higgsfield",
        "tool": tool,
        "model_requested": model_requested,
        "model_used": (g or {}).get("model") or model_requested,
        "job_id": (g or {}).get("id"),
        "seed": p.get("seed"),
        "prompt": p.get("prompt"),
        "aspect_ratio": p.get("aspect_ratio"),
        "width": p.get("width"),
        "height": p.get("height"),
        "resolution": p.get("resolution"),
        "raw_url": r.get("rawUrl") or (urls[0] if urls else None),
        "thumb_url": r.get("minUrl"),
        "created_at": (g or {}).get("createdAt"),
        # job_status carries no cost; reconcile from transactions(). Web-only
        # "unlimited" never applies to API gens, so this stays False here.
        "credits_spent": credits_spent,
        "unlimited": False,
    }
