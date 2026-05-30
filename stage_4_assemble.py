#!/usr/bin/env python3
"""Stage 4: per-cue ffmpeg with jank filter, concat shots, mux VO,
build full silent (then VO-muxed) assembly -> .work/<slug>_nosubs.mp4.

Idempotent: skips if .work/<slug>_nosubs.mp4 exists and is newer than manifest.
Usage: python3 stage_4_assemble.py <slug>
"""
import sys, os, glob, subprocess, time, json
sys.path.insert(0, os.path.dirname(__file__))
from lib import (episode_paths, load_manifest, ensure_dirs,
                 jank_filter, probe_dur, staged_master_dir)

def run(cmd):
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print("FAIL:", " ".join(cmd[:6])); print(e.stderr[-1500:]); raise

def rife_shot(rife_dir, sid, dur, work):
    out = f"{work}/{sid}.mp4"
    pngs = sorted(glob.glob(f"{rife_dir}/*.png"))
    n = len(pngs)
    fps_in = max(1.0, n / dur)
    run(["ffmpeg","-y","-framerate", f"{fps_in:.6f}",
         "-i", f"{rife_dir}/%08d.png",
         "-vf", jank_filter(),
         "-r","24","-t", f"{dur:.4f}",
         "-c:v","libx264","-preset","medium","-crf","22",
         "-movflags","+faststart","-pix_fmt","yuv420p", out])
    return out

def title_shot(mp4, sid, dur, work):
    out = f"{work}/{sid}.mp4"
    src_dur = probe_dur(mp4)
    if dur <= src_dur + 0.05:
        run(["ffmpeg","-y","-t", f"{dur:.4f}","-i", mp4,
             "-vf","scale=1024:1024","-r","24","-an",
             "-c:v","libx264","-preset","fast","-crf","22","-pix_fmt","yuv420p", out])
    else:
        pad = dur - src_dur
        run(["ffmpeg","-y","-i", mp4,
             "-vf", f"scale=1024:1024,tpad=stop_mode=clone:stop_duration={pad:.4f}",
             "-r","24","-an","-t", f"{dur:.4f}",
             "-c:v","libx264","-preset","fast","-crf","22","-pix_fmt","yuv420p", out])
    return out

def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    nosubs = p["nosubs"]

    if os.path.exists(nosubs) and os.path.getmtime(nosubs) > os.path.getmtime(p["manifest"]):
        print(f"[stage 4 assemble] cached: {nosubs}")
        return {"cached": True, "nosubs": nosubs}

    start = time.time()
    cue_videos = []
    cue_durs = {}
    for cue in m["cues"]:
        vo = f"{p['vo']}/{cue['id']}.wav"
        vo_dur = probe_dur(vo)
        per = vo_dur / len(cue["shots"])
        shot_mp4s = []
        for sh in cue["shots"]:
            if sh["kind"] in ("character","broll"):
                rife = staged_master_dir(slug, sh["who"], sh["kind"])
                shot_mp4s.append(rife_shot(rife, sh["id"], per, p["work"]))
            elif sh["kind"] == "title":
                tm = f"{p['titles']}/{sh['asset']}.mp4"
                shot_mp4s.append(title_shot(tm, sh["id"], per, p["work"]))
            else:
                raise ValueError(sh)
        clist = f"{p['work']}/{cue['id']}_concat.txt"
        with open(clist,"w") as f:
            for v in shot_mp4s: f.write(f"file '{v}'\n")
        silent = f"{p['work']}/{cue['id']}_silent.mp4"
        run(["ffmpeg","-y","-f","concat","-safe","0","-i", clist,
             "-c","copy", silent])
        muxed = f"{p['work']}/{cue['id']}.mp4"
        run(["ffmpeg","-y","-i", silent,"-i", vo,
             "-c:v","copy","-c:a","aac","-b:a","128k","-shortest", muxed])
        cue_videos.append(muxed)
        cue_durs[cue["id"]] = probe_dur(muxed)
        print(f"  cue {cue['id']} per_shot={per:.2f}s dur={cue_durs[cue['id']]:.2f}s")

    flist = f"{p['work']}/full.txt"
    with open(flist,"w") as f:
        for v in cue_videos: f.write(f"file '{v}'\n")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i", flist,
         "-c","copy", nosubs])
    total = probe_dur(nosubs)
    with open(f"{p['work']}/cue_durs.json","w") as f:
        json.dump(cue_durs, f, indent=2)
    print(f"[stage 4 assemble] {nosubs} dur={total:.2f}s")
    return {"cached": False, "nosubs": nosubs, "total_dur": total,
            "cue_durs": cue_durs, "wall_s": round(time.time()-start,2)}

if __name__ == "__main__":
    main(sys.argv[1])
