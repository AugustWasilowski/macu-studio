"""Trivial SRT read/write."""
from __future__ import annotations
import re
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
    for e in entries:
        blocks.append(f"{e['i']}\n{e['start']} --> {e['end']}\n{e['text']}\n")
    p.write_text("\n".join(blocks) + "\n")
    return {"mtime": p.stat().st_mtime, "count": len(entries)}
