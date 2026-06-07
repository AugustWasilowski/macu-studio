#!/usr/bin/env python3
"""Minimal MACU chat bridge — Studio's chat tile / writers' room <-> Claude Code.

Speaks the exact protocol Studio's chat.py uses (POST {request_id, session_id,
text, reply_url} + an X-Webhook-Token header to :8802), but instead of the full
Second Shift always-on-channels rig it just runs **`claude -p` headless** per
message and POSTs the reply back to reply_url. Portable: the only dependency is
the `claude` CLI, logged in as the user running this. stdlib-only.

Per Studio session_id (e.g. "macu-studio:awb-001") it keeps a Claude session and
`--resume`s it, so each episode's chat is one continuous conversation.

Security: this hands any caller a tool-enabled `claude` session, so it FAILS
CLOSED — with no token set, every POST is refused (503). Set SS_CHAT_WEBHOOK_TOKEN
(via /setup-macu-channel) to enable it, or set MACU_CHAT_BRIDGE_ALLOW_NO_AUTH=1 to
deliberately run tokenless on a trusted loopback. Even with a token, scope what the
session can do with MACU_CLAUDE_ALLOWED_TOOLS / MACU_CLAUDE_PERMISSION_MODE. Binds
127.0.0.1 only — never expose it off-box.

Config (env, or ~/.claude/channels/ss-chat-channel/.env — same file Studio reads):
  SS_CHAT_WEBHOOK_TOKEN         shared secret; POSTs without a matching token are
                               rejected. With no token the bridge refuses all POSTs.
  MACU_CHAT_BRIDGE_ALLOW_NO_AUTH=1   opt out of the token requirement (trusted LAN only)
  MACU_CHAT_BRIDGE_PORT         default 8802
  MACU_CLAUDE_BIN               default "claude"
  MACU_CLAUDE_ALLOWED_TOOLS     optional --allowedTools allowlist (e.g. "Read,Edit,Bash")
  MACU_CLAUDE_PERMISSION_MODE   optional --permission-mode (e.g. "acceptEdits")
"""
import json, os, subprocess, threading, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

CHANNEL_ENV = Path.home() / ".claude" / "channels" / "ss-chat-channel" / ".env"


def _token() -> str:
    t = os.environ.get("SS_CHAT_WEBHOOK_TOKEN", "").strip()
    if t:
        return t
    if CHANNEL_ENV.exists():
        for line in CHANNEL_ENV.read_text().splitlines():
            s = line.strip()
            if s.startswith("SS_CHAT_WEBHOOK_TOKEN="):
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


TOKEN = _token()
ALLOW_NO_AUTH = _truthy(os.environ.get("MACU_CHAT_BRIDGE_ALLOW_NO_AUTH", ""))
PORT = int(os.environ.get("MACU_CHAT_BRIDGE_PORT", "8802"))
CLAUDE = os.environ.get("MACU_CLAUDE_BIN", "claude")
ALLOWED_TOOLS = os.environ.get("MACU_CLAUDE_ALLOWED_TOOLS", "").strip()
PERMISSION_MODE = os.environ.get("MACU_CLAUDE_PERMISSION_MODE", "").strip()
SESS_FILE = Path.home() / ".macu-chat-bridge-sessions.json"
_lock = threading.Lock()


def _sessions() -> dict:
    try:
        return json.loads(SESS_FILE.read_text())
    except Exception:
        return {}


def _remember(studio_sid: str, claude_sid: str) -> None:
    with _lock:
        s = _sessions(); s[studio_sid] = claude_sid
        try:
            SESS_FILE.write_text(json.dumps(s))
        except Exception:
            pass


def _ask_claude(text: str, studio_sid: str) -> str:
    """Run claude headless, resuming the per-session Claude conversation."""
    csid = _sessions().get(studio_sid)
    cmd = [CLAUDE]
    if csid:
        cmd += ["--resume", csid]
    cmd += ["-p", "--output-format", "json"]
    if PERMISSION_MODE:
        cmd += ["--permission-mode", PERMISSION_MODE]
    if ALLOWED_TOOLS:
        cmd += ["--allowedTools", ALLOWED_TOOLS]
    try:
        p = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=140)
    except Exception as e:  # noqa: BLE001
        return f"(bridge error running claude: {e})"
    try:
        out = json.loads(p.stdout)
        reply = out.get("result") or out.get("text") or ""
        new = out.get("session_id")
        if new:
            _remember(studio_sid, new)
        return reply or "(empty reply)"
    except Exception:
        # Non-JSON (e.g. a CLI error) — surface stdout/stderr so it's debuggable.
        return (p.stdout or p.stderr or "(no output from claude)").strip()


def _process(body: dict) -> None:
    text = body.get("text", "")
    rid = body.get("request_id")
    sid = body.get("session_id", "default")
    reply_url = body.get("reply_url")
    reply = _ask_claude(text, sid)
    if reply_url and rid:
        data = json.dumps({"request_id": rid, "text": reply}).encode()
        req = urllib.request.Request(
            reply_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=20).read()
        except Exception as e:  # noqa: BLE001
            print(f"[bridge] reply POST to {reply_url} failed: {e}")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "claude": CLAUDE, "auth": bool(TOKEN)})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        # Fail closed: a tokenless bridge refuses everything unless explicitly opted out.
        if not TOKEN:
            if not ALLOW_NO_AUTH:
                self._json(503, {"error": "bridge not configured: set SS_CHAT_WEBHOOK_TOKEN "
                                          "(run /setup-macu-channel) or MACU_CHAT_BRIDGE_ALLOW_NO_AUTH=1"}); return
        elif self.headers.get("X-Webhook-Token") != TOKEN:
            self._json(401, {"error": "bad token"}); return
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n))
        except Exception:
            self._json(400, {"error": "bad json"}); return
        # Ack immediately; the (slow) claude call + reply happen in the background,
        # mirroring the channel — Studio long-polls its own reply_url for the answer.
        self._json(200, {"ok": True})
        threading.Thread(target=_process, args=(body,), daemon=True).start()

    def _json(self, code: int, obj: dict):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    if not TOKEN:
        if ALLOW_NO_AUTH:
            print("[bridge] WARNING: no SS_CHAT_WEBHOOK_TOKEN — running UNAUTHENTICATED "
                  "(MACU_CHAT_BRIDGE_ALLOW_NO_AUTH=1). Any local process can drive a "
                  "tool-enabled Claude session. Trusted loopback only.")
        else:
            print("[bridge] no SS_CHAT_WEBHOOK_TOKEN set — POSTs will be REFUSED (503). "
                  "Run /setup-macu-channel to set a token, or set "
                  "MACU_CHAT_BRIDGE_ALLOW_NO_AUTH=1 to run tokenless on a trusted LAN.")
    print(f"[bridge] macu-chat-bridge listening on 127.0.0.1:{PORT}  (claude={CLAUDE}, "
          f"auth={bool(TOKEN)}, tools={ALLOWED_TOOLS or 'all'})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
