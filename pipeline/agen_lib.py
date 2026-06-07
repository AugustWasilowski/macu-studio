"""Shared helpers for the `agen` offline music/SFX acquisition route.

`agen` (`/mnt/storage/audio-gen/agen`) is another GPU consumer (~6 GB for the medium
AudioCraft models on the 11 GB 2080 Ti). It is ephemeral by construction — each call
loads a model, generates, writes a WAV, and exits — but it MUST NOT run concurrently
with ComfyUI stage 2 (zeroscope masters) or OmniVoice stage 1 (the ep6 lowvram
incident). We enforce that with a free-VRAM gate rather than process-name matching:
if the GPU doesn't have enough headroom, a render is almost certainly active, so refuse.
"""
from __future__ import annotations

import os
import subprocess

AGEN = os.environ.get("MACU_AGEN", "/mnt/storage/audio-gen/agen")
MIN_FREE_MIB = 6500  # agen-medium needs ~6 GB; if less is free, a render is likely running


def gpu_free_mib() -> int | None:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return int(r.stdout.strip().splitlines()[0])
    except Exception:
        return None


def ensure_gpu_free(min_mib: int = MIN_FREE_MIB) -> None:
    """Raise RuntimeError if the GPU is too busy to host agen safely."""
    free = gpu_free_mib()
    if free is None:
        print("[agen] WARN: couldn't read GPU free memory; proceeding")
        return
    if free < min_mib:
        raise RuntimeError(
            f"GPU busy: only {free} MiB free (need >= {min_mib}). A render is likely "
            f"active (ComfyUI stage 2 / OmniVoice stage 1) — agen must not run "
            f"concurrently with it. Wait for the render to finish, then retry."
        )


def run_agen(subcmd: str, prompt: str, out: str, duration=None, seed=None, extra=None) -> None:
    """Invoke the agen CLI for one generation (gated on free VRAM)."""
    ensure_gpu_free()
    cmd = [AGEN, subcmd, "-p", prompt, "-o", str(out)]
    if duration is not None:
        cmd += ["-d", str(duration)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if extra:
        cmd += list(extra)
    print("[agen]", " ".join(cmd))
    subprocess.run(cmd, check=True)
