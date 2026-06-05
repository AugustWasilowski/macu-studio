"""Manual git sync of an episode's TEXT files into the tracked repo.

Episodes live OUTSIDE the repo (under MACU_EPISODES, a gitignored area), so this
copies just the text files — script.md / manifest.json / youtube.txt — into a
tracked path at ``episode_meta/<slug>/`` and commits + pushes on demand.
Generated assets (audio/video/frames) are never copied.
"""
from __future__ import annotations

import filecmp
import shutil
import subprocess

from . import config
from .episodes import episode_dir

REPO = config.STUDIO_ROOT.parent
META = REPO / "episode_meta"

TEXT_FILES = ("script.md", "manifest.json", "youtube.txt")


def sync_status(slug: str) -> bool:
    """True when the episode's working TEXT files match the tracked episode_meta
    copy (i.e. nothing to sync). False if any differ or the episode was never
    synced — that's the 'pending changes' (red dot) state in the picker."""
    try:
        src = episode_dir(slug)
    except FileNotFoundError:
        return False
    dest = META / slug
    if not dest.exists():
        return False
    for name in TEXT_FILES:
        f = src / name
        if not f.exists():
            continue  # absent in working → nothing to compare for this file
        d = dest / name
        if not d.exists() or not filecmp.cmp(f, d, shallow=False):
            return False
    return True


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO, text=True,
        capture_output=True,
    )


def sync(slug: str) -> dict:
    """Copy an episode's text files into the repo, commit, and push.

    Never raises on a clean no-op; git errors are surfaced in ``log`` with
    ``ok: False``.
    """
    log_parts: list[str] = []

    def _log(p: subprocess.CompletedProcess) -> None:
        if p.stdout:
            log_parts.append(p.stdout.rstrip())
        if p.stderr:
            log_parts.append(p.stderr.rstrip())

    try:
        src = episode_dir(slug)
    except FileNotFoundError as e:
        return {"ok": False, "committed": False, "commit": None,
                "pushed": False, "log": str(e)}

    dest = META / slug
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in TEXT_FILES:
        f = src / name
        if f.exists():
            shutil.copy2(f, dest / name)
            copied.append(name)
    log_parts.append(f"copied: {', '.join(copied) if copied else '(none)'}")

    add = _git("add", f"episode_meta/{slug}")
    _log(add)
    if add.returncode != 0:
        return {"ok": False, "committed": False, "commit": None,
                "pushed": False, "log": "\n".join(log_parts)}

    commit = _git("commit", "-m", f"studio: sync {slug} meta")
    _log(commit)
    committed = False
    short = None
    if commit.returncode == 0:
        committed = True
    elif "nothing to commit" in (commit.stdout + commit.stderr):
        # clean no-op — already in sync
        committed = False
    else:
        return {"ok": False, "committed": False, "commit": None,
                "pushed": False, "log": "\n".join(log_parts)}

    if committed:
        rev = _git("rev-parse", "--short", "HEAD")
        if rev.returncode == 0:
            short = rev.stdout.strip()

    push = _git("push")
    _log(push)
    pushed = push.returncode == 0

    ok = pushed if committed else True
    return {"ok": ok, "committed": committed, "commit": short,
            "pushed": pushed, "log": "\n".join(log_parts)}


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m macu_studio.gitsync <slug>", file=sys.stderr)
        sys.exit(2)
    result = sync(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
