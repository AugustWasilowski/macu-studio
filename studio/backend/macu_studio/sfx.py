"""SFX fetch — wraps the existing freesound_fetch.py CLI."""
from __future__ import annotations
import asyncio, json, re, shutil
from pathlib import Path

from .config import PIPELINE, SHARES
from .episodes import episode_dir
from . import manifest as manifest_mod


FETCH_SCRIPT = PIPELINE / "freesound_fetch.py"
SFX_DIR = SHARES / "assets" / "sfx"


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower())
    return s.strip("_")[:32] or "sfx"


async def fetch_and_pin(
    slug: str,
    query: str,
    cue_id: str | None,
    at: str = "start",
    duration_max: float = 4.0,
    basename: str | None = None,
    gain_db: float = -6.0,
    fade_s: float = 0.5,
    license_mode: str = "cc0",
) -> dict:
    """Run freesound_fetch.py, then append an entry to manifest.sfx[]."""
    if not FETCH_SCRIPT.exists():
        raise FileNotFoundError(f"freesound_fetch.py not found at {FETCH_SCRIPT}")

    # Always slugify — a caller-supplied basename must not escape SFX_DIR (it lands
    # in the filesystem and in manifest.sfx[]). _slugify strips to [a-z0-9_].
    basename = _slugify(basename or query)
    cmd = [
        "python3", str(FETCH_SCRIPT),
        query, basename,
        "--duration-max", str(duration_max),
        "--license", license_mode,
        "--dest", str(SFX_DIR),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    out = stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        return {
            "ok": False,
            "returncode": proc.returncode,
            "log": out,
            "hint": (
                "rc=2 means no CC0 match under the duration cap; try a longer cap "
                "or set license=all. rc=3 means missing/invalid Freesound API key."
            ),
        }

    out_path = SFX_DIR / f"{basename}.wav"
    if not out_path.exists():
        # may have landed as mp3 with --no-normalize, but we don't pass that
        # so any non-error returning is suspect — surface the log
        return {"ok": False, "returncode": proc.returncode, "log": out, "hint": "expected wav not found"}

    # Append to manifest.sfx[]. NOTE: file is the bare basename (no "sfx/" prefix) —
    # stage_5_music.py resolves it as <assets/sfx>/<file>, per assets/sfx/README.md.
    m = manifest_mod.load(slug)
    entry = {
        "file": f"{basename}.wav",
        "cue": cue_id,
        "at": at,
        "gain": gain_db,
        "fade": fade_s,
        "query": query,
    }
    sfx = m.get("sfx")
    if not isinstance(sfx, list):
        sfx = []
    sfx.append(entry)
    m["sfx"] = sfx
    manifest_mod.save(slug, m)

    return {
        "ok": True,
        "log": out,
        "entry": entry,
        "wav_path": str(out_path),
    }


def remove(slug: str, file_path: str) -> dict:
    """Drop an SFX entry from manifest.sfx[] by exact file match. Does NOT delete the wav."""
    m = manifest_mod.load(slug)
    sfx = m.get("sfx") or []
    new = [s for s in sfx if s.get("file") != file_path]
    m["sfx"] = new
    manifest_mod.save(slug, m)
    return {"removed": len(sfx) - len(new), "remaining": len(new)}
