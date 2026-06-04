"""Docs/canon editor (Feature G).

Read/write the markdown canon docs under <repo>/docs. Filenames are strictly
validated (`[\\w.-]+\\.md`, no slashes, no `..`) so nothing escapes DOCS_DIR.
Writes are atomic (mkstemp + os.replace), mirroring manifest.save.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from . import config

DOCS_DIR = config.REPO_ROOT / "docs"

_NAME_RE = re.compile(r"[\w.-]+\.md")


def _safe_name(name: str) -> str:
    """Return `name` if it's a bare `<name>.md`, else raise ValueError."""
    if not name or "/" in name or "\\" in name or ".." in name or not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid doc name: {name!r}")
    return name


def _path(name: str) -> Path:
    return DOCS_DIR / _safe_name(name)


def list_docs() -> list[dict]:
    out: list[dict] = []
    if not DOCS_DIR.exists():
        return out
    for p in sorted(DOCS_DIR.glob("*.md"), key=lambda x: x.name):
        if not p.is_file():
            continue
        st = p.stat()
        out.append({"name": p.name, "mtime": st.st_mtime, "bytes": st.st_size})
    return out


def read(name: str) -> str:
    p = _path(name)
    if not p.exists():
        raise FileNotFoundError(f"doc not found: {name}")
    return p.read_text()


def write(name: str, text: str) -> dict:
    p = _path(name)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    mode = p.stat().st_mode & 0o777 if p.exists() else 0o664
    fd, tmp = tempfile.mkstemp(prefix=".doc.", suffix=".md.tmp", dir=DOCS_DIR)
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
    st = p.stat()
    return {"name": p.name, "mtime": st.st_mtime, "bytes": st.st_size}
