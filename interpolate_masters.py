#!/usr/bin/env python3
"""Interpolate all 12 master webps 3x via rife-ncnn-vulkan.

For each master:
  webp → anim_dump → in_dir/f_NNNN.png (24 frames)
  rife-ncnn-vulkan -i in_dir -o out_dir -n 72 -m rife-v4.6 -j 1:2:2
  → 72 PNGs in out_dir

The assembler will pick these up by looking for clips/<name>.rife/ (a dir)
in addition to clips/<name>.zs.webp."""
import os, subprocess, time, glob, shutil

CLIPS = "/mnt/storage/shares/MACU/episodes/ep5/clips"
RIFE_FRAMES = "/mnt/storage/shares/MACU/episodes/ep5/.rife_frames"
os.makedirs(RIFE_FRAMES, exist_ok=True)

MASTERS = [
    # (label, src_webp)
    ("safe_master",    f"{CLIPS}/safe_master.zs.webp"),
    ("c09_s1",         f"{CLIPS}/c09_s1.zs.webp"),  # empty_room broll
    ("ron_master",     f"{CLIPS}/ron_master.zs.webp"),
    ("walter_master",  f"{CLIPS}/walter_master.zs.webp"),
    ("marigold_master",f"{CLIPS}/marigold_master.zs.webp"),
    ("tally_man_master", f"{CLIPS}/tally_man_master.zs.webp"),
    ("vendor_master",  f"{CLIPS}/vendor_master.zs.webp"),
    ("bartholomew_master", f"{CLIPS}/bartholomew_master.zs.webp"),
    ("mr_cricket_master", f"{CLIPS}/mr_cricket_master.zs.webp"),
    ("norm_master",    f"{CLIPS}/norm_master.zs.webp"),
    ("broll_greenhouse", f"{CLIPS}/broll_greenhouse.zs.webp"),
    ("broll_cooling_tower", f"{CLIPS}/broll_cooling_tower.zs.webp"),
    ("broll_weather_map", f"{CLIPS}/broll_weather_map.zs.webp"),
]

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)

results = []
t_total = time.time()
for label, src in MASTERS:
    if not os.path.exists(src):
        print(f"SKIP {label}: source missing {src}")
        continue
    t0 = time.time()
    in_dir  = f"{RIFE_FRAMES}/{label}_in"
    out_dir = f"{RIFE_FRAMES}/{label}_out"
    for d in (in_dir, out_dir):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    # anim_dump → PNGs
    run(["anim_dump","-prefix","f_","-folder", in_dir, src])
    n_in = len(glob.glob(f"{in_dir}/f_*.png"))
    # RIFE 3x → n_in * 3 = 72 expected
    n_out = n_in * 3
    t_r = time.time()
    run(["rife-ncnn-vulkan",
         "-i", in_dir, "-o", out_dir,
         "-n", str(n_out),
         "-m", "rife-v4.6",
         "-j", "1:2:2"])
    rife_dur = time.time() - t_r
    produced = len(glob.glob(f"{out_dir}/*.png"))
    dur = round(time.time() - t0, 2)
    print(f"  {label:24} {n_in}f -> {produced}f  rife={rife_dur:.1f}s  total={dur}s")
    results.append({"label": label, "n_in": n_in, "n_out": produced,
                    "rife_s": round(rife_dur,2), "total_s": dur,
                    "frames_dir": out_dir})

import json
with open("/tmp/rife_results.json","w") as f:
    json.dump({"results": results, "total_wall_s": round(time.time()-t_total,2)},
              f, indent=2)
print(f"\nTotal: {round(time.time()-t_total,2)}s wall over {len(results)} masters")
print(f"Wrote /tmp/rife_results.json")
