"""Self-update routes — check the code repo for a newer version and apply it.

  GET  /api/version               current commit + cached check + live update state
  POST /api/version/check         git fetch + recompute "update available" (network)
  POST /api/version/update        pull + rebuild + restart (background; poll status)
  GET  /api/version/update/status live phase + log of the running/last update
"""
from fastapi import APIRouter, HTTPException

from . import agen as agen_mod
from . import version as version_mod

router = APIRouter()


@router.get("/api/version")
def get_version():
    return {
        "current": version_mod.current(),
        "check": version_mod.cached(),
        "update": version_mod.update_state(),
    }


@router.post("/api/version/check")
def post_version_check():
    return version_mod.check(do_fetch=True)


@router.get("/api/version/update/status")
def get_update_status():
    return version_mod.update_state()


@router.post("/api/version/update")
def post_version_update(force: bool = False):
    # Don't pull+rebuild on top of a live render: the render service shares this
    # checkout (and the studio venv), and the restart would interrupt the UI.
    # ?force=1 (set after the UI's "GPU busy — update anyway?" confirm) skips
    # only this guard — dirty-tree and manual-setup blocks still apply.
    busy, free = agen_mod.gpu_busy()
    if busy and not force:
        raise HTTPException(409, {
            "code": "gpu_busy",
            "free_mib": free,
            "message": f"GPU busy ({free} MiB free) — a render is active; update when idle",
        })
    cur = version_mod.current()
    if cur["dirty"]:
        raise HTTPException(409, "working tree has local changes — refusing to auto-update")
    # Some updates need a manual setup step the in-app updater can't do (no sudo: systemd
    # re-template, new prereqs/models). Block the one-click update and return the exact
    # command(s) — ./deploy/install.sh is idempotent and also pulls.
    blocking = version_mod.blocking_setup()
    if blocking:
        raise HTTPException(409, {
            "reason": "This update needs a manual setup step the in-app updater can't run.",
            "setup": blocking,
            "commands": list(dict.fromkeys(r["command"] for r in blocking if r["command"])),
        })
    started = version_mod.start_update()
    if not started["ok"]:
        raise HTTPException(409, started["reason"])
    return {"ok": True}
