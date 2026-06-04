"""Shared helpers for the MACU render pipeline.

All stage scripts accept <slug> as argv and read paths relative to
/mnt/storage/shares/MACU/episodes/<slug>/.
"""
import os, json, socket, subprocess, time, glob, urllib.request, urllib.error

# Data lives on the storage drive's MACU share (Windows-visible S:\MACU); the
# pipeline CODE lives in this repo at /mnt/storage/macu-pipeline. They're separate
# on purpose — episodes/assets are big binary data, the repo is code.
SHARES = "/mnt/storage/shares/MACU"
ASSETS = f"{SHARES}/assets"
# Services are all local on the box. Loopback (not the LAN IP) so this survives an
# IP change like the .72 -> .245 host move.
COMFY_URL = "http://127.0.0.1:8188"
PIPER_URL = "http://127.0.0.1:5050"
OMNIVOICE_URL = "http://127.0.0.1:3900"  # bound 127.0.0.1 only on max — stages run local
OMNIVOICE_CONTAINER = "omnivoice"
COMFY_OUT = "/mnt/storage/comfyui/output/macu"


def omnivoice_start(wait_timeout=180, poll_interval=2):
    """Bring the OmniVoice container up and wait until :3900 responds.

    Idempotent: if the container is already running, `docker start` is a no-op
    and the probe loop just confirms readiness. Raises RuntimeError on timeout.
    """
    print(f"[omnivoice] starting container '{OMNIVOICE_CONTAINER}' ...")
    r = subprocess.run(["docker", "start", OMNIVOICE_CONTAINER],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"docker start {OMNIVOICE_CONTAINER} failed: "
                           f"{r.stderr.strip() or r.stdout.strip()}")
    deadline = time.time() + wait_timeout
    last_err = None
    while time.time() < deadline:
        # 1) TCP first (cheap)
        try:
            with socket.create_connection(("127.0.0.1", 3900), timeout=2):
                pass
        except OSError as e:
            last_err = e
            time.sleep(poll_interval)
            continue
        # 2) HTTP confirm — any reply (200 / 404 / 405) means FastAPI is up
        try:
            urllib.request.urlopen(OMNIVOICE_URL + "/docs", timeout=3).read()
            print(f"[omnivoice] ready after {wait_timeout - int(deadline - time.time())}s")
            return
        except urllib.error.HTTPError:
            print(f"[omnivoice] ready (HTTP responding) after "
                  f"{wait_timeout - int(deadline - time.time())}s")
            return
        except Exception as e:
            last_err = e
            time.sleep(poll_interval)
    raise RuntimeError(f"omnivoice did not become ready in {wait_timeout}s "
                       f"(last error: {last_err!r})")


def omnivoice_stop():
    """Stop the OmniVoice container to release VRAM. Best-effort — never raises."""
    r = subprocess.run(["docker", "stop", "-t", "5", OMNIVOICE_CONTAINER],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print(f"[omnivoice] stopped (VRAM released)")
    else:
        print(f"[omnivoice] stop returned non-zero: "
              f"{r.stderr.strip() or r.stdout.strip()}")


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
        "out_thumb_png": f"{base}/final/{slug}_thumb.png",
        "music_dir": f"{base}/.work/music",
        "nosubs": f"{base}/.work/{slug}_nosubs.mp4",
        "nosubs_clean": f"{base}/.work/{slug}_nosubs_clean.mp4",
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


# Sub-stage progress hook. run.py registers a callback here at startup; stages
# call progress_tick(...) to report intra-stage completion. Silent no-op when
# unregistered, so stages stay runnable as standalone scripts.
_progress_tick = None


def set_progress_tick(fn):
    """Register a callable fn(stage_n: int, name: str, frac: float)."""
    global _progress_tick
    _progress_tick = fn


def progress_tick(stage_n, name, frac):
    """Report fractional progress within stage_n. Safe to call always."""
    if _progress_tick is None:
        return
    try:
        f = max(0.0, min(1.0, float(frac)))
        _progress_tick(int(stage_n), str(name), f)
    except Exception:
        pass
