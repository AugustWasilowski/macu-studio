#!/usr/bin/env python3
"""On-demand local LLM (Ollama) for the render pipeline — used by translate.py.

Mirrors studio/backend/macu_studio/llm.py (the Studio side) but lives in the pipeline
package so run.py/dub.py can drive qwen without importing across package roots.
Consumer-lifecycle: the container is normally STOPPED (VRAM belongs to ComfyUI during
renders). A translate call does start() -> chat_json() -> stop().
"""
from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request

OLLAMA_CONTAINER = "ollama"
OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b-instruct-q4_K_M"


def start(wait_timeout: int = 180, poll_interval: int = 2) -> None:
    """`docker start` the container and wait until :11434 answers. Idempotent."""
    r = subprocess.run(["docker", "start", OLLAMA_CONTAINER], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"docker start {OLLAMA_CONTAINER} failed: {r.stderr.strip() or r.stdout.strip()}")
    deadline = time.time() + wait_timeout
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 11434), timeout=2):
                pass
        except OSError as e:
            last = e
            time.sleep(poll_interval)
            continue
        try:
            urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3).read()
            return
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(poll_interval)
    raise RuntimeError(f"ollama not ready in {wait_timeout}s (last error: {last!r})")


def stop() -> None:
    """Best-effort `docker stop` to release VRAM. Never raises."""
    subprocess.run(["docker", "stop", "-t", "5", OLLAMA_CONTAINER], capture_output=True, text=True)


def chat_json(messages: list[dict], schema: dict, model: str = DEFAULT_MODEL,
              temperature: float = 0.3, timeout: int = 600) -> dict:
    """POST /api/chat with Ollama structured outputs (`format` = a JSON Schema).
    Returns the parsed JSON object the model produced (schema-constrained)."""
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": schema,
        "options": {"temperature": temperature, "num_ctx": 16384},
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout).read()
    out = json.loads(resp)
    content = (out.get("message") or {}).get("content") or ""
    return json.loads(content)
