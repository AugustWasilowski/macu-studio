#!/usr/bin/env python3
"""agen_music.py — generate a music bed with `agen` (MusicGen or Riffusion), normalize
it, and land it in assets/music/ with a provenance catalog row.

MusicGen drifts/loops past ~15–20s and Riffusion is tape-degraded lo-fi — both fit the
zeroscope jank; lean into it. Output (32 kHz music / 44.1 kHz riff, mono) is normalized to
24 kHz mono PCM s16 / −3 dBFS (reusing freesound_fetch.normalize) so manifest `music.gain`
scales predictably; stage 5 random-windows `clip_seconds` out of the clip and resamples in
the amix anyway, so generate >= your `clip_seconds`.

Usage:
  agen_music.py "<prompt>" <basename> [--engine music|riff] [--duration N] [--seed N] [--dest DIR]

Reference the result from manifest.music.clips[] exactly like the existing big-band clips.
De-novo / public-domain; prompt + seed logged for reproducibility.
"""
import argparse
import hashlib
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from freesound_fetch import normalize
import agen_lib
import lib

DEFAULT_DEST = pathlib.Path(lib.ASSETS) / "music"
README_HEADER = """# MACU music beds

Background music beds referenced from `manifest.music.clips[]`; stage 5 random-windows
`clip_seconds` out of each clip, applies `music.gain`, and amix-es them under the episode.

## Catalog

| File | Duration | Source | License | Notes |
|---|---:|---|---|---|
"""


def _probe_dur(p: pathlib.Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
            capture_output=True, text=True, check=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _append_catalog(dest_dir: pathlib.Path, basename: str, dur: float, engine: str, prompt: str, seed: int):
    readme = dest_dir / "README.md"
    if not readme.exists():
        readme.write_text(README_HEADER)
    model = "MusicGen-medium" if engine == "music" else "Riffusion"
    row = (f"| `{basename}.wav` | {dur:.2f}s | **agen {engine}** (MACU-local, {model}) | "
           f"Public Domain (de novo) | prompt: \"{prompt}\" · seed {seed} |\n")
    readme.write_text(readme.read_text().rstrip("\n") + "\n" + row)


def _seed_for(prompt: str, override) -> int:
    if override is not None:
        return int(override)
    return int(hashlib.sha256(prompt.encode()).hexdigest(), 16) % 100000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("basename")
    ap.add_argument("--engine", choices=["music", "riff"], default="music")
    ap.add_argument("--duration", type=float, default=20.0)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    args = ap.parse_args()

    dest_dir = pathlib.Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / f"{args.basename}.wav"
    if out_path.exists():
        print(f"already exists: {out_path}")
        return 0

    seed = _seed_for(args.prompt, args.seed)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = pathlib.Path(tmp.name)
    try:
        try:
            agen_lib.run_agen(args.engine, args.prompt, tmp_path, duration=args.duration, seed=seed)
        except RuntimeError as e:
            print(f"[agen_music] {e}")
            return 4  # GPU busy
        normalize(tmp_path, out_path)
        dur = _probe_dur(out_path)
        _append_catalog(dest_dir, args.basename, dur, args.engine, args.prompt, seed)
        print(f"wrote {out_path} ({dur:.2f}s, {args.engine}, seed {seed})")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
