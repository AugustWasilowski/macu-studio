"""Browsable library of generated audio assets (assets/sfx + assets/music).

Powers the Audio-page library table: list files with catalog metadata + a numeric
duration (for SFX delay-sequencing) and stream them for preview.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import SHARES

KINDS = {
    "sfx": SHARES / "assets" / "sfx",
    "music": SHARES / "assets" / "music",
}
_AUDIO_EXT = (".wav", ".mp3")
_DUR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*s", re.I)


def _parse_catalog(readme: Path) -> dict[str, dict]:
    """Parse the README markdown catalog: | File | Duration | Source | License | Notes |."""
    out: dict[str, dict] = {}
    if not readme.exists():
        return out
    for line in readme.read_text().splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5:
            continue
        fname = cells[0].strip().strip("`")
        if not fname.lower().endswith(_AUDIO_EXT):
            continue
        out[fname] = {
            "duration": cells[1],
            "source": cells[2].replace("**", ""),
            "license": cells[3],
            "notes": cells[4],
        }
    return out


def _probe_dur(p: Path) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
            capture_output=True, text=True, timeout=5,
        )
        return round(float(r.stdout.strip()), 2)
    except Exception:
        return None


def list_assets(kind: str) -> list[dict]:
    d = KINDS.get(kind)
    if not d or not d.exists():
        return []
    cat = _parse_catalog(d / "README.md")
    out: list[dict] = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix.lower() not in _AUDIO_EXT:
            continue
        meta = cat.get(f.name, {})
        # Prefer the catalog duration string (cheap); ffprobe only when missing.
        dur_s: float | None = None
        mdur = meta.get("duration")
        if mdur:
            mm = _DUR_RE.search(mdur)
            if mm:
                dur_s = round(float(mm.group(1)), 2)
        if dur_s is None:
            dur_s = _probe_dur(f)
        out.append({
            "file": f.name,
            "duration_s": dur_s,
            "source": meta.get("source"),
            "license": meta.get("license"),
            "notes": meta.get("notes"),
        })
    return out


def asset_path(kind: str, file: str) -> Path | None:
    """Resolve a library file with a strict basename sanitize."""
    d = KINDS.get(kind)
    if not d:
        return None
    if "/" in file or "\\" in file or ".." in file:
        return None
    if not file.lower().endswith(_AUDIO_EXT):
        return None
    p = d / file
    return p if p.exists() else None
