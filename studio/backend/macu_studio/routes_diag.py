"""Diagnostics route — run the installer preflight (deploy/doctor.sh) on demand and
return its report to the UI.

doctor.sh CHECKS the host (git/ffmpeg/python/node, Docker + nvidia runtime, GPU/VRAM,
and the optional chat/terminal deps) and exits 0 when all REQUIRED checks pass. We run
it, strip the ANSI colour codes, and hand the text back — the ✓ / ✗ / ! glyphs survive,
so the frontend can render it as a plain mono report.
"""
import os
import re
import subprocess
import urllib.request
import urllib.error

from fastapi import APIRouter

from . import config
from . import shows as shows_mod
from . import sysstat

router = APIRouter()

DOCTOR = config.REPO_ROOT / "deploy" / "doctor.sh"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _reachable(url: str | None, timeout: float = 1.5) -> bool:
    """True if the service answers at all. Any HTTP response (even 404/405) counts as up;
    only a refused connection / timeout / DNS failure counts as down. Used by the guided
    walkthrough to skip GPU-dependent steps gracefully when a service isn't running."""
    if not url:
        return False
    try:
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True  # answered with a status — it's reachable
    except Exception:
        return False


@router.post("/api/diagnostics")
def post_diagnostics():
    if not DOCTOR.exists():
        return {"ok": False, "exit_code": None, "output": f"diagnostics script not found at {DOCTOR}"}
    # Augment PATH so user-local tools (claude in ~/.local/bin) resolve the same way
    # they would in an interactive shell — otherwise doctor warns they're "not found".
    env = dict(os.environ)
    home = env.get("HOME", "")
    if home:
        env["PATH"] = f"{home}/.local/bin:{env.get('PATH', '')}"
    try:
        p = subprocess.run(
            ["bash", str(DOCTOR)],
            cwd=str(config.REPO_ROOT),
            text=True, capture_output=True, timeout=90, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "output": "diagnostics timed out after 90s"}
    output = _ANSI.sub("", (p.stdout or "") + (p.stderr or "")).strip()
    return {"ok": p.returncode == 0, "exit_code": p.returncode, "output": output}


@router.get("/api/services")
def get_services(show: str | None = None):
    """Quick liveness probe of the optional GPU/render services for a show, so the guided
    walkthrough can mark steps it can't complete (video shots, full render) as skippable
    instead of letting them silently fail. Cheap (~1.5s timeouts), no heavy doctor run."""
    voice_ep = comfy_ep = None
    try:
        defaults = (shows_mod.get_show(show) if show else shows_mod.get_show(shows_mod.DEFAULT_SHOW)).get("episode_defaults") or {}
        voice_ep = (defaults.get("voice") or {}).get("endpoint")
        comfy_ep = (defaults.get("comfyui") or {}).get("endpoint")
    except Exception:
        pass  # unknown show / malformed config → treat services as unprobed (down)
    comfy_url = (comfy_ep.rstrip("/") + "/system_stats") if comfy_ep else None
    return {
        "comfyui": _reachable(comfy_url),
        "voice": _reachable(voice_ep),
        "gpu": sysstat.gpu_stat().get("gpu_pct") is not None,
    }
