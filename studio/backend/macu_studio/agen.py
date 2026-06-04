"""agen — generate SFX one-shots + music beds with the local `agen` CLI.

A third SFX acquisition route (alongside freesound + ffmpeg synth) and a music-bed
generator. Shells the pipeline helpers `agen_sfx.py` / `agen_music.py`, which gate on
free VRAM (agen must not run during ComfyUI stage 2 / OmniVoice stage 1 — the ep6
lowvram incident). We also pre-check here so the UI gets a fast, clear 409 if a render
is active rather than waiting on a doomed generation.
"""
from __future__ import annotations

import asyncio
import re
import subprocess

from .config import PIPELINE, SHARES
from . import manifest as manifest_mod
from .sfx import _slugify, SFX_DIR

AGEN_SFX = PIPELINE / "agen_sfx.py"
AGEN_MUSIC = PIPELINE / "agen_music.py"
MUSIC_DIR = SHARES / "assets" / "music"
MIN_FREE_MIB = 6500  # keep in sync with pipeline/agen_lib.py


def gpu_free_mib() -> int | None:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return None


def gpu_busy() -> tuple[bool, int | None]:
    free = gpu_free_mib()
    if free is None:
        return False, None  # can't tell → let the helper's own guard decide
    return free < MIN_FREE_MIB, free


async def _run(cmd: list[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode, stdout.decode("utf-8", errors="replace")


def _parse_seed(log: str) -> int | None:
    m = re.search(r"seed (\d+)", log)
    return int(m.group(1)) if m else None


async def gen_sfx_and_pin(
    slug: str, prompt: str, cue_id: str | None, at: str = "start",
    duration: float = 3.0, seed: int | None = None, basename: str | None = None,
    gain_db: float = -6.0, fade_s: float = 0.5,
) -> dict:
    if not AGEN_SFX.exists():
        raise FileNotFoundError(f"agen_sfx.py not found at {AGEN_SFX}")
    busy, free = gpu_busy()
    if busy:
        return {"ok": False, "busy": True, "gpu_free_mib": free,
                "hint": f"GPU busy ({free} MiB free) — a render is active; agen can't run now."}
    basename = basename or _slugify(prompt)
    cmd = ["python3", str(AGEN_SFX), prompt, basename,
           "--duration", str(duration), "--dest", str(SFX_DIR)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    rc, log = await _run(cmd)
    if rc == 4:
        return {"ok": False, "busy": True, "log": log,
                "hint": "GPU became busy mid-request (render started). Retry when idle."}
    out_path = SFX_DIR / f"{basename}.wav"
    if rc != 0 or not out_path.exists():
        return {"ok": False, "returncode": rc, "log": log, "hint": "agen generation failed"}

    m = manifest_mod.load(slug)
    entry = {
        "file": f"{basename}.wav",
        "cue": cue_id, "at": at, "gain": gain_db, "fade": fade_s,
        "prompt": prompt, "seed": _parse_seed(log), "source": "agen",
    }
    sfx = m.get("sfx")
    if not isinstance(sfx, list):
        sfx = []
    sfx.append(entry)
    m["sfx"] = sfx
    manifest_mod.save(slug, m)
    return {"ok": True, "log": log, "entry": entry, "wav_path": str(out_path)}


async def gen_music(
    slug: str, prompt: str, engine: str = "music", duration: float = 20.0,
    seed: int | None = None, basename: str | None = None, add_to_clips: bool = True,
) -> dict:
    if not AGEN_MUSIC.exists():
        raise FileNotFoundError(f"agen_music.py not found at {AGEN_MUSIC}")
    if engine not in ("music", "riff"):
        return {"ok": False, "hint": "engine must be 'music' or 'riff'"}
    busy, free = gpu_busy()
    if busy:
        return {"ok": False, "busy": True, "gpu_free_mib": free,
                "hint": f"GPU busy ({free} MiB free) — a render is active; agen can't run now."}
    basename = basename or _slugify(prompt)
    cmd = ["python3", str(AGEN_MUSIC), prompt, basename,
           "--engine", engine, "--duration", str(duration), "--dest", str(MUSIC_DIR)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    rc, log = await _run(cmd)
    if rc == 4:
        return {"ok": False, "busy": True, "log": log}
    out_path = MUSIC_DIR / f"{basename}.wav"
    if rc != 0 or not out_path.exists():
        return {"ok": False, "returncode": rc, "log": log, "hint": "agen music generation failed"}

    added = False
    if add_to_clips:
        m = manifest_mod.load(slug)
        music = m.get("music")
        if not isinstance(music, dict):
            music = {}
        clips = music.get("clips")
        if not isinstance(clips, list):
            clips = []
        fname = f"{basename}.wav"
        if fname not in clips:
            clips.append(fname)
            added = True
        music["clips"] = clips
        # Point source_dir at the generated-bed dir if it isn't set to a music dir already.
        music.setdefault("source_dir", str(MUSIC_DIR))
        m["music"] = music
        manifest_mod.save(slug, m)
    return {"ok": True, "log": log, "file": f"{basename}.wav",
            "wav_path": str(out_path), "added_to_clips": added, "seed": _parse_seed(log)}
