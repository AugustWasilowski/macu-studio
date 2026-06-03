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
