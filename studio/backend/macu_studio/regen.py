"""Single-asset regeneration helpers.

Each helper invalidates the relevant cache file(s), then enqueues a job on the
upstream render service with --only or --from set so the rest of the pipeline
isn't re-run unnecessarily.
"""
from __future__ import annotations
import json, random, shutil
from pathlib import Path

from .episodes import episode_dir
from .manifest import _vo_cache_path
from . import manifest as manifest_mod
from . import pipeline
from . import versions


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
    versions.archive_current(slug, "cue", cue_id)
    if wav.exists():
        wav.unlink()
    _drop_cue_from_vo_cache(slug, cue_id)
    return await pipeline.submit(slug, only=1)


async def regen_shot(slug: str, key: str) -> dict:
    ep = episode_dir(slug)
    versions.archive_current(slug, "shot", key)  # auto-stamps the outgoing seed
    # Shuffle the seed so a regen actually differs. Character masters reuse the
    # fixed seed stored in the manifest, so without this they'd re-render
    # identically; broll already randomizes its seed per-render in stage 2.
    m = manifest_mod.load(slug)
    chars = m.get("characters") or {}
    broll = m.get("broll") or {}
    if isinstance(chars.get(key), dict):
        chars[key]["seed"] = random.randint(1000, 9999)
        manifest_mod.save(slug, m)
    elif isinstance(broll.get(key), dict):
        # Broll in {"prompt","seed"} form carries a fixed seed — shuffle it too.
        # (Plain-string broll has no stored seed; stage 2 randomizes per render.)
        broll[key]["seed"] = random.randint(1000, 9999)
        manifest_mod.save(slug, m)
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
    # Render ONLY the masters stage (stage 2) and stop. Stage 2 skips cached
    # masters, so just the one we deleted above re-renders. We deliberately do
    # NOT run the downstream tail (rife/assemble/music/whisper/srt/burn) — a
    # single-shot regen shouldn't trigger a full episode rebuild. The stale rife
    # frames dropped above get re-interpolated whenever a full render is run.
    return await pipeline.submit(slug, only=2)
