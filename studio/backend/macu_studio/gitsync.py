"""Version an episode's TEXT files in a SEPARATE content git repo.

Episodes live OUTSIDE the code repo (under MACU_EPISODES). This copies just the text
files — script.md / manifest.json / youtube.txt — into a CONTENT repo and commits
(and pushes, if that repo has a remote). The content repo is independent of the code
repo so a clone of the code ships none of the author's episodes.

Location: ``MACU_CONTENT_REPO`` (default ``episode_meta/``, which the code repo
gitignores). It's auto-``git init``ed on first sync. To back your episodes up to a
remote, give that repo one: ``cd episode_meta && git remote add origin <url>``.
Generated assets (audio/video/frames) are never copied.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from . import config
from .episodes import episode_dir

REPO = config.STUDIO_ROOT.parent
# The content repo — separate from the code repo. Default: episode_meta/ (gitignored
# by the code repo, so the nested .git is invisible to it).
CONTENT_REPO = Path(os.environ.get("MACU_CONTENT_REPO", str(REPO / "episode_meta")))
# Back-compat alias (older code referenced META).
META = CONTENT_REPO

TEXT_FILES = ("script.md", "manifest.json")  # youtube.txt deprecated → folded into manifest.json

# The ref the sync dot is measured against — a remote ref if the content repo has one,
# else local HEAD (a local-only content repo is still "synced" once committed).
REMOTE_REF = os.environ.get("MACU_CONTENT_REMOTE_REF", "origin/main")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=CONTENT_REPO, text=True, capture_output=True)


def _ensure_repo() -> None:
    """Create + `git init` the content repo on first use (idempotent)."""
    CONTENT_REPO.mkdir(parents=True, exist_ok=True)
    if not (CONTENT_REPO / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=CONTENT_REPO, text=True, capture_output=True)


def _has_remote() -> bool:
    p = _git("remote")
    return p.returncode == 0 and bool(p.stdout.strip())


def _compare_ref() -> str | None:
    """The ref to compare working files against: REMOTE_REF if it resolves, else local
    HEAD, else None (no commits yet → everything is unpushed)."""
    if (CONTENT_REPO / ".git").exists():
        if _git("rev-parse", "--verify", "-q", REMOTE_REF).returncode == 0:
            return REMOTE_REF
        if _git("rev-parse", "--verify", "-q", "HEAD").returncode == 0:
            return "HEAD"
    return None


def _git_blob_hash(content: bytes) -> str:
    """The git object id for `content` (sha1 of 'blob <len>\\0<content>')."""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def pushed_tree() -> dict[str, str] | None:
    """{ '<slug>/<file>': blobhash } at the compare ref, or None if unreadable. One
    git call for all episodes (uses local refs — no network)."""
    ref = _compare_ref()
    if ref is None:
        return None
    p = _git("ls-tree", "-r", ref)
    if p.returncode != 0:
        return None
    out: dict[str, str] = {}
    for line in p.stdout.splitlines():
        meta, _, path = line.partition("\t")           # "<mode> blob <hash>\t<path>"
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob" and path:
            out[path] = parts[2]
    return out


def sync_status(slug: str, tree: dict[str, str] | None = None) -> bool:
    """True when the episode's working TEXT files exactly match the compare ref."""
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
            continue
        saw = True
        want = tree.get(f"{slug}/{name}")
        if not want or _git_blob_hash(f.read_bytes()) != want:
            return False
    return saw


def sync(slug: str, message: str | None = None) -> dict:
    """Copy an episode's text files into the content repo, commit, and (if the repo
    has a remote) push. Never raises on a clean no-op; git errors are surfaced in
    ``log`` with ``ok: False``."""
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

    _ensure_repo()
    dest = CONTENT_REPO / slug
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in TEXT_FILES:
        f = src / name
        if f.exists():
            shutil.copy2(f, dest / name)
            copied.append(name)
    log_parts.append(f"copied: {', '.join(copied) if copied else '(none)'}")

    add = _git("add", slug)
    _log(add)
    if add.returncode != 0:
        return {"ok": False, "committed": False, "commit": None,
                "pushed": False, "log": "\n".join(log_parts)}

    # Scope the commit to ONLY this episode's dir.
    commit = _git("commit", "-m",
                  message.strip() if (message and message.strip()) else f"studio: sync {slug}",
                  "--", slug)
    _log(commit)
    committed = False
    short = None
    if commit.returncode == 0:
        committed = True
    elif "nothing to commit" in (commit.stdout + commit.stderr):
        committed = False
    else:
        return {"ok": False, "committed": False, "commit": None,
                "pushed": False, "log": "\n".join(log_parts)}

    if committed:
        rev = _git("rev-parse", "--short", "HEAD")
        if rev.returncode == 0:
            short = rev.stdout.strip()

    # Push only if the content repo has a remote; a local-only repo is "done" on commit.
    pushed = False
    if _has_remote():
        push = _git("push")
        _log(push)
        pushed = push.returncode == 0
        ok = pushed if committed else True
    else:
        log_parts.append("(no remote on content repo — committed locally only)")
        ok = True

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
