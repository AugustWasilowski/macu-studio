#!/usr/bin/env python3
"""Stage 3: RIFE 3x per master (24f -> 72f).

Idempotent: skips masters whose .rife_frames/<label>_out has the expected count.
Usage: python3 stage_3_rife.py <slug>
"""
import sys, os, glob, subprocess, time, shutil
sys.path.insert(0, os.path.dirname(__file__))
from lib import (episode_paths, load_manifest, ensure_dirs,
                 staged_master_dir, staged_master_webp)

def run(cmd, timeout=900):
    # Per-call cap so a hung RIFE/Vulkan or ffmpeg invocation fails the stage (releasing
    # the render lock) instead of blocking forever. 15 min is far above any real per-clip
    # interpolation/encode time.
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)

def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    n_in = m["comfyui"]["frames"]
    n_out = n_in * 3

    unique = []
    seen = set()
    for cue in m["cues"]:
        for shot in cue["shots"]:
            if shot.get("kind") in ("character","broll"):
                k = (shot["kind"], shot["who"])
                if k not in seen:
                    seen.add(k); unique.append(k)

    todo = []; skipped = 0
    for kind, key in unique:
        out_dir = staged_master_dir(slug, key, kind)
        if os.path.isdir(out_dir) and len(glob.glob(f"{out_dir}/*.png")) >= n_out:
            skipped += 1
            continue
        todo.append((kind, key, out_dir))

    print(f"[stage 3 rife] {len(todo)} to interpolate, {skipped} cached")
    if not todo:
        return {"rendered": 0, "skipped": skipped}

    start = time.time()
    for kind, key, out_dir in todo:
        webp = staged_master_webp(slug, key, kind)
        # Per-key in_dir for the anim_dump
        in_dir = f"{p['rife_frames']}/{key}__in_{kind}"
        if os.path.isdir(in_dir): shutil.rmtree(in_dir)
        if os.path.isdir(out_dir): shutil.rmtree(out_dir)
        os.makedirs(in_dir); os.makedirs(out_dir)
        run(["anim_dump","-prefix","f_","-folder", in_dir, webp])
        run(["rife-ncnn-vulkan",
             "-i", in_dir, "-o", out_dir,
             "-n", str(n_out), "-m", "rife-v4.6", "-j", "1:2:2"])
        produced = len(glob.glob(f"{out_dir}/*.png"))
        print(f"  {key:24} ({kind}) -> {produced}f")
    return {"rendered": len(todo), "skipped": skipped,
            "wall_s": round(time.time()-start, 2)}

if __name__ == "__main__":
    main(sys.argv[1])
