"""Single-asset regeneration helpers.

Each helper invalidates the relevant cache file(s), then enqueues a job on the
upstream render service with --only or --from set so the rest of the pipeline
isn't re-run unnecessarily.
"""
from __future__ import annotations
import json, shutil
from pathlib import Path

from .episodes import episode_dir
from .manifest import _vo_cache_path
from . import pipeline


def _drop_cue_from_vo_cache(slug: str, cue_id: str) -> None:
    p = _vo_cache_path(slug)
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text())
    except Exception:
        return
    if cue_id in data:
        data.pop(cue_id, None)
        p.write_text(json.dumps(data, indent=2))


async def regen_cue(slug: str, cue_id: str) -> dict:
    ep = episode_dir(slug)
    wav = ep / "vo" / f"{cue_id}.wav"
    if wav.exists():
        wav.unlink()
    _drop_cue_from_vo_cache(slug, cue_id)
    return await pipeline.submit(slug, only=1)


async def regen_shot(slug: str, key: str) -> dict:
    ep = episode_dir(slug)
    # Be thorough — both character and broll path conventions
    candidates: list[Path] = [
        ep / "clips" / f"{key}_master.zs.webp",
        ep / "clips" / f"safe_master.zs.webp" if key == "safe" else None,
        ep / "clips" / f"broll_{key}.zs.webp",
        ep / "clips" / f"c09_s1.zs.webp" if key == "empty_room" else None,
    ]
    for c in candidates:
        if c and c.exists():
            c.unlink()
    rife = ep / ".rife_frames"
    if rife.exists():
        for d in rife.iterdir():
            if d.is_dir() and (d.name == f"{key}_master_out" or d.name.startswith(f"broll_{key}_") or (key == "empty_room" and d.name == "c09_s1_out")):
                shutil.rmtree(d, ignore_errors=True)
    return await pipeline.submit(slug, from_stage=2)
