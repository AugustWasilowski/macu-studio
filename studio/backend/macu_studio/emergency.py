"""Emergency stop — kill the active render, clear the ComfyUI queue, free GPU memory.

One button on the dashboard calls stop_all():
  1. macu-render `/kill` — SIGTERM/SIGKILL the running render job's process group
     (run.py + its ffmpeg/rife children) and mark it errored so the render lock clears.
  2. ComfyUI — `/interrupt` the in-flight job, `/queue {clear}` the pending ones, and
     `/free {unload_models, free_memory}` to release VRAM (the service stays up).
  3. Stop the consumer-lifecycle GPU containers (ollama, omnivoice) to free their VRAM.
Best-effort throughout: each step is independent and reported, so one failure doesn't
block the rest.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request

from .config import RENDER_URL

COMFY_URL = "http://127.0.0.1:8188"
GPU_CONTAINERS = ("ollama", "omnivoice")


def _post(url: str, payload: dict | None = None, timeout: int = 10) -> str:
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def stop_all() -> dict:
    report: dict[str, str] = {}

    # 1. kill the active render job (whole process tree)
    try:
        _post(RENDER_URL + "/kill", {})
        report["render"] = "killed"
    except Exception as e:  # noqa: BLE001
        report["render"] = f"err: {e}"

    # 2. stop ComfyUI work + free its VRAM (keep the service running)
    for path, payload, label in (
        ("/interrupt", {}, "comfy_interrupt"),
        ("/queue", {"clear": True}, "comfy_queue_clear"),
        ("/free", {"unload_models": True, "free_memory": True}, "comfy_free"),
    ):
        try:
            _post(COMFY_URL + path, payload)
            report[label] = "ok"
        except Exception as e:  # noqa: BLE001
            report[label] = f"err: {e}"

    # 3. unload the on-demand GPU containers
    for c in GPU_CONTAINERS:
        try:
            r = subprocess.run(["docker", "stop", "-t", "5", c], capture_output=True, text=True, timeout=30)
            report[f"stop_{c}"] = "stopped" if r.returncode == 0 else f"err: {(r.stderr or r.stdout).strip()[:120]}"
        except Exception as e:  # noqa: BLE001
            report[f"stop_{c}"] = f"err: {e}"

    return report
