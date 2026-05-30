"""Shared helpers for the MACU render pipeline.

All stage scripts accept <slug> as argv and read paths relative to
/mnt/storage/shares/MACU/episodes/<slug>/.
"""
import os, json, subprocess, time, glob

SHARES = "/mnt/storage/shares/MACU"
PIPELINE = f"{SHARES}/pipeline"
ASSETS = f"{SHARES}/assets"
COMFY_URL = "http://10.0.0.245:8188"
PIPER_URL = "http://10.0.0.245:5050"
COMFY_OUT = "/mnt/storage/comfyui/output/macu"


def episode_paths(slug):
    base = f"{SHARES}/episodes/{slug}"
    return {
        "base": base,
        "manifest": f"{base}/manifest.json",
        "clips": f"{base}/clips",
        "frames": f"{base}/frames",
        "rife_frames": f"{base}/.rife_frames",
        "vo": f"{base}/vo",
        "titles": f"{base}/titles",
        "work": f"{base}/.work",
        "final": f"{base}/final",
        "out_mp4": f"{base}/final/{slug}.mp4",
        "out_srt": f"{base}/final/{slug}.srt",
        "out_thumbs": f"{base}/final/{slug}_thumbs.jpg",
        "music_dir": f"{base}/.work/music",
        "nosubs": f"{base}/.work/{slug}_nosubs.mp4",
        "music_nosubs": f"{base}/.work/{slug}_music_nosubs.mp4",
    }


def load_manifest(slug):
    with open(episode_paths(slug)["manifest"]) as f:
        return json.load(f)


def ensure_dirs(slug):
    p = episode_paths(slug)
    for d in (p["clips"], p["frames"], p["rife_frames"], p["vo"],
              p["titles"], p["work"], p["final"], p["music_dir"]):
        os.makedirs(d, exist_ok=True)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def run_quiet(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_dur(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(r.stdout.strip())


def jank_filter():
    return (
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


def staged_master_dir(slug, key, kind):
    """Map a character/broll/etc key to its RIFE PNG dir."""
    p = episode_paths(slug)
    if kind == "character":
        if key == "safe":
            return f"{p['rife_frames']}/safe_master_out"
        return f"{p['rife_frames']}/{key}_master_out"
    if kind == "broll":
        if key == "empty_room":
            # SAFE ad used c09_s1 as the empty_room render; preserved.
            return f"{p['rife_frames']}/c09_s1_out"
        return f"{p['rife_frames']}/broll_{key}_out"
    raise ValueError(f"unhandled kind: {kind}")


def staged_master_webp(slug, key, kind):
    """Where the master webp lives in clips/."""
    p = episode_paths(slug)
    if kind == "character":
        if key == "safe":
            return f"{p['clips']}/safe_master.zs.webp"
        return f"{p['clips']}/{key}_master.zs.webp"
    if kind == "broll":
        if key == "empty_room":
            return f"{p['clips']}/c09_s1.zs.webp"
        return f"{p['clips']}/broll_{key}.zs.webp"
    raise ValueError(f"unhandled kind: {kind}")


def stage_timer():
    t0 = time.time()
    return lambda: round(time.time() - t0, 2)
