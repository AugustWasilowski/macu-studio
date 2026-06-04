"""Version history + line diffs for an episode's script.md.

Versions come from the git history of episode_meta/<slug>/script.md — the snapshot
the Studio "sync" button commits — plus the live working file
(EPISODES/<slug>/script.md) as the newest "working" version when it differs from
the latest sync. Diffs are computed with difflib (line-level, GitHub-style).
"""
from __future__ import annotations
import subprocess
import difflib
from datetime import datetime, timezone

from .config import REPO_ROOT
from .episodes import episode_dir


def _rel(slug: str) -> str:
    return f"episode_meta/{slug}/script.md"


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=20,
    )


def _commits(slug: str) -> list[dict]:
    """Sync commits touching this episode's tracked script, newest first."""
    sep = "\x1f"
    r = _git(["log", f"--format=%H{sep}%h{sep}%ct{sep}%s", "--", _rel(slug)])
    out: list[dict] = []
    if r.returncode != 0:
        return out
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        h, short, ct, subj = line.split(sep, 3)
        out.append({"id": h, "short": short, "ts": int(ct), "subject": subj})
    return out


def _content_at(slug: str, commit: str) -> str:
    r = _git(["show", f"{commit}:{_rel(slug)}"])
    return r.stdout if r.returncode == 0 else ""


def _working(slug: str) -> str:
    p = episode_dir(slug) / "script.md"
    return p.read_text() if p.exists() else ""


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def versions(slug: str) -> list[dict]:
    """Newest-first version list. Index 0 is the working copy iff it differs from
    the latest sync; the rest are sync commits."""
    commits = _commits(slug)
    vs: list[dict] = []
    work = _working(slug)
    latest = _content_at(slug, commits[0]["id"]) if commits else None
    if work and (latest is None or work != latest):
        vs.append({"id": "working", "kind": "working",
                   "label": "Working (unsynced)", "iso": None})
    for c in commits:
        vs.append({"id": c["id"], "kind": "commit", "short": c["short"],
                   "label": c["subject"], "iso": _iso(c["ts"])})
    return vs


def _text_for(slug: str, vid: str) -> str:
    return _working(slug) if vid == "working" else _content_at(slug, vid)


def diff(slug: str, base: str, target: str) -> dict:
    """Line-level diff base -> target. base = older version, target = newer."""
    a = _text_for(slug, base).splitlines()
    b = _text_for(slug, target).splitlines()
    lines: list[dict] = []
    added = removed = 0
    for d in difflib.unified_diff(a, b, lineterm="", n=3):
        if d.startswith(("+++", "---")):
            continue
        if d.startswith("@@"):
            lines.append({"tag": "hunk", "text": d})
        elif d.startswith("+"):
            lines.append({"tag": "add", "text": d[1:]})
            added += 1
        elif d.startswith("-"):
            lines.append({"tag": "del", "text": d[1:]})
            removed += 1
        else:
            lines.append({"tag": "ctx", "text": d[1:] if d[:1] == " " else d})
    return {"base": base, "target": target, "added": added, "removed": removed, "lines": lines}
