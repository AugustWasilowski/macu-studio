"""Studio↔Studio sync — working text travels through the show's macu-web repo.

Two Studio installs connected to the same macu-web (the existing connect token
is the shared key) sync a show's WORKING TEXT through a private `sync/` subtree
of the same per-show git repo the Publish flow uses:

  sync/episodes/<slug>/script.md        ← the authored scripts (riff-excluded
  sync/episodes/<slug>/manifest.json       on macu-web — never in public bundles)
  sync/docs/<name>.md                   ← canon docs
  sync/characters/<key>.json            ← character records (takes' PNGs travel
                                           via import/export, not sync)

Three-way reconciliation per file against a local base snapshot (the state at
the last successful sync, kept at <repo>/.git/macu-sync-base.json so neither
publish's tree rewrite nor anything else can clobber it):

  local==remote               → in sync (adopt into base)
  changed locally only        → PUSH
  changed remotely only       → PULL
  changed on both             → CONFLICT → newest wins (local file mtime vs the
                                remote commit time); the losing local file gets
                                a timestamped .bak

Deletions do NOT propagate (v1): a file missing on one side is copied from the
other. Plan first (GET …/sync/plan), then apply — the plan is recomputed at
apply time so a stale UI can't smuggle writes.

Binaries never sync here — that's import/export's job. Machine-local config
(engines.json, tokens, voice profile ids) never travels at all.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path

from . import config
from . import gitsync
from . import models
from . import shows as shows_mod
from .publish import PUBLISH_ROOT, _creds, _git, _git_env

DOCS_ROOT = config.REPO_ROOT / "docs" / "shows"
SYNC_PREFIX = "sync/"


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _hostname() -> str:
    try:
        return socket.gethostname().split(".")[0]
    except Exception:
        return "studio"


def _token_url(base: str, token: str | None, show: str) -> str:
    if base.startswith("file://"):
        return f"{base}/{show}.git"   # test harness: a local bare repo, no auth
    return f"{base.replace('://', f'://macu:{token}@', 1)}/{show}.git"


def _redact(text: str, token: str | None) -> str:
    return text.replace(token, "***") if token else text


# ---- contract: which local files sync, and where they live -----------------------

def _char_root(show: str) -> Path:
    return config.SHARES / "shows" / show / "characters"


def local_entries(show: str) -> dict[str, Path]:
    """{contract-path: local Path} for everything that exists locally."""
    cfg = shows_mod.get_show(show)
    ep_root = Path(cfg["episodes_dir"])
    out: dict[str, Path] = {}
    if ep_root.exists():
        for ep in sorted(p for p in ep_root.iterdir() if p.is_dir()):
            if not (ep / "manifest.json").exists():
                continue
            for name in ("script.md", "manifest.json"):
                f = ep / name
                if f.exists():
                    out[f"episodes/{ep.name}/{name}"] = f
    docs = DOCS_ROOT / show
    if docs.is_dir():
        for f in sorted(docs.glob("*.md")):
            out[f"docs/{f.name}"] = f
    croot = _char_root(show)
    if croot.is_dir():
        for d in sorted(croot.iterdir()):
            cj = d / "character.json"
            if d.is_dir() and not d.name.startswith(".") and cj.exists():
                out[f"characters/{d.name}.json"] = cj
    return out


def _local_dest(show: str, path: str) -> Path:
    """Where a pulled contract path lands locally."""
    cfg = shows_mod.get_show(show)
    parts = path.split("/")
    if parts[0] == "episodes" and len(parts) == 3:
        return Path(cfg["episodes_dir"]) / parts[1] / parts[2]
    if parts[0] == "docs" and len(parts) == 2:
        return DOCS_ROOT / show / parts[1]
    if parts[0] == "characters" and len(parts) == 2 and parts[1].endswith(".json"):
        return _char_root(show) / parts[1][:-5] / "character.json"
    raise ValueError(f"unexpected sync path: {path}")


def _validate_pull(path: str, data: bytes) -> str | None:
    """Reason to refuse a pulled file, or None when it's safe to write."""
    if path.endswith("manifest.json"):
        try:
            models.validate(json.loads(data.decode()))
        except Exception as e:
            return f"invalid manifest: {e}"
    if path.startswith("characters/"):
        try:
            json.loads(data.decode())
        except Exception as e:
            return f"invalid character json: {e}"
    return None


# ---- repo plumbing ---------------------------------------------------------------

def _repo(show: str) -> Path:
    repo = PUBLISH_ROOT / show
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo,
                       text=True, capture_output=True, env=_git_env())
    return repo


def _base_path(repo: Path) -> Path:
    return repo / ".git" / "macu-sync-base.json"


def _load_base(repo: Path) -> dict[str, str]:
    p = _base_path(repo)
    try:
        return dict(json.loads(p.read_text()))
    except Exception:
        return {}


def _save_base(repo: Path, base: dict[str, str]) -> None:
    _base_path(repo).write_text(json.dumps(base, indent=2, sort_keys=True))


def _fetch(repo: Path, show: str, base_url: str, token: str | None) -> tuple[bool, str]:
    """Fetch origin main → FETCH_HEAD. Returns (has_remote_history, log)."""
    r = _git(repo, "fetch", _token_url(base_url, token, show), "main")
    if r.returncode == 0:
        return True, "fetched"
    err = _redact(r.stderr or r.stdout, token)
    if "couldn't find remote ref" in err or "Could not find remote" in err:
        return False, "remote is empty (first sync)"
    raise RuntimeError(f"fetch failed: {err[:400]}")


def _remote_tree(repo: Path) -> dict[str, str]:
    """{contract-path: blob-sha} of the sync/ subtree at FETCH_HEAD."""
    r = _git(repo, "ls-tree", "-r", "FETCH_HEAD", "--", "sync")
    out: dict[str, str] = {}
    if r.returncode != 0:
        return out
    for line in r.stdout.splitlines():
        # "<mode> blob <sha>\t<path>"
        try:
            meta, path = line.split("\t", 1)
            sha = meta.split()[2]
        except ValueError:
            continue
        if path.startswith(SYNC_PREFIX):
            out[path[len(SYNC_PREFIX):]] = sha
    return out


def _remote_bytes(repo: Path, path: str) -> bytes:
    r = subprocess.run(["git", "cat-file", "blob", f"FETCH_HEAD:{SYNC_PREFIX}{path}"],
                       cwd=repo, capture_output=True, env=_git_env())
    if r.returncode != 0:
        raise RuntimeError(f"cat-file failed for {path}")
    return r.stdout


def _remote_commit_ts(repo: Path, path: str) -> float:
    r = _git(repo, "log", "-1", "--format=%ct", "FETCH_HEAD", "--", f"{SYNC_PREFIX}{path}")
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


# ---- plan ------------------------------------------------------------------------

def status(show: str) -> dict:
    base_url, token = _creds()
    return {"connected": bool(base_url and (token or base_url.startswith("file://"))),
            "base": base_url, "host": _hostname()}


def plan(show: str) -> dict:
    """Compute what a sync would do. Read-only (does fetch)."""
    base_url, token = _creds()
    if not base_url or (not token and not base_url.startswith("file://")):
        raise RuntimeError("not connected to macu-web — connect on the Publish page "
                           "(both Studios must use the same connection)")
    shows_mod.get_show(show)  # raises on unknown show
    repo = _repo(show)
    has_remote, fetch_log = _fetch(repo, show, base_url, token)
    remote = _remote_tree(repo) if has_remote else {}
    local = local_entries(show)
    base = _load_base(repo)

    local_hash = {p: _h(f.read_bytes()) for p, f in local.items()}
    remote_hash: dict[str, str] = {}
    for p in remote:
        remote_hash[p] = _h(_remote_bytes(repo, p))

    push: list[dict] = []
    pull: list[dict] = []
    conflicts: list[dict] = []
    in_sync = 0
    for p in sorted(set(local_hash) | set(remote_hash)):
        lh, rh, bh = local_hash.get(p), remote_hash.get(p), base.get(p)
        if lh == rh:
            in_sync += 1
            continue
        if rh is None:
            push.append({"path": p, "reason": "new here"})
        elif lh is None:
            pull.append({"path": p, "reason": "new on the other Studio"})
        elif rh == bh:
            push.append({"path": p, "reason": "changed here"})
        elif lh == bh:
            pull.append({"path": p, "reason": "changed on the other Studio"})
        else:
            local_ts = local[p].stat().st_mtime
            remote_ts = _remote_commit_ts(repo, p)
            winner = "local" if local_ts >= remote_ts else "remote"
            conflicts.append({"path": p, "winner": winner,
                              "local_ts": local_ts, "remote_ts": remote_ts})
    return {"show": show, "push": push, "pull": pull, "conflicts": conflicts,
            "in_sync": in_sync, "remote_empty": not has_remote,
            "clean": not (push or pull or conflicts), "log": fetch_log}


# ---- apply ------------------------------------------------------------------------

def apply(show: str, message: str | None = None) -> dict:
    """Recompute the plan and execute it: pull writes local files (with .bak),
    push commits sync/ updates and pushes. Base snapshot updated at the end."""
    base_url, token = _creds()
    p = plan(show)
    repo = _repo(show)
    local = local_entries(show)
    log: list[str] = [p["log"]]
    pulled: list[str] = []
    pushed: list[str] = []
    backed_up: list[str] = []
    errors: list[str] = []

    pulls = list(p["pull"]) + [c for c in p["conflicts"] if c["winner"] == "remote"]
    pushes = list(p["push"]) + [c for c in p["conflicts"] if c["winner"] == "local"]

    # ---- pulls: remote → local files
    for item in pulls:
        path = item["path"]
        try:
            data = _remote_bytes(repo, path)
            reason = _validate_pull(path, data)
            if reason:
                errors.append(f"{path}: refused — {reason}")
                continue
            dest = _local_dest(show, path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and dest.read_bytes() != data:
                bak = dest.with_name(dest.name + f".bak.{time.strftime('%Y%m%d-%H%M%S')}")
                dest.replace(bak)
                backed_up.append(str(bak))
            tmp = dest.with_name(dest.name + ".sync-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            pulled.append(path)
        except Exception as e:
            errors.append(f"{path}: pull failed — {e}")

    # ---- pushes: local files → sync/ in the repo, commit, push
    if pushes:
        if not p["remote_empty"]:
            _git(repo, "reset", "--hard", "FETCH_HEAD")
        for item in pushes:
            path = item["path"]
            src = local.get(path)
            if not src or not src.exists():
                errors.append(f"{path}: push skipped — local file vanished")
                continue
            dest = repo / SYNC_PREFIX / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            pushed.append(path)
        if pushed:
            _git(repo, "add", "--", "sync")
            msg = (message or f"sync from {_hostname()}").strip()
            c = _git(repo, "commit", "-m", msg)
            if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
                errors.append(f"commit failed: {_redact(c.stderr or c.stdout, token)[:300]}")
            else:
                push_r = _git(repo, "push", _token_url(base_url, token, show), "HEAD:main")
                if push_r.returncode != 0:
                    errors.append(f"push failed: {_redact(push_r.stderr or push_r.stdout, token)[:300]}")
                    pushed = []
                else:
                    log.append(f"pushed {len(pushed)} file(s)")

    # ---- refresh the base snapshot for everything now in agreement
    try:
        has_remote, _ = _fetch(repo, show, base_url, token)
        remote = _remote_tree(repo) if has_remote else {}
        local2 = local_entries(show)
        base: dict[str, str] = {}
        for path in set(remote) | set(local2):
            lh = _h(local2[path].read_bytes()) if path in local2 else None
            rh = _h(_remote_bytes(repo, path)) if path in remote else None
            if lh and rh and lh == rh:
                base[path] = lh
        _save_base(repo, base)
    except Exception as e:
        errors.append(f"base snapshot refresh failed: {e}")

    # Record pulled/pushed episode text into the local episode_meta history repo
    # (keeps the script-version timeline intact across machines). Best-effort.
    touched_slugs = sorted({x.split("/")[1] for x in pulled + pushed
                            if x.startswith("episodes/")})
    for slug in touched_slugs:
        try:
            gitsync.sync(slug, message=f"sync: {show} via macu-web")
        except Exception:
            pass

    return {"ok": not errors, "pulled": pulled, "pushed": pushed,
            "conflicts_resolved": [c["path"] for c in p["conflicts"]],
            "backed_up": backed_up, "errors": errors,
            "touched_episodes": touched_slugs, "log": "\n".join(log)}
