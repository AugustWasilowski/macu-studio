"""Shared helpers for the MACU render pipeline.

All stage scripts accept <slug> as argv and read paths relative to
/mnt/storage/shares/MACU/episodes/<slug>/.
"""
import os, json, socket, subprocess, time, glob, urllib.request, urllib.error
from pathlib import Path

# Load the repo-root .env (the pipeline has no config.py). Wrapped so Max's SYSTEM
# python — which has no python-dotenv — still imports lib fine; there the literal
# defaults below ARE the current Max values. On a new machine set .env, or inject
# the vars via the systemd unit's EnvironmentFile=. dotenv won't override vars the
# environment already set, so systemd Environment= lines still win.
def _load_dotenv(path: Path) -> None:
    """Load .env into os.environ. Prefer python-dotenv; fall back to a minimal
    inline parser when it isn't installed — otherwise a configured .env on a fresh
    machine would be SILENTLY ignored and every path below would revert to the Max
    defaults. Never overrides a var already in the environment (systemd wins)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(path)
        return
    except ModuleNotFoundError:
        pass
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Data lives on the storage drive's MACU share (Windows-visible S:\MACU); the
# pipeline CODE lives in this repo. Env-driven; the default = the current Max path,
# so Max with no .env is byte-identical to before.
SHARES = os.environ.get("MACU_SHARES", "/mnt/storage/shares/MACU")
ASSETS = os.environ.get("MACU_ASSETS", f"{SHARES}/assets")
# Where episodes live. Defaults to the MACU flat dir; the render server (serve.py)
# overrides this per-job via MACU_EPISODES so a non-default show whose episodes
# live elsewhere renders with no other code change.
EPISODES_ROOT = os.environ.get("MACU_EPISODES", f"{SHARES}/episodes")
# Services are all local on the box. Loopback default (survives an IP change like
# the .72 -> .245 host move); override only if a service is remote.
COMFY_URL = os.environ.get("MACU_COMFY_URL", "http://127.0.0.1:8188")
PIPER_URL = os.environ.get("MACU_PIPER_URL", "http://127.0.0.1:5050")
OMNIVOICE_URL = os.environ.get("MACU_OMNIVOICE_URL", "http://127.0.0.1:3900")
OMNIVOICE_CONTAINER = os.environ.get("MACU_OMNIVOICE_CONTAINER", "omnivoice")
COMFY_OUT = os.environ.get("MACU_COMFY_OUT", "/mnt/storage/comfyui/output/macu")
COMFY_OUTPUT_ROOT = os.environ.get("MACU_COMFY_OUTPUT_ROOT", "/mnt/storage/comfyui/output")


def resolve_asset_path(path, base=None):
    """Resolve a manifest-supplied asset path to THIS host's filesystem.

    Manifests sometimes carry absolute paths baked on another host — e.g. a
    /mnt/storage/shares/MACU/assets/... path on a box where the share actually lives
    under MACU_SHARES=/home/.../macu-data/shares/MACU. Stages used to read those
    verbatim and break on the wrong host (SSA-126: music.source_dir, fontsdir).

    Rules: an absolute path that EXISTS is used as-is. An absolute path that doesn't
    is re-rooted under this host's ASSETS/SHARES by its last 'assets/' or 'shares/MACU/'
    marker segment (so paths authored on any host resolve here). A relative path is
    joined onto `base` (ASSETS by default). Falls back to the original string if
    nothing matches — the caller's own existence check / ffmpeg then reports it."""
    if not path:
        return path
    if os.path.isabs(path):
        if os.path.exists(path):
            return path
        norm = path.replace("\\", "/")
        for marker, root in (("/assets/", ASSETS), ("/shares/MACU/", SHARES)):
            idx = norm.rfind(marker)
            if idx != -1:
                cand = os.path.join(root, norm[idx + len(marker):])
                if os.path.exists(cand):
                    return cand
        return path
    return os.path.join(base or ASSETS, path)


def _omnivoice_compose_up():
    """Create + start the OmniVoice container from its compose file — for a fresh
    install where the image was pulled but no container was ever created (so
    `docker start` finds nothing). Uses deploy/services/.env for MACU_DATA_ROOT."""
    repo = Path(__file__).resolve().parents[1]
    compose = repo / "deploy" / "services" / "omnivoice" / "docker-compose.yml"
    envfile = repo / "deploy" / "services" / ".env"
    cmd = ["docker", "compose"]
    if envfile.exists():
        cmd += ["--env-file", str(envfile)]
    cmd += ["-f", str(compose), "up", "-d"]
    return subprocess.run(cmd, capture_output=True, text=True)


_DOCKER_HELP = (
    "OmniVoice runs as a LOCAL Docker container, but Docker isn't usable from this "
    "environment.\n"
    "  • Docker Desktop + WSL (common): the distro's `docker` shim can dangle after a "
    "distro move/reinstall.\n"
    "    Fix: Docker Desktop -> Settings -> Resources -> WSL Integration -> enable this "
    "distro -> Apply & Restart,\n"
    "    then `wsl --shutdown` and reopen the distro. Verify: `docker info`.\n"
    "  • Then ensure the container exists: `docker ps -a | grep omnivoice` (if missing: "
    "`docker compose -f deploy/services/omnivoice/docker-compose.yml create`)."
)


def _docker_ok():
    """(ok, detail) — is the `docker` CLI present AND the daemon/integration reachable?
    Catches the Docker-Desktop-on-WSL failure where /usr/bin/docker dangles after a
    distro move (FileNotFoundError) or the daemon is unreachable (`docker info` != 0),
    so the on-demand start can fail with an actionable message instead of a raw trace."""
    try:
        r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                           capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return False, "the `docker` CLI is not on PATH (missing or dangling symlink)"
    except Exception as e:
        return False, f"could not run docker: {e}"
    if r.returncode != 0:
        return False, (r.stderr.strip() or r.stdout.strip() or "docker daemon unreachable")
    return True, (r.stdout.strip() or "ok")


def omnivoice_start(wait_timeout=180, poll_interval=2):
    """Bring the OmniVoice container up and wait until :3900 responds.

    Idempotent: if the container is already running, `docker start` is a no-op
    and the probe loop just confirms readiness. Raises RuntimeError on timeout.
    """
    ok, detail = _docker_ok()
    if not ok:
        raise RuntimeError(f"[omnivoice] Docker is not usable here ({detail}).\n{_DOCKER_HELP}")
    print(f"[omnivoice] starting container '{OMNIVOICE_CONTAINER}' ...")
    r = subprocess.run(["docker", "start", OMNIVOICE_CONTAINER],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # Fresh install: only the image was pulled, no container yet — create it.
        if "no such container" in (r.stderr + r.stdout).lower():
            print("[omnivoice] no container yet — creating it via compose ...")
            r = _omnivoice_compose_up()
        if r.returncode != 0:
            raise RuntimeError(f"could not start {OMNIVOICE_CONTAINER}: "
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
    try:
        r = subprocess.run(["docker", "stop", "-t", "5", OMNIVOICE_CONTAINER],
                           capture_output=True, text=True)
    except Exception as e:
        # runs in finally blocks — a missing/dangling docker must not mask the real error
        print(f"[omnivoice] stop skipped — docker not usable: {e}")
        return
    if r.returncode == 0:
        print(f"[omnivoice] stopped (VRAM released)")
    else:
        print(f"[omnivoice] stop returned non-zero: "
              f"{r.stderr.strip() or r.stdout.strip()}")


def episode_paths(slug):
    base = f"{EPISODES_ROOT}/{slug}"
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


def dub_paths(slug, lang):
    """Per-language Localize artifacts under the episode dir. English keys in
    episode_paths() are untouched; these are additive."""
    base = f"{EPISODES_ROOT}/{slug}"
    return {
        "vo_dir": f"{base}/vo/{lang}",
        "loc_dir": f"{base}/loc/{lang}",
        "translations": f"{base}/loc/{lang}/translations.json",
        "glossary": f"{base}/loc/glossary.json",
        "dub_music_nosubs": f"{base}/.work/{slug}.{lang}_music_nosubs.mp4",
        "out_srt": f"{base}/final/{slug}.{lang}.srt",
        "out_mp4": f"{base}/final/{slug}.{lang}.mp4",
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


def jank_filter(full=False):
    """The MACU broadcast look, as an ffmpeg -vf chain.

    Default (August's call 2026-06-14, SSA-127) is the CLEAN look: B&W + broadcast
    contrast + grain + chroma fringe + vignette, on a clean lanczos upscale. The
    wiggle (geq sine-warp), scanlines (tinterlace), and lo-fi pixelation (256->1024
    neighbor down-up) are dropped. Pass full=True (manifest `style.jank: true`) to
    restore the original full-retro recipe per-episode."""
    if full:
        # Original full-jank recipe — the down-up neighbor scale is the lo-fi
        # pixelation; geq is the VHS tracking wiggle; tinterlace is the scanlines.
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
    return (
        "scale=1024:1024:flags=lanczos,"
        "hue=s=0,"
        "curves=master='0/0 0.25/0.20 0.75/0.85 1/1',"
        "gblur=sigma=0.4,"
        "noise=alls=24:allf=t+u,"
        "chromashift=cbh=2:crh=-2,"
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
