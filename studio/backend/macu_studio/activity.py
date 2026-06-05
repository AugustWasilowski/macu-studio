"""A tiny global 'what is the box doing right now' slot for the topbar job indicator.

The render-server jobs and HyperFrames jobs already have their own registries (the
/api/activity aggregator reads those live). This slot only covers the SYNCHRONOUS,
studio-driven GPU jobs that have no registry: agen SFX/music generation and LLM
shot-gen. set_running() while one runs, set_error()/clear() when it ends. Everything
auto-reverts to idle after its TTL so a missed clear() can't pin the indicator.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_slot = {"state": "idle", "label": "", "ts": 0.0, "ttl": 0.0}


def set_running(label: str, ttl: float = 30.0) -> None:
    with _lock:
        _slot.update(state="running", label=label, ts=time.time(), ttl=ttl)


def set_error(label: str, ttl: float = 6.0) -> None:
    with _lock:
        _slot.update(state="error", label=label, ts=time.time(), ttl=ttl)


def clear() -> None:
    with _lock:
        _slot.update(state="idle", label="", ts=time.time(), ttl=0.0)


def get() -> dict:
    with _lock:
        s = dict(_slot)
    if s["state"] != "idle" and s["ttl"] and (time.time() - s["ts"]) > s["ttl"]:
        return {"state": "idle", "label": ""}
    return {"state": s["state"], "label": s["label"]}
