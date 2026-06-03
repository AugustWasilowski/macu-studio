"""script.md read/write."""
from __future__ import annotations
from .episodes import episode_dir


def script_path(slug: str):
    return episode_dir(slug) / "script.md"


def read(slug: str) -> dict:
    p = script_path(slug)
    if not p.exists():
        return {"text": "", "mtime": None, "exists": False}
    return {"text": p.read_text(), "mtime": p.stat().st_mtime, "exists": True}


def write(slug: str, text: str) -> dict:
    p = script_path(slug)
    p.write_text(text)
    return {"mtime": p.stat().st_mtime, "bytes": len(text.encode())}
