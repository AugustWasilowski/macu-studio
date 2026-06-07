"""script.md read/write."""
from __future__ import annotations
import os, tempfile
from .episodes import episode_dir


def script_path(slug: str):
    return episode_dir(slug) / "script.md"


def read(slug: str) -> dict:
    p = script_path(slug)
    if not p.exists():
        return {"text": "", "mtime": None, "exists": False}
    return {"text": p.read_text(), "mtime": p.stat().st_mtime, "exists": True}


def write(slug: str, text: str) -> dict:
    # Atomic write — script.md is the source the whole pipeline regenerates cues
    # from; a crash/concurrent read mid-write must never leave it half-written.
    p = script_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode()
    fd, tmp = tempfile.mkstemp(prefix=".script.", suffix=".md.tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"mtime": p.stat().st_mtime, "bytes": len(data)}
