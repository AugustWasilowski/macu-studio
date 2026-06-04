import os
from pathlib import Path

SHARES = Path(os.environ.get("MACU_SHARES", "/mnt/storage/shares/MACU"))
EPISODES = Path(os.environ.get("MACU_EPISODES", str(SHARES / "episodes")))
PIPELINE = Path(os.environ.get("MACU_PIPELINE", str(SHARES / "pipeline")))
RENDER_URL = os.environ.get("MACU_RENDER_URL", "http://127.0.0.1:8773").rstrip("/")

STUDIO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = STUDIO_ROOT / "frontend" / "dist"

HOST = os.environ.get("MACU_STUDIO_HOST", "0.0.0.0")
PORT = int(os.environ.get("MACU_STUDIO_PORT", "8774"))

CORS_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://10.0.0.245:5173",
]

# ---- Chat bridge (ss-chat-channel → always-on Max session) ----
# Studio POSTs user messages to the channel server, which pushes them into the
# always-on ss-channels claude session; the reply comes back to CHAT_REPLY_URL.
CHAT_CHANNEL_URL = os.environ.get("MACU_CHAT_CHANNEL_URL", "http://localhost:8802/").rstrip("/") + "/"
CHAT_REPLY_URL = os.environ.get("MACU_CHAT_REPLY_URL", f"http://localhost:{PORT}/api/chat/reply")


def _load_chat_token() -> str:
    """Token shared with ss-chat-channel. Env var wins; else read the channel's
    own .env so Studio and the channel stay in sync without manual copying."""
    t = os.environ.get("SS_CHAT_WEBHOOK_TOKEN", "").strip()
    if t:
        return t
    env_file = Path.home() / ".claude" / "channels" / "ss-chat-channel" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            s = line.strip()
            if s.startswith("SS_CHAT_WEBHOOK_TOKEN="):
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


CHAT_WEBHOOK_TOKEN = _load_chat_token()
