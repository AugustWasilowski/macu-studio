"""Self-update: check the *code* repo (macu-studio) for a newer version and apply it.

Operates on the git checkout the running code lives in (``config.REPO_ROOT``) — this is
the CODE repo, distinct from the episode CONTENT repo handled by ``gitsync.py``.

Flow:
  - ``current()`` — cheap, no network: HEAD, branch, commit subject/date, dirty flag.
  - ``check()`` — ``git fetch`` then compare HEAD against the upstream branch; the result
    is cached so the UI's "update available" badge is cheap to poll.
  - ``start_update()`` — runs ``git pull --ff-only`` + a rebuild
    (``studio/scripts/install.sh`` — needed because the frontend ``dist/`` is gitignored
    and must be re-``npm run build``ed) in a background thread, then exits the process with
    a non-zero code so the systemd unit (``Restart=on-failure``) relaunches with the new
    code. The frontend polls health and reloads.

No sudo and no cgroup gymnastics: the restart is just a non-zero ``os._exit`` — it works on
any deploy that uses the shipped unit (``Restart=on-failure``). When NOT running under
systemd (foreground dev), the updater honestly reports it can't auto-restart instead of
killing the server with no way back.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

from . import config

REPO = str(config.REPO_ROOT)
INSTALL_SH = config.STUDIO_ROOT / "scripts" / "install.sh"

# ASCII unit separator — safe field delimiter for `git log --format`.
_US = "\x1f"

_LOCK = threading.Lock()

# Cached result of the last `check()` — surfaced by GET /api/version so the badge is cheap.
_CHECK: dict = {
    "ts": None, "behind": 0, "ahead": 0, "update_available": False,
    "incoming": [], "remote_short": None, "error": None, "upstream": None,
    "requires_setup": False, "setup": [],
}

# Live state of an in-progress update (phases: idle → pulling → building →
# restarting | restart-needed | error). `log` accumulates pull + build output lines.
_UPDATE: dict = {"phase": "idle", "log": [], "error": None, "started": None}


def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", REPO, *args], text=True,
                          capture_output=True, timeout=timeout)


def _upstream() -> str | None:
    p = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None


def _classify_setup(paths: list[str]) -> list[dict]:
    """Map changed file paths to the manual setup steps the in-app updater CAN'T do
    (it has no sudo and only rebuilds code/deps/frontend). Each reason is shown to the
    user with the exact command to run. De-duplicated, at most one entry per area."""
    reasons: list[dict] = []

    def add(area: str, reason: str, command: str | None, blocking: bool = True) -> None:
        if not any(r["area"] == area for r in reasons):
            reasons.append({"area": area, "reason": reason, "command": command, "blocking": blocking})

    for p in paths:
        base = p.rsplit("/", 1)[-1]
        if p.endswith(".service") or base == "install-systemd.sh":
            add("systemd", "A systemd unit template changed — the live units won't update on their own.",
                "sudo ./deploy/install-systemd.sh")
        elif base == "install-prereqs.sh":
            add("prereqs", "System packages / prerequisites changed.", "./deploy/install.sh")
        elif base == "fetch-models.sh":
            add("models", "The model set changed — new weights may need fetching.", "./deploy/install.sh")
        elif p.startswith("deploy/services/"):
            add("services", "Local service definitions (ComfyUI/OmniVoice/Ollama/Piper) changed.",
                "./deploy/install.sh")
        elif p == ".env.example":
            # Advisory, not blocking: the updater applies fine; the user just may want to
            # adopt new optional config. No command can do this for them.
            add("env", "New configuration options were added — review your .env against .env.example.",
                None, blocking=False)
        elif p.startswith("deploy/"):
            add("deploy", "The installer changed.", "./deploy/install.sh")
    return reasons


def _setup_for_range(rng: str) -> list[dict]:
    """Setup steps implied by the files changed across a git range (e.g. 'HEAD..origin/main').
    Network-free — operates on refs already present."""
    d = _git("diff", "--name-only", rng)
    if d.returncode != 0:
        return []
    return _classify_setup([p for p in d.stdout.splitlines() if p.strip()])


def setup_required() -> list[dict]:
    """All setup notes for the pending update (HEAD → upstream): blocking steps the
    updater can't do AND advisory notices (e.g. new .env options). May be empty."""
    up = _upstream()
    return _setup_for_range(f"HEAD..{up}") if up else []


def blocking_setup() -> list[dict]:
    """Only the steps that BLOCK the one-click updater (it can't sudo/fetch). Advisory
    notices (env) are excluded — they don't stop an update."""
    return [r for r in setup_required() if r.get("blocking")]


_SHORT_COMMIT: "str | None" = None


def short_commit() -> "str | None":
    """Short macu-studio HEAD hash, cached for the process (a self-update restarts us so the
    cache can't go stale). Stamped into manifests by manifest.save() for provenance."""
    global _SHORT_COMMIT
    if _SHORT_COMMIT is None:
        p = _git("rev-parse", "--short", "HEAD")
        _SHORT_COMMIT = p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else ""
    return _SHORT_COMMIT or None


def _can_autorestart() -> bool:
    """True when we were launched by systemd — a non-zero exit will be restarted.
    (systemd sets INVOCATION_ID for every service it runs.)"""
    return bool(os.environ.get("INVOCATION_ID"))


def current() -> dict:
    """Cheap, network-free snapshot of the running checkout."""
    return {
        "commit": _git("rev-parse", "HEAD").stdout.strip(),
        "short": _git("rev-parse", "--short", "HEAD").stdout.strip(),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
        "subject": _git("log", "-1", "--format=%s").stdout.strip(),
        "committed_iso": _git("log", "-1", "--format=%cI").stdout.strip() or None,
        "dirty": bool(_git("status", "--porcelain").stdout.strip()),
        "upstream": _upstream(),
        "can_autorestart": _can_autorestart(),
    }


def cached() -> dict:
    with _LOCK:
        return dict(_CHECK)


def _store(info: dict) -> None:
    with _LOCK:
        _CHECK.update(info)


def check(do_fetch: bool = True) -> dict:
    """Compare the local HEAD against its upstream branch and cache the result.

    ``do_fetch`` hits the network (``git fetch``); pass False to recompute from refs
    we already have. Never raises — errors are returned in the ``error`` field."""
    up = _upstream()
    info = {
        "ts": time.time(), "behind": 0, "ahead": 0, "update_available": False,
        "incoming": [], "remote_short": None, "error": None, "upstream": up,
        "requires_setup": False, "setup": [],
    }
    if not up:
        info["error"] = "no upstream branch (this checkout has no remote-tracking ref)"
        _store(info)
        return info

    if do_fetch:
        try:
            f = _git("fetch", "--quiet", timeout=120)
        except subprocess.TimeoutExpired:
            info["error"] = "git fetch timed out"
            _store(info)
            return info
        if f.returncode != 0:
            info["error"] = (f.stderr or f.stdout or "git fetch failed").strip()
            _store(info)
            return info

    counts = _git("rev-list", "--left-right", "--count", f"HEAD...{up}")
    if counts.returncode == 0 and counts.stdout.split():
        ahead, behind = counts.stdout.split()
        info["ahead"], info["behind"] = int(ahead), int(behind)
    info["update_available"] = info["behind"] > 0

    if info["behind"] > 0:
        log = _git("log", f"--format=%h{_US}%s{_US}%cI", f"HEAD..{up}")
        for line in log.stdout.splitlines():
            parts = line.split(_US)
            if len(parts) == 3:
                info["incoming"].append({"short": parts[0], "subject": parts[1], "iso": parts[2]})
        info["remote_short"] = _git("rev-parse", "--short", up).stdout.strip() or None
        info["setup"] = _setup_for_range(f"HEAD..{up}")
        info["requires_setup"] = any(r.get("blocking") for r in info["setup"])

    _store(info)
    return info


def update_state() -> dict:
    with _LOCK:
        return {"phase": _UPDATE["phase"], "log": list(_UPDATE["log"]),
                "error": _UPDATE["error"], "started": _UPDATE["started"]}


def _ulog(line: str) -> None:
    with _LOCK:
        _UPDATE["log"].append(line)


def _set_phase(phase: str) -> None:
    with _LOCK:
        _UPDATE["phase"] = phase


def _fail(msg: str) -> None:
    _ulog("ERROR: " + msg)
    with _LOCK:
        _UPDATE["phase"] = "error"
        _UPDATE["error"] = msg


def start_update() -> dict:
    """Kick off the update in a background thread. Returns immediately so the caller
    can stream progress via ``update_state()``. Refuses if one is already running."""
    with _LOCK:
        if _UPDATE["phase"] in ("pulling", "building", "restarting"):
            return {"ok": False, "reason": "an update is already in progress"}
        _UPDATE.update({"phase": "pulling", "log": [], "error": None, "started": time.time()})
    threading.Thread(target=_run_update, daemon=True, name="macu-update").start()
    return {"ok": True}


def _run_install() -> bool:
    """Run the in-place rebuild (deps + frontend) and tee its output into the log.
    install.sh locates Node via ~/.nvm itself, so it doesn't need node on PATH."""
    if not INSTALL_SH.exists():
        _ulog(f"rebuild script missing: {INSTALL_SH}")
        return False
    proc = subprocess.Popen(
        ["bash", str(INSTALL_SH)],
        cwd=str(config.STUDIO_ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env=dict(os.environ),
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        _ulog(line.rstrip())
    proc.wait()
    return proc.returncode == 0


def _run_update() -> None:
    try:
        cur = current()
        if cur["dirty"]:
            _fail("working tree has uncommitted changes — refusing to pull. "
                  "Commit or discard local edits first.")
            return
        # Refuse if the pending update needs a manual setup step the in-app updater can't
        # do (sudo systemd re-template, new prereqs/models). The route also blocks this, but
        # guard here too in case start_update() is driven directly.
        blocking = blocking_setup()
        if blocking:
            cmds = " ; ".join(dict.fromkeys(r["command"] for r in blocking if r["command"]))
            _fail("this update needs a manual setup step the in-app updater can't run"
                  + (f" — run: {cmds}" if cmds else "") + ". See the update panel for details.")
            return
        _ulog(f"at {cur['short']} ({cur['branch']}); pulling…")

        pull = _git("pull", "--ff-only", timeout=180)
        for ln in (pull.stdout + pull.stderr).splitlines():
            _ulog(ln)
        if pull.returncode != 0:
            _fail("git pull failed (not a fast-forward, or network error) — see log.")
            return

        new = current()
        if new["commit"] == cur["commit"]:
            _ulog("already up to date — nothing to rebuild.")
            _set_phase("idle")
            check(do_fetch=False)
            return
        _ulog(f"pulled → {new['short']}; rebuilding…")

        _set_phase("building")
        if not _run_install():
            _fail("rebuild failed — see log. The new code is on disk but the server was "
                  "NOT restarted; fix the build, then restart manually.")
            return

        # New version is built and on disk. Refresh the cached check so a reload shows
        # "up to date", then relaunch under the new code.
        check(do_fetch=False)
        if _can_autorestart():
            _set_phase("restarting")
            _ulog("rebuild complete — restarting service…")
            # Give the client ~1.5s to read the 'restarting' phase before we exit.
            threading.Timer(1.5, lambda: os._exit(70)).start()
        else:
            _set_phase("restart-needed")
            _ulog("rebuild complete. Not running under systemd — restart the server "
                  "manually (e.g. ./deploy/start-studio.sh) to load the new version.")
    except subprocess.TimeoutExpired:
        _fail("a git operation timed out — check the network and try again.")
    except Exception as e:  # never let the worker thread die silently
        _fail(f"unexpected error: {e}")
