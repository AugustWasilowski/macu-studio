"""Publish a show's TEXT bundle to its macu-web (mayorawesome.com) git repo.

This *reuses the export enumeration* (routes_shows helpers) to decide which files travel
with a show, but writes the TEXT subset into a per-show git working tree (in the same arc
layout an export ZIP uses) and pushes to the show's bare repo on macu-web. Binaries
(voice .wav / sfx / music / rendered media) are never published — macu-web hosts text only;
a recipient re-sources audio via the provenance READMEs and re-clones voices by name.

Because the committed tree matches the export bundle layout (episodes/<slug>/…, show.json,
voices.json, referenced hyperframes templates, docs/ canon, export.json), macu-web's
"Riff this show" download is literally `git archive HEAD`, which Studio's /api/import accepts.

Remote/creds: env MACU_WEB_GIT_BASE + MACU_WEB_TOKEN, else ~/.config/macu-studio/macu-web.json
{"base": "http://10.0.0.245:8776", "token": "macu_…"}. The token is a macu-web PAT (used as the
git Basic-auth password); it is sent in a one-off push URL and never written into .git/config.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import config
from . import shows as shows_mod
from . import validate as validate_mod
from .routes_shows import (
    TEXT_FILES,
    EXPORT_VERSION,
    HYPERFRAMES_TEMPLATES,
    TEMPLATE_ARC_PREFIX,
    SFX_DIR,
    MUSIC_DIR,
    SFX_ARC_PREFIX,
    MUSIC_ARC_PREFIX,
    _manifest_template_names,
    _manifest_voice_names,
    _manifest_audio_files,
)

# Per-show macu-web publish repos live here (separate from the local episode_meta backup).
PUBLISH_ROOT = Path(os.environ.get("MACU_WEB_PUBLISH_ROOT", str(config.REPO_ROOT / ".macu-web-repos")))
# Canon docs (character bible, story arcs, routines, voice roster) — all text, support riffing.
DOCS_ROOT = config.REPO_ROOT / "docs" / "shows"
# Only text travels to macu-web.
TEXT_EXT = {".md", ".json", ".txt", ".html", ".htm", ".css", ".js", ".svg", ".csv", ".yaml", ".yml"}


def _creds() -> tuple[str | None, str | None]:
    base = os.environ.get("MACU_WEB_GIT_BASE", "").strip().rstrip("/") or None
    token = os.environ.get("MACU_WEB_TOKEN", "").strip() or None
    if base and token:
        return base, token
    cfg = Path.home() / ".config" / "macu-studio" / "macu-web.json"
    if cfg.exists():
        try:
            d = json.loads(cfg.read_text())
            base = base or str(d.get("base") or "").strip().rstrip("/") or None
            token = token or str(d.get("token") or "").strip() or None
        except Exception:
            pass
    return base, token


def text_bundle_entries(show: str) -> dict[str, bytes]:
    """{arcname: bytes} of the TEXT files that should be version-controlled for `show`,
    in export-bundle layout. Raises KeyError if the show is unknown."""
    cfg = shows_mod.get_show(show)
    ep_root = Path(cfg["episodes_dir"])
    entries: dict[str, bytes] = {}

    entries["show.json"] = json.dumps(cfg, indent=2, ensure_ascii=False).encode()

    slugs: list[str] = []
    templates: set[str] = set()
    voice_names: set[str] = set()
    sfx: set[str] = set()
    music: set[str] = set()

    if ep_root.exists():
        for ep in sorted((p for p in ep_root.iterdir() if p.is_dir()), key=lambda p: p.name):
            if not (ep / "manifest.json").exists():
                continue
            slugs.append(ep.name)
            for name in TEXT_FILES:
                # Scripts stay private — never ship script.md to the public macu-web repo.
                if name == "script.md":
                    continue
                f = ep / name
                if f.exists():
                    entries[f"episodes/{ep.name}/{name}"] = f.read_bytes()
            templates |= _manifest_template_names(ep)
            voice_names |= _manifest_voice_names(ep)
            s, m = _manifest_audio_files(ep)
            sfx |= s
            music |= m

    # Referenced hyperframes title-card templates — TEXT files only.
    for tname in sorted(templates):
        tdir = HYPERFRAMES_TEMPLATES / tname
        if not tdir.is_dir():
            continue
        for f in sorted(tdir.rglob("*")):
            if f.is_file() and f.suffix.lower() in TEXT_EXT:
                rel = f.relative_to(HYPERFRAMES_TEMPLATES).as_posix()
                entries[f"{TEMPLATE_ARC_PREFIX}{rel}"] = f.read_bytes()

    # Asset provenance READMEs (how each sfx/music was sourced) — text catalogs.
    for src, arc in ((SFX_DIR / "README.md", f"{SFX_ARC_PREFIX}README.md"),
                     (MUSIC_DIR / "README.md", f"{MUSIC_ARC_PREFIX}README.md")):
        if src.is_file():
            entries[arc] = src.read_bytes()

    # Voice mapping (names only — the .wav refs are binary and never published).
    if voice_names:
        entries["voices.json"] = json.dumps(
            {"voices": [{"name": n, "language": "English"} for n in sorted(voice_names)]},
            indent=2,
        ).encode()

    # Canon docs (character prompt bible + arcs/routines/roster) — text, enables riffing.
    docs_dir = DOCS_ROOT / show
    if docs_dir.is_dir():
        for f in sorted(docs_dir.glob("*.md")):
            entries[f"docs/shows/{show}/{f.name}"] = f.read_bytes()

    # Import marker (no timestamp — a stable bundle so re-publishing only diffs real changes).
    entries["export.json"] = json.dumps(
        {"kind": "show", "show": show, "name": cfg.get("name"),
         "episodes": slugs, "version": EXPORT_VERSION},
        indent=2,
    ).encode()
    return entries


def _git_env() -> dict[str, str]:
    """Environment for Studio's own git calls, with any inherited global SSH override
    stripped. A machine-wide ``GIT_SSH_COMMAND``/``GIT_SSH`` hijacks *every* git-over-ssh on
    the box (e.g. a stray ``-p <port>`` meant for one host silently forces GitHub onto that
    port and times out). We refuse to inherit it so Studio stays self-contained — even though
    the macu-web push itself is HTTPS — and never propagates one. Per-host needs belong in
    ``~/.ssh/config``, which git's default ssh honors regardless."""
    env = os.environ.copy()
    env.pop("GIT_SSH_COMMAND", None)
    env.pop("GIT_SSH", None)
    return env


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, env=_git_env())


def _previous_slugs(repo: Path) -> list[str] | None:
    """Episode slugs in the repo's last-published bundle (HEAD's export.json), or None when
    the repo has no history yet (first publish of the show — nothing to guard against)."""
    head = _git(repo, "show", "HEAD:export.json")
    if head.returncode != 0:
        return None
    try:
        return list(json.loads(head.stdout).get("episodes") or [])
    except Exception:
        return None


def publish(show: str, message: str | None = None,
            allow_new_public: list[str] | None = None) -> dict:
    """Write the text bundle into the show's macu-web repo, commit, and push (if creds set)."""
    try:
        entries = text_bundle_entries(show)
    except KeyError as e:
        return {"ok": False, "log": f"unknown show: {e}"}

    repo = PUBLISH_ROOT / show
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, text=True, capture_output=True)

    # Sync (studiosync.py) commits from OTHER Studios may have advanced the
    # remote; integrate them first or this publish would push non-fast-forward
    # (and the rewrite below would clobber the synced sync/ subtree).
    base0, token0 = _creds()
    if base0 and (token0 or base0.startswith("file://")):
        url0 = (f"{base0}/{show}.git" if base0.startswith("file://")
                else f"{base0.replace('://', f'://macu:{token0}@', 1)}/{show}.git")
        f = _git(repo, "fetch", url0, "main")
        if f.returncode == 0:
            _git(repo, "reset", "--hard", "FETCH_HEAD")

    # Guard: an episode dir the repo has NEVER published whose manifest already says
    # published:true would seed PUBLIC on macu-web's first index of it (visibility is seeded
    # once, on row creation, and the show page filters on it). Stray working dirs — legacy
    # slug families, dub scratch dirs — must not go live just because they sit in episodes/
    # with a stale flag; that is exactly how ep5..ep10 (+ -hi/-uk) tripled Season 1 on
    # 2026-06-11. Hold such episodes back unless explicitly allowed. New DRAFTS (published
    # unset) still travel: they seed PRIVATE, which is harmless.
    prev = _previous_slugs(repo)
    skipped_new: list[str] = []
    if prev is not None:
        allow = {str(s) for s in (allow_new_public or [])}
        exp = json.loads(entries["export.json"].decode())
        for slug in [s for s in exp["episodes"] if s not in prev and s not in allow]:
            man = entries.get(f"episodes/{slug}/manifest.json")
            try:
                published = bool(json.loads(man.decode()).get("published")) if man else False
            except Exception:
                published = True  # unparseable manifest — hold it back rather than ship it
            if not published:
                continue
            skipped_new.append(slug)
            for arc in [a for a in entries if a.startswith(f"episodes/{slug}/")]:
                del entries[arc]
            exp["episodes"].remove(slug)
        if skipped_new:
            entries["export.json"] = json.dumps(exp, indent=2).encode()

    # Best-effort early feedback (macu-web is the authoritative gate; see validate.py).
    warnings = validate_mod.bundle_warnings(entries)
    if skipped_new:
        warnings.append(
            "HELD BACK new published episode(s) never seen by this repo: "
            + ", ".join(skipped_new)
            + " — a first-time publish of an already-published episode goes straight to "
            "PUBLIC on macu-web. Re-run with allow_new_public: [\"<slug>\", …] to ship them "
            "deliberately, or clear their manifest `published` flag if they are strays."
        )

    # Rewrite the working tree from scratch (handles adds/edits/deletes) — keep
    # .git AND the sync/ subtree (Studio↔Studio working text; owned by
    # studiosync.py, riff-excluded on macu-web, never part of the publish bundle).
    for child in repo.iterdir():
        if child.name in (".git", "sync"):
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    for arc, data in entries.items():
        dest = repo / arc
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    log: list[str] = [f"files: {len(entries)}"]
    _git(repo, "add", "-A")
    commit = _git(repo, "commit", "-m", (message or f"publish {show}").strip())
    committed = commit.returncode == 0
    if not committed and "nothing to commit" not in (commit.stdout + commit.stderr):
        return {"ok": False, "log": "\n".join(log + [commit.stdout, commit.stderr])}
    log.append("committed" if committed else "no changes")

    pushed = False
    base, token = _creds()
    if base and token:
        url = f"{base.replace('://', f'://macu:{token}@', 1)}/{show}.git"
        push = _git(repo, "push", url, "HEAD:main")
        pushed = push.returncode == 0
        # Redact the token from any surfaced log.
        log.append((push.stderr or push.stdout or "").replace(token, "***") or ("pushed" if pushed else "push failed"))
    else:
        log.append("(no macu-web creds — committed locally only)")

    return {"ok": (pushed if (base and token) else True), "committed": committed,
            "pushed": pushed, "files": len(entries), "repo": str(repo),
            "skipped_new_episodes": skipped_new,
            "warnings": warnings, "log": "\n".join(log)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python -m macu_studio.publish <show> [message]", file=sys.stderr)
        sys.exit(2)
    res = publish(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(res, indent=2))
    sys.exit(0 if res["ok"] else 1)
