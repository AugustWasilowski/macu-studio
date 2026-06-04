#!/usr/bin/env python3
"""Rename episode dirs from ep<N> / EP<N> to ep-<NNN>.

Skips Commercials, everwell-bit, and any dir whose name contains 'backup'.
Updates each renamed dir's manifest.json `episode` field to match.

Usage:
    rename_episodes.py            # dry run (default)
    rename_episodes.py --commit   # actually do it
"""
from __future__ import annotations
import argparse, json, os, re, shutil, sys
from pathlib import Path

EPISODES = Path(os.environ.get("MACU_EPISODES", "/mnt/storage/shares/MACU/episodes"))
PATTERN = re.compile(r"^[Ee][Pp](\d+)$")  # ep5, EP2 — no separator


def plan() -> list[tuple[Path, Path]]:
    """Return list of (old_path, new_path) for dirs that should be renamed."""
    if not EPISODES.is_dir():
        sys.exit(f"episodes dir not found: {EPISODES}")
    moves: list[tuple[Path, Path]] = []
    for entry in sorted(EPISODES.iterdir()):
        if not entry.is_dir():
            continue
        if "backup" in entry.name.lower():
            continue
        m = PATTERN.match(entry.name)
        if not m:
            continue
        n = int(m.group(1))
        new_name = f"ep-{n:03d}"
        if new_name == entry.name:
            continue
        moves.append((entry, entry.parent / new_name))
    return moves


def update_manifest(path: Path, new_slug: str) -> str | None:
    """Update manifest.json's `episode` field to new_slug. Returns old value or None if no change."""
    mf = path / "manifest.json"
    if not mf.exists():
        return None
    try:
        data = json.loads(mf.read_text())
    except Exception as e:
        print(f"  ! cannot parse {mf}: {e}", file=sys.stderr)
        return None
    old = data.get("episode")
    if old == new_slug:
        return None
    data["episode"] = new_slug
    # Atomic-ish write
    tmp = mf.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(mf)
    return old


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="Actually perform the rename + manifest patch")
    args = ap.parse_args()
    moves = plan()
    if not moves:
        print("Nothing to do — all episodes already in the new shape.")
        return
    print(f"{'COMMIT' if args.commit else 'DRY RUN'} — {len(moves)} dir(s):")
    for old, new in moves:
        print(f"  {old.name:20s} → {new.name}")
    if not args.commit:
        print("\nRe-run with --commit to apply.")
        return
    print()
    for old, new in moves:
        if new.exists():
            print(f"  ! target exists, skipping: {new}")
            continue
        old.rename(new)
        upd = update_manifest(new, new.name)
        msg = f"  ✓ {old.name} → {new.name}"
        if upd is not None:
            msg += f"  (manifest.episode: {upd!r} → {new.name!r})"
        elif (new / "manifest.json").exists():
            msg += "  (manifest.episode already matched or no change needed)"
        else:
            msg += "  (no manifest.json)"
        print(msg)
    print("\nDone.")


if __name__ == "__main__":
    main()
