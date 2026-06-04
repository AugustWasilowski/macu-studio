#!/usr/bin/env python3
"""Re-assembly using RIFE-interpolated 72-frame PNG dirs at 24fps native.
Same per-cue / per-shot structure, same jank filter, same VO mux, same SRT,
same NVENC encode — only the source frames change."""
import json, os, subprocess, glob

EP5 = "/mnt/storage/shares/MACU/episodes/ep5"
RIFE = f"{EP5}/.rife_frames"
VO_DIR = f"{EP5}/vo"
TITLES = f"{EP5}/titles"
WORK = f"{EP5}/.work_rife"
FINAL = f"{EP5}/final"
for d in (WORK, FINAL):
    os.makedirs(d, exist_ok=True)

# Map character/broll keys to RIFE PNG dirs
RIFE_DIR = {
    "safe": f"{RIFE}/safe_master_out",
    "empty_room": f"{RIFE}/c09_s1_out",
    "ron": f"{RIFE}/ron_master_out",
    "walter": f"{RIFE}/walter_master_out",
    "marigold": f"{RIFE}/marigold_master_out",
    "tally_man": f"{RIFE}/tally_man_master_out",
    "vendor": f"{RIFE}/vendor_master_out",
    "bartholomew": f"{RIFE}/bartholomew_master_out",
    "mr_cricket": f"{RIFE}/mr_cricket_master_out",
    "norm": f"{RIFE}/norm_master_out",
    "greenhouse": f"{RIFE}/broll_greenhouse_out",
    "cooling_tower": f"{RIFE}/broll_cooling_tower_out",
    "weather_map": f"{RIFE}/broll_weather_map_out",
}

JANK_FILTER = (
    "scale=256:256:flags=neighbor,"
    "scale=1024:1024:flags=neighbor,"
    "hue=s=0,"
    "curves=master='0/0 0.25/0.20 0.75/0.85 1/1',"
    "gblur=sigma=0.4,"
    "noise=alls=24:allf=t+u,"
    "chromashift=cbh=2:crh=-2,"
    "geq=lum='lum(X+sin(T*9+Y*0.04)*1.5,Y)':cb=128:cr=128,"
    "tinterlace=mode=interleave_top,"
    "vignette=angle=PI/5,"
    "format=yuv420p"
)

def run(cmd):
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print("CMD FAILED:", " ".join(cmd[:8]), "...")
        print(e.stderr[-2000:])
        raise

def probe_dur(path):
    r = run(["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1", path])
    return float(r.stdout.strip())

def rife_shot(rife_dir, shot_id, dur):
    """Build a per-shot mp4 from a 72-frame RIFE dir, capped to `dur`."""
    out = f"{WORK}/{shot_id}.mp4"
    pngs = sorted(glob.glob(f"{rife_dir}/*.png"))
    n = len(pngs)
    # play 72 frames at fps = n/dur. ffmpeg will -r 24 internally to handle
    # cadence; with 24fps output: hold ratio = max(1, 24/(n/dur)) = 24*dur/n.
    target_fps = max(1.0, n / dur)
    run(["ffmpeg","-y","-framerate", f"{target_fps:.6f}",
         "-i", f"{rife_dir}/%08d.png",
         "-vf", JANK_FILTER,
         "-r","24","-t", f"{dur:.4f}",
         "-c:v","libx264","-preset","medium","-crf","22",
         "-movflags","+faststart","-pix_fmt","yuv420p", out])
    return out

def title_shot(title_mp4, shot_id, dur):
    out = f"{WORK}/{shot_id}.mp4"
    src_dur = probe_dur(title_mp4)
    if dur <= src_dur + 0.05:
        run(["ffmpeg","-y","-t", f"{dur:.4f}", "-i", title_mp4,
             "-vf","scale=1024:1024","-r","24","-an",
             "-c:v","libx264","-preset","fast","-crf","22","-pix_fmt","yuv420p", out])
    else:
        pad = dur - src_dur
        run(["ffmpeg","-y","-i", title_mp4,
             "-vf", f"scale=1024:1024,tpad=stop_mode=clone:stop_duration={pad:.4f}",
             "-r","24","-an","-t", f"{dur:.4f}",
             "-c:v","libx264","-preset","fast","-crf","22","-pix_fmt","yuv420p", out])
    return out

def resolve_shot(shot):
    if shot.get("kind") == "character":
        return ("rife", RIFE_DIR[shot["who"]])
    if shot.get("kind") == "broll":
        return ("rife", RIFE_DIR[shot["who"]])
    if shot.get("kind") == "title":
        asset = shot["asset"]
        path = f"{TITLES}/{asset}.mp4"
        return ("title", path)
    raise ValueError(f"unhandled: {shot}")

def main():
    with open(f"{EP5}/manifest.json") as f:
        manifest = json.load(f)

    cue_videos = []
    for cue in manifest["cues"]:
        vo = f"{VO_DIR}/{cue['id']}.wav"
        vo_dur = probe_dur(vo)
        per = vo_dur / len(cue["shots"])
        print(f"cue {cue['id']:4} vo={vo_dur:.2f}s shots={len(cue['shots'])} per={per:.2f}s")

        shot_mp4s = []
        for sh in cue["shots"]:
            kind, src = resolve_shot(sh)
            if kind == "rife":
                out = rife_shot(src, sh["id"], per)
            else:
                out = title_shot(src, sh["id"], per)
            shot_mp4s.append(out)

        clist = f"{WORK}/{cue['id']}_concat.txt"
        with open(clist,"w") as f:
            for v in shot_mp4s:
                f.write(f"file '{v}'\n")
        silent = f"{WORK}/{cue['id']}_silent.mp4"
        run(["ffmpeg","-y","-f","concat","-safe","0","-i", clist,
             "-c","copy", silent])
        muxed = f"{WORK}/{cue['id']}.mp4"
        run(["ffmpeg","-y","-i", silent, "-i", vo,
             "-c:v","copy","-c:a","aac","-b:a","128k","-shortest", muxed])
        cue_videos.append((cue["id"], muxed, probe_dur(muxed)))

    flist = f"{WORK}/full_concat.txt"
    with open(flist,"w") as f:
        for cid, p, _ in cue_videos:
            f.write(f"file '{p}'\n")
    nosubs = f"{WORK}/ep5_rife_nosubs.mp4"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i", flist,
         "-c","copy", nosubs])

    srt = f"{FINAL}/ep5.srt"
    srt_esc = srt.replace(":", "\\:")
    sub_filter = (
        f"subtitles='{srt_esc}':force_style='"
        "Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,"
        "MarginV=32,Alignment=2'"
    )
    final = f"{FINAL}/ep5.mp4"
    run(["ffmpeg","-y","-i", nosubs,
         "-vf", sub_filter,
         "-c:v","h264_nvenc","-preset","p5","-tune","hq","-cq","22",
         "-c:a","copy","-movflags","+faststart", final])

    dur = probe_dur(final)
    print(f"\nFinal: {final}  dur={dur:.2f}s  size={os.path.getsize(final)//1024} KB")

if __name__ == "__main__":
    main()
