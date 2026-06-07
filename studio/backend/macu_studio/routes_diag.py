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

from fastapi import APIRouter

from . import config

router = APIRouter()

DOCTOR = config.REPO_ROOT / "deploy" / "doctor.sh"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


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
