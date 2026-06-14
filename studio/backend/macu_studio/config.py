import os
from pathlib import Path

# Load a single repo-root .env so the backend + pipeline share one machine-config
# file. Must run BEFORE the os.environ.get calls below. No-op on Max (no .env
# present) → every default below keeps its current Max value. dotenv defaults to
# override=False, so systemd Environment= lines still win.
_REPO_ROOT = Path(__file__).resolve().parents[3]
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ModuleNotFoundError:
    pass

SHARES = Path(os.environ.get("MACU_SHARES", "/mnt/storage/shares/MACU"))
EPISODES = Path(os.environ.get("MACU_EPISODES", str(SHARES / "episodes")))
PIPELINE = Path(os.environ.get("MACU_PIPELINE", str(SHARES / "pipeline")))
RENDER_URL = os.environ.get("MACU_RENDER_URL", "http://127.0.0.1:8773").rstrip("/")

STUDIO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = STUDIO_ROOT / "frontend" / "dist"

# The macu-studio repo root (studio/ lives inside it). `docs/` is the canon dir.
REPO_ROOT = STUDIO_ROOT.parent

# Bind loopback by default — Studio has no auth, so a 0.0.0.0 bind exposes every
# write/render endpoint to anyone on your network. Set MACU_STUDIO_HOST=0.0.0.0 to
# reach it from another machine on a trusted LAN.
HOST = os.environ.get("MACU_STUDIO_HOST", "127.0.0.1")
PORT = int(os.environ.get("MACU_STUDIO_PORT", "8774"))

# Public base URL for building ABSOLUTE asset URLs (character take + episode still
# images) that a REMOTE MCP client (e.g. headless Leo) can fetch directly. Empty →
# emit relative paths so the client prepends the Studio host it's already talking to.
# e.g. http://10.0.0.245:8774  or  https://studio.mayorawesome.com
PUBLIC_BASE = os.environ.get("MACU_STUDIO_PUBLIC_URL", "").rstrip("/")


def asset_url(path: str) -> str:
    """Absolute URL if MACU_STUDIO_PUBLIC_URL is set, else the relative `path`
    (the caller already knows which Studio host it connected to)."""
    return f"{PUBLIC_BASE}{path}" if PUBLIC_BASE else path

CORS_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
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


# ---- YouTube Data API v3 (landing page) ----
# Env vars win; else read ~/.config/macu-studio/youtube.json
# ({"api_key": ..., "channel_id": ...}). Both default to empty strings, in
# which case the YouTube landing page degrades to "not configured".
def _load_youtube_creds() -> tuple[str, str]:
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
    if api_key and channel_id:
        return api_key, channel_id
    cfg = Path.home() / ".config" / "macu-studio" / "youtube.json"
    if cfg.exists():
        try:
            import json
            data = json.loads(cfg.read_text())
            api_key = api_key or str(data.get("api_key") or "").strip()
            channel_id = channel_id or str(data.get("channel_id") or "").strip()
        except Exception:
            pass
    return api_key, channel_id


YOUTUBE_API_KEY, YOUTUBE_CHANNEL_ID = _load_youtube_creds()
