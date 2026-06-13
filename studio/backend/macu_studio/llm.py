"""Text generation for the script tools (shot lists, SFX plans, card text).

Two engines, routed by Settings → Engines ("textgen"):
  - ollama_local (default): on-demand local Ollama, consumer-lifecycle like
    OmniVoice — start() -> chat_json() -> stop() (VRAM is shared with renders).
  - claude_cli: the user's own Claude Code CLI run headless (`claude -p`),
    using their Claude subscription. No GPU, no local model download — the
    text half of a "light" install. start()/stop() are no-ops.
Callers keep the same start/chat_json/stop contract either way.
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request

OLLAMA_CONTAINER = "ollama"
OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b-instruct-q4_K_M"


def _engine() -> str:
    try:
        from . import engines
        return engines.route("textgen")
    except Exception:
        return "ollama_local"


def start(wait_timeout: int = 180, poll_interval: int = 2) -> None:
    """`docker start` the container and wait until :11434 answers. Idempotent.
    No-op when textgen is routed to claude_cli."""
    if _engine() == "claude_cli":
        return
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
    if _engine() == "claude_cli":
        return
    subprocess.run(["docker", "stop", "-t", "5", OLLAMA_CONTAINER], capture_output=True, text=True)


def has_model(model: str = DEFAULT_MODEL) -> bool:
    try:
        data = json.loads(urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=5).read())
        names = {m.get("name", "") for m in data.get("models", [])}
        base = model.split(":")[0]
        return model in names or any(n.split(":")[0] == base for n in names if n)
    except Exception:
        return False


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction: strip code fences, find the outermost object."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    start_i, end_i = t.find("{"), t.rfind("}")
    if start_i >= 0 and end_i > start_i:
        return json.loads(t[start_i:end_i + 1])
    raise ValueError(f"no JSON object in claude output: {t[:200]!r}")


def _claude_json(messages: list[dict], schema: dict, timeout: int) -> dict:
    """Run the user's Claude Code CLI headless and parse a schema-shaped JSON
    object out of the reply. Same invocation style as deploy/macu-chat-bridge."""
    from . import engines
    prompt = "\n\n".join(
        (f"[system]\n{m['content']}" if m.get("role") == "system" else m["content"])
        for m in messages
    )
    prompt += ("\n\nReturn ONLY a JSON object matching this JSON Schema — no prose, "
               "no code fences:\n" + json.dumps(schema))
    cbin = engines.claude_path()
    if not cbin:
        raise RuntimeError("claude CLI not found — install Claude Code and sign in, "
                           "or route Script tools back to Ollama in Settings → Engines")
    cmd = [cbin, "-p", "--output-format", "json"]
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       timeout=min(timeout, 600))
    if p.returncode != 0:
        raise RuntimeError(f"claude CLI failed ({p.returncode}): "
                           f"{(p.stderr or p.stdout)[:300]} — is Claude Code signed in?")
    out = json.loads(p.stdout)
    reply = out.get("result") or out.get("text") or ""
    return _extract_json(reply)


def chat_json(messages: list[dict], schema: dict, model: str = DEFAULT_MODEL,
              temperature: float = 0.3, timeout: int = 600) -> dict:
    """Schema-shaped JSON from the routed text engine. Ollama enforces the schema
    via structured outputs; the Claude path instructs + tolerantly parses (callers
    already retry once on failure)."""
    if _engine() == "claude_cli":
        return _claude_json(messages, schema, timeout)
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


def chat_text(messages: list[dict], model: str = DEFAULT_MODEL,
              temperature: float = 0.4, timeout: int = 600, num_ctx: int = 16384) -> str:
    """POST /api/chat and return the raw text the model produced (no JSON schema) —
    for free-form output like generated HTML compositions."""
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout).read()
    out = json.loads(resp)
    return (out.get("message") or {}).get("content") or ""
