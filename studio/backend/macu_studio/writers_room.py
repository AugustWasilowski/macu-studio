"""Fire-and-forget 'send to writers' room' bridge.

Unlike `chat.send()` (which long-polls 150s for a reply), the writers'-room is
an agent-driven, multi-minute critique loop run by Max's always-on session. So
we just POST a request to the channel and return immediately; Max runs the
writers'-room critique skill on the episode's script and writes the synthesized
notes to `episodes/<slug>/writers_room.md`. The UI polls for that file.
"""
from __future__ import annotations
import uuid

import httpx

from .episodes import episode_dir
from . import config


def NOTES(slug: str):
    return episode_dir(slug) / "writers_room.md"


def _script_text(slug: str) -> str:
    p = episode_dir(slug) / "script.md"
    return p.read_text() if p.exists() else ""


async def kick(slug: str) -> dict:
    """POST a fire-and-forget writers'-room request to Max's always-on session.

    Does NOT wait for a reply — Max writes writers_room.md asynchronously and the
    UI polls read_notes() for it. The short timeout only covers the POST handshake;
    transport timeouts are swallowed (the work continues on Max's side)."""
    if not config.CHAT_WEBHOOK_TOKEN:
        raise RuntimeError(
            "chat bridge not configured: SS_CHAT_WEBHOOK_TOKEN missing "
            "(set the env var or ensure ~/.claude/channels/ss-chat-channel/.env exists)"
        )

    script = _script_text(slug)
    script_path = str(episode_dir(slug) / "script.md")
    notes_path = str(episode_dir(slug) / "writers_room.md")
    text = (
        f"[writers' room] Run the writers'-room critique pass (the comedy-writers-room "
        f"skill / the macu-report writers'-room pass) on MACU episode '{slug}'. "
        f"The script is at {script_path}. Synthesize the room's notes and write them "
        f"to {notes_path} as markdown. This is fire-and-forget — no reply needed; the "
        f"Studio UI polls for writers_room.md.\n\n"
        f"--- script.md ---\n{script}"
    )

    request_id = "macu-wr-" + uuid.uuid4().hex[:12]
    body = {
        "request_id": request_id,
        "session_id": f"macu-writers:{slug}",
        "text": text,
        "host": "plex",
        # No reply_url: fire-and-forget, we don't block on a callback.
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                config.CHAT_CHANNEL_URL,
                json=body,
                headers={"x-webhook-token": config.CHAT_WEBHOOK_TOKEN},
            )
        if r.status_code != 200:
            print(f"[writers-room] channel returned {r.status_code}: {r.text[:200]}")
    except Exception as e:
        # The handshake may time out while Max is busy; the work still runs.
        print(f"[writers-room] POST handshake failed (work continues async): {e}")

    return {"ok": True, "queued": True}


def read_notes(slug: str) -> dict:
    p = NOTES(slug)
    if not p.exists():
        return {"text": "", "mtime": None, "exists": False}
    return {"text": p.read_text(), "mtime": p.stat().st_mtime, "exists": True}
