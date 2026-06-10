"""Global server-event feed for toasts + the topbar.

A tiny thread-safe ring buffer of {seq, ts, kind, level, label} events plus an SSE
generator. Anything the box does that a human would want a toast for — HyperFrames
jobs, agen/LLM activity, mutating MCP/API calls — emit()s here; the frontend
subscribes once to GET /api/events/stream. The stream is poll-based (0.5s) so
emitters never need the asyncio loop: emit() works from threads and sync code alike.

Fresh subscribers only receive events newer than their connect time (or pass
?since=<seq> to resume after a reconnect — the browser sends Last-Event-ID
semantics via the id: field).
"""
from __future__ import annotations

import asyncio
import itertools
import json
import threading
import time
from collections import deque

_lock = threading.Lock()
_buf: deque[dict] = deque(maxlen=200)
_seq = itertools.count(1)

LEVELS = ("info", "running", "success", "error")


def emit(kind: str, label: str, level: str = "info") -> None:
    """Record one event. kind is the source ("hf", "mcp", "job"); label is the
    human line the toast shows; level maps to the toast color."""
    if level not in LEVELS:
        level = "info"
    with _lock:
        _buf.append({"seq": next(_seq), "ts": time.time(),
                     "kind": kind, "level": level, "label": label})


async def stream(since: int = 0):
    """SSE generator: yields events newer than `since` (default: only NEW events
    from connect time onward), with periodic keepalive comments."""
    with _lock:
        newest = _buf[-1]["seq"] if _buf else 0
    last = since if since > 0 else newest
    yield ": connected\n\n"
    quiet = 0.0
    while True:
        out = []
        with _lock:
            for ev in _buf:
                if ev["seq"] > last:
                    out.append(ev)
        for ev in out:
            last = ev["seq"]
            yield f"id: {ev['seq']}\ndata: {json.dumps(ev)}\n\n"
        if out:
            quiet = 0.0
        else:
            quiet += 0.5
            if quiet >= 15.0:
                yield ": keepalive\n\n"
                quiet = 0.0
        await asyncio.sleep(0.5)
