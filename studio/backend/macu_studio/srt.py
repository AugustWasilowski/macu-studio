"""Trivial SRT read/write."""
from __future__ import annotations
import os, re, tempfile
from pathlib import Path

from .episodes import episode_dir


SRT_BLOCK = re.compile(
    r"(\d+)\s*\n([\d:,]+)\s*-->\s*([\d:,]+)\s*\n(.*?)(?:\n\n|\Z)",
    re.DOTALL,
)


def srt_path(slug: str) -> Path:
    return episode_dir(slug) / "final" / f"{slug}.srt"


def read(slug: str) -> dict:
    p = srt_path(slug)
    if not p.exists():
        return {"text": "", "entries": [], "exists": False}
    text = p.read_text()
    entries = []
    for m in SRT_BLOCK.finditer(text):
        entries.append({
            "i": int(m.group(1)),
            "start": m.group(2).strip(),
            "end": m.group(3).strip(),
            "text": m.group(4).strip(),
        })
    return {"text": text, "entries": entries, "exists": True}


def write(slug: str, entries: list[dict]) -> dict:
    p = srt_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for idx, e in enumerate(entries, 1):
        if not isinstance(e, dict):
            raise ValueError(f"SRT entry {idx} is not an object")
        i = e.get("i", idx)
        start, end = e.get("start"), e.get("end")
        if not start or not end:
            raise ValueError(f"SRT entry {idx} missing start/end")
        blocks.append(f"{i}\n{start} --> {end}\n{e.get('text', '')}\n")
    body = ("\n".join(blocks) + "\n").encode()
    # Atomic write so a bad/concurrent write can't truncate the SRT.
    fd, tmp = tempfile.mkstemp(prefix=".srt.", suffix=".srt.tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"mtime": p.stat().st_mtime, "count": len(entries)}
