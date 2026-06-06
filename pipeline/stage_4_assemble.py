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


def freeze_shot(rife_dir, sid, dur, work):
    """Hold-cue variant of rife_shot: lock onto the master's first frame for the
    full per-shot duration. Stops mouths/gestures from animating during a silent
    reaction beat. The jank_filter still runs per output frame so noise,
    scanline-shimmer, and tinterlace keep the broadcast aesthetic alive on top
    of the still image — only the underlying character pose is frozen."""
    pngs = sorted(glob.glob(f"{rife_dir}/*.png"))
    if not pngs:
        raise FileNotFoundError(f"freeze_shot: no PNGs in {rife_dir}")
    first = pngs[0]
    out = f"{work}/{sid}.mp4"
    run(["ffmpeg","-y","-loop","1","-framerate","24",
         "-i", first,
         "-vf", jank_filter(),
         "-r","24","-t", f"{dur:.4f}",
         "-c:v","libx264","-preset","medium","-crf","22",
         "-movflags","+faststart","-pix_fmt","yuv420p", out])
    return out

def title_shot(mp4, sid, dur, work, loop=False):
    out = f"{work}/{sid}.mp4"
    if loop:
        # Loop the source to fill the slot (e.g. the intro title card held under
        # Walter's announcement + the 2s pad). Author the card with gentle
        # continuous motion and a duration >= the longest expected open and this
        # just trims it (no visible seam); a shorter card simply repeats.
        run(["ffmpeg","-y","-stream_loop","-1","-i", mp4,
             "-vf","scale=1024:1024","-r","24","-an","-t", f"{dur:.4f}",
             "-c:v","libx264","-preset","fast","-crf","22",
             "-movflags","+faststart","-pix_fmt","yuv420p", out])
        return out
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
    # Pre-flight: a cue with no shots has no video to show and would divide-by-zero
    # in the per-shot timing below. Fail fast with the exact cue ids so the operator
    # can assign shots (Studio → Video → Generate shot list, or edit the manifest)
    # before re-assembling, instead of hitting a cryptic ZeroDivisionError mid-run.
    shotless = [c["id"] for c in m["cues"] if not c.get("shots")]
    if shotless:
        raise RuntimeError(
            f"[stage 4 assemble] {len(shotless)} cue(s) have no shots assigned: "
            f"{', '.join(shotless)}. Assign shots to each (Studio → Video → "
            f"Generate shot list, or edit the manifest) before assembling.")
    for cue in m["cues"]:
        vo = f"{p['vo']}/{cue['id']}.wav"
        vo_dur = probe_dur(vo)
        per = vo_dur / len(cue["shots"])
        # Hold cues (silent reaction beats) default to freezing on the master's
        # first frame so characters look still under the broadcast jank overlay.
        # hold_style:"play" overrides — the clip animates fully (moon dying,
        # moon returning, final whistle, etc.).
        is_hold = bool(cue.get("hold_seconds"))
        hold_play = is_hold and cue.get("hold_style") == "play"
        # Optional trailing pad (held/looped video + silence) AFTER the VO ends.
        # The intro title-card cue uses this so the card lingers ~2s past Walter's
        # announcement. The pad is tacked onto the LAST shot's screen time; the
        # muxed audio is silence-padded to match (see mux below).
        pad = float(cue.get("pad_seconds") or 0.0)
        nshots = len(cue["shots"])
        shot_mp4s = []
        for idx, sh in enumerate(cue["shots"]):
            sdur = per + (pad if idx == nshots - 1 else 0.0)
            if sh["kind"] in ("character","broll"):
                rife = staged_master_dir(slug, sh["who"], sh["kind"])
                if is_hold and not hold_play:
                    shot_mp4s.append(freeze_shot(rife, sh["id"], sdur, p["work"]))
                else:
                    shot_mp4s.append(rife_shot(rife, sh["id"], sdur, p["work"]))
            elif sh["kind"] == "title":
                # Per-episode titles dir wins; fall back to shared assets/titles/
                tm = f"{p['titles']}/{sh['asset']}.mp4"
                if not os.path.exists(tm):
                    shared = f"/mnt/storage/shares/MACU/assets/titles/{sh['asset']}.mp4"
                    if os.path.exists(shared):
                        tm = shared
                # fill:"loop" loops the card to fill its slot (the intro open);
                # default clones the last frame (tpad) as before.
                loop = sh.get("fill") == "loop"
                shot_mp4s.append(title_shot(tm, sh["id"], sdur, p["work"], loop=loop))
            else:
                raise ValueError(sh)
        clist = f"{p['work']}/{cue['id']}_concat.txt"
        with open(clist,"w") as f:
            for v in shot_mp4s: f.write(f"file '{v}'\n")
        silent = f"{p['work']}/{cue['id']}_silent.mp4"
        run(["ffmpeg","-y","-f","concat","-safe","0","-i", clist,
             "-c","copy", silent])
        muxed = f"{p['work']}/{cue['id']}.mp4"
        if pad > 0:
            # Video already runs vo_dur+pad (pad tacked onto the last shot). Pad
            # the VO with trailing silence so the audio matches the video length,
            # capped with -t. Theme bed (stage 5) keeps playing across the pad.
            total = vo_dur + pad
            run(["ffmpeg","-y","-i", silent,"-i", vo,
                 "-filter_complex","[1:a]apad[aout]",
                 "-map","0:v","-map","[aout]",
                 "-c:v","copy","-c:a","aac","-b:a","128k",
                 "-t", f"{total:.4f}","-movflags","+faststart", muxed])
        else:
            run(["ffmpeg","-y","-i", silent,"-i", vo,
                 "-c:v","copy","-c:a","aac","-b:a","128k","-shortest", muxed])
        cue_videos.append(muxed)
        cue_durs[cue["id"]] = probe_dur(muxed)
        print(f"  cue {cue['id']} per_shot={per:.2f}s dur={cue_durs[cue['id']]:.2f}s")

    flist = f"{p['work']}/full.txt"
    with open(flist,"w") as f:
        for v in cue_videos: f.write(f"file '{v}'\n")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i", flist,
         "-c:v","libx264","-preset","medium","-crf","20","-r","24","-vsync","cfr",
         "-c:a","aac","-b:a","160k","-af","aresample=async=1:first_pts=0",
         "-movflags","+faststart", nosubs])
    total = probe_dur(nosubs)
    with open(f"{p['work']}/cue_durs.json","w") as f:
        json.dump(cue_durs, f, indent=2)
    print(f"[stage 4 assemble] {nosubs} dur={total:.2f}s")
    # Stage 4b: bake any spanning title-card graphics (manifest.overlays[]) onto the
    # freshly-assembled video. refresh_clean snapshots this clean cut so an overlay-only
    # edit can re-composite without a full re-assemble. No-op when overlays is empty.
    gfx = {}
    try:
        import stage_4b_graphics
        gfx = stage_4b_graphics.apply(slug, refresh_clean=True)
    except Exception as e:
        print(f"[stage 4b graphics] skipped: {e}")
        gfx = {"error": str(e)}
    return {"cached": False, "nosubs": nosubs, "total_dur": total,
            "cue_durs": cue_durs, "graphics": gfx, "wall_s": round(time.time()-start,2)}

if __name__ == "__main__":
    main(sys.argv[1])
