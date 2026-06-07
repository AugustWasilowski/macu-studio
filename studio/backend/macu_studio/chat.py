"""Two-way chat bridge to the always-on Max session via ss-chat-channel.

Flow (mirrors Second Shift's `ss-channel` path, but replies route back to :8774):
  send(slug, msg) → mint request_id → POST to channel :8802 with a reply_url
  pointing at our own /api/chat/reply → long-poll on an asyncio.Event until the
  channel delivers Max's reply (or we time out). The browser keeps its simple
  synchronous `await fetch → data.reply`; the wait happens here, server-side.

The channel pushes the message into the always-on claude session, which calls
its `ss_chat_reply` tool; the channel then POSTs {request_id, text} to our
/api/chat/reply, which calls deliver() to wake the matching long-poll.
"""
from __future__ import annotations
import asyncio
import os
import time
import uuid

import httpx

from .config import CHAT_CHANNEL_URL, CHAT_REPLY_URL, CHAT_WEBHOOK_TOKEN

# The agent can take a while to compose a reply (channel push + reasoning + tool call).
REPLY_TIMEOUT_S = 150.0
_PENDING_TTL_S = 600.0
# Identifies this Studio instance to the channel (cosmetic routing tag).
CHAT_HOST = os.environ.get("MACU_CHAT_HOST", "studio")


class _Pending:
    __slots__ = ("event", "text", "created_at", "slug")

    def __init__(self, slug: str):
        self.event = asyncio.Event()
        self.text: str | None = None
        self.created_at = time.time()
        self.slug = slug


_PENDING: dict[str, _Pending] = {}


def _gc() -> None:
    now = time.time()
    for k, v in list(_PENDING.items()):
        if now - v.created_at > _PENDING_TTL_S:
            _PENDING.pop(k, None)


async def send(slug: str, message: str, session_id: str | None = None) -> dict:
    """POST a user message to the channel and wait for Max's reply.

    Returns {reply, session_id, request_id}. Raises RuntimeError on a transport
    failure and TimeoutError if no reply arrives within REPLY_TIMEOUT_S.
    """
    if not CHAT_WEBHOOK_TOKEN:
        raise RuntimeError(
            "chat bridge not configured: SS_CHAT_WEBHOOK_TOKEN missing "
            "(set the env var or ensure ~/.claude/channels/ss-chat-channel/.env exists)"
        )
    _gc()
    request_id = "macu-" + uuid.uuid4().hex[:12]
    # One conversational thread per episode. The always-on session is a single
    # continuous context, so this is mostly a label that tells Max which episode
    # the operator is talking about; it also keeps Studio turns distinct from the
    # SS dashboard's turns.
    sess = session_id or f"macu-studio:{slug}"

    pending = _Pending(slug)
    _PENDING[request_id] = pending
    body = {
        "request_id": request_id,
        "session_id": sess,
        "text": message,
        "host": CHAT_HOST,
        "reply_url": CHAT_REPLY_URL,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                CHAT_CHANNEL_URL,
                json=body,
                headers={"X-Webhook-Token": CHAT_WEBHOOK_TOKEN},
            )
        if r.status_code != 200:
            raise RuntimeError(f"channel returned {r.status_code}: {r.text[:200]}")
    except RuntimeError:
        _PENDING.pop(request_id, None)
        raise
    except Exception as e:
        # A transport failure (channel down) becomes a RuntimeError so the route maps
        # it to 502 instead of leaking a raw httpx error as a 500.
        _PENDING.pop(request_id, None)
        raise RuntimeError(f"chat channel unreachable: {e}") from e

    try:
        await asyncio.wait_for(pending.event.wait(), timeout=REPLY_TIMEOUT_S)
    except asyncio.TimeoutError:
        _PENDING.pop(request_id, None)
        raise TimeoutError(
            "The agent didn't reply in time — the message was delivered to the session, "
            "but it may be busy. Try again in a moment."
        )
    _PENDING.pop(request_id, None)
    return {"reply": pending.text or "(empty reply)", "session_id": sess, "request_id": request_id}


def deliver(request_id: str, text: str) -> bool:
    """Called by the /api/chat/reply route when the channel POSTs Max's reply.
    Wakes the matching long-poll. Returns False if the request_id is unknown
    (expired or already answered)."""
    pending = _PENDING.get(request_id)
    if not pending:
        return False
    pending.text = text
    pending.event.set()
    return True
