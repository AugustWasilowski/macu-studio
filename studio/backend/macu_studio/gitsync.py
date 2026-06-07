"""Manual git sync of an episode's TEXT files into the tracked repo.

Episodes live OUTSIDE the repo (under MACU_EPISODES, a gitignored area), so this
copies just the text files — script.md / manifest.json / youtube.txt — into a
tracked path at ``episode_meta/<slug>/`` and commits + pushes on demand.
Generated assets (audio/video/frames) are never copied.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess

from . import config
from .episodes import episode_dir

REPO = config.STUDIO_ROOT.parent
META = REPO / "episode_meta"

TEXT_FILES = ("script.md", "manifest.json", "youtube.txt")

# Which remote ref the sync dot is measured against — green means the working
# files exactly match what's PUSHED there (not just the local episode_meta copy).
REMOTE_REF = "origin/main"


def _git_blob_hash(content: bytes) -> str:
    """The git object id for `content` (sha1 of 'blob <len>\\0<content>') — same
    value git stores, so we can compare a working file to a tree blob hash without
    reading the blob's bytes back out."""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def pushed_tree() -> dict[str, str] | None:
    """{ 'episode_meta/<slug>/<file>': blobhash } at REMOTE_REF, or None if the
    ref/tree is unreadable (treat every episode as not-pushed). One git call for
    all episodes — no network (uses the local remote-tracking ref, which our own
    pushes update; a push that fails leaves it stale, so the dot stays red)."""
    p = _git("ls-tree", "-r", REMOTE_REF, "--", "episode_meta")
    if p.returncode != 0:
        return None
    out: dict[str, str] = {}
    for line in p.stdout.splitlines():
        meta, _, path = line.partition("\t")          # "<mode> blob <hash>\t<path>"
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob" and path:
            out[path] = parts[2]
    return out


def sync_status(slug: str, tree: dict[str, str] | None = None) -> bool:
    """True when the episode's working TEXT files exactly match what's PUSHED to
    REMOTE_REF (green dot). False if any differ, are missing on the remote, or the
    push hasn't happened — that's the 'pending / unpushed changes' (red) state.
    Pass a `tree` from pushed_tree() to avoid recomputing it per episode."""
    if tree is None:
        tree = pushed_tree()
    if tree is None:
        return False
    try:
        src = episode_dir(slug)
    except FileNotFoundError:
        return False
    saw = False
    for name in TEXT_FILES:
        f = src / name
        if not f.exists():
            continue  # absent in working → nothing to compare for this file
        saw = True
        want = tree.get(f"episode_meta/{slug}/{name}")
        if not want or _git_blob_hash(f.read_bytes()) != want:
            return False
    return saw


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO, text=True,
        capture_output=True,
    )


def sync(slug: str, message: str | None = None) -> dict:
    """Copy an episode's text files into the repo, commit, and push.

    ``message`` overrides the default commit message — used by per-version script
    revisions so each version lands as a clearly-labeled commit.

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

    # Scope the commit to ONLY this episode's meta dir so a sync never bundles
    # unrelated staged work (the repo also holds Studio source + per-show docs).
    commit = _git("commit", "-m",
                  message.strip() if (message and message.strip()) else f"studio: sync {slug} meta",
                  "--", f"episode_meta/{slug}")
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
