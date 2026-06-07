"""Docs/canon editor (Feature G) — show-aware.

Canon docs live under <repo>/docs in two scopes:

  docs/_common/            shared pipeline/tooling docs (PROMPT_*, schema, …) —
                           visible from every show, scope="common".
  docs/shows/<show-id>/    per-show canon (character bible, story arcs, …),
                           scope="show". Editing one show never touches another.

The Docs panel lists `_common` + the active show's dir together; each entry is
tagged with its scope so reads/writes route back to the right directory.

Filenames are strictly validated (`[\\w.-]+\\.md`, no slashes, no `..`) and show
ids to `[a-z0-9][a-z0-9_-]*`, so nothing escapes DOCS_ROOT. Writes are atomic
(mkstemp + os.replace), mirroring manifest.save.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from . import config

DOCS_ROOT = config.REPO_ROOT / "docs"
COMMON_DIR = DOCS_ROOT / "_common"
SHOWS_DIR = DOCS_ROOT / "shows"

_NAME_RE = re.compile(r"[\w.-]+\.md")
_SHOW_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")


def _safe_name(name: str) -> str:
    """Return `name` if it's a bare `<name>.md`, else raise ValueError."""
    if not name or "/" in name or "\\" in name or ".." in name or not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid doc name: {name!r}")
    return name


def _safe_show(show: str) -> str:
    if not show or "/" in show or "\\" in show or ".." in show or not _SHOW_RE.fullmatch(show):
        raise ValueError(f"invalid show id: {show!r}")
    return show


def show_dir(show: str) -> Path:
    return SHOWS_DIR / _safe_show(show)


def _dir_for_scope(scope: str, show: str | None) -> Path:
    if scope == "common":
        return COMMON_DIR
    if scope == "show":
        if not show:
            raise ValueError("show required for scope='show'")
        return show_dir(show)
    raise ValueError(f"invalid scope: {scope!r}")


def _resolve(name: str, show: str | None, scope: str | None) -> tuple[Path, str]:
    """Return (path, scope). When scope is given it's authoritative; otherwise
    resolve the show dir first, then fall back to _common."""
    name = _safe_name(name)
    if scope:
        return _dir_for_scope(scope, show) / name, scope
    if show:
        cand = show_dir(show) / name
        if cand.exists():
            return cand, "show"
    return COMMON_DIR / name, "common"


def _summ(p: Path, scope: str) -> dict:
    st = p.stat()
    return {"name": p.name, "scope": scope, "mtime": st.st_mtime, "bytes": st.st_size}


def list_docs(show: str | None = None) -> list[dict]:
    """List `_common` docs plus (if `show` given) that show's docs. Common first,
    then show, each alpha by name."""
    out: list[dict] = []
    if COMMON_DIR.exists():
        for p in sorted(COMMON_DIR.glob("*.md"), key=lambda x: x.name):
            if p.is_file():
                out.append(_summ(p, "common"))
    if show:
        sd = show_dir(show)
        if sd.exists():
            for p in sorted(sd.glob("*.md"), key=lambda x: x.name):
                if p.is_file():
                    out.append(_summ(p, "show"))
    return out


def read(name: str, show: str | None = None, scope: str | None = None) -> str:
    p, _ = _resolve(name, show, scope)
    if not p.exists():
        raise FileNotFoundError(f"doc not found: {name}")
    return p.read_text()


def write(name: str, text: str, show: str | None = None, scope: str = "show") -> dict:
    p, scope = _resolve(name, show, scope)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = p.stat().st_mode & 0o777 if p.exists() else 0o664
    fd, tmp = tempfile.mkstemp(prefix=".doc.", suffix=".md.tmp", dir=p.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return _summ(p, scope)
