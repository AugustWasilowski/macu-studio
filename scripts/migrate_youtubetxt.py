#!/usr/bin/env python3
"""One-time: fold youtube.txt into manifest.json, then delete youtube.txt.

- manifest.youtube.video_id  ← the video id parsed from youtube.txt (if not already set)
- manifest.notes             ← the youtube.txt DESCRIPTION paragraph (only if notes is empty)
Idempotent: skips episodes with no youtube.txt; safe to re-run.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/mnt/storage/macu-pipeline/studio/backend")
from macu_studio import shows as S, manifest as M, episodes as E  # noqa: E402


def extract_desc(text: str) -> str | None:
    out: list[str] = []
    grab = False
    for ln in text.splitlines():
        s = ln.strip()
        if not grab:
            if s.upper().startswith("DESCRIPTION"):
                grab = True
            continue
        if s and set(s) <= set("-="):  # divider line
            continue
        if s.upper().startswith(("TAGS", "HASHTAG", "TITLE")):
            break
        if s.isupper() and 0 < len(s) < 40 and out:  # next section header
            break
        out.append(ln)
    desc = "\n".join(out).strip()
    return desc or None


migrated_vid = seeded_notes = deleted = 0
for show in S.list_shows():
    try:
        root = Path(S.get_show(show["id"])["episodes_dir"])
    except Exception:
        continue
    if not root.exists():
        continue
    for ep in sorted(p for p in root.iterdir() if p.is_dir()):
        mf, yt = ep / "manifest.json", ep / "youtube.txt"
        if not mf.exists() or not yt.exists():
            continue
        try:
            data = json.loads(mf.read_text())
        except Exception:
            print("skip (bad manifest):", ep.name)
            continue
        changed = False
        vid = E.youtube_id_of(ep)
        if vid and not (data.get("youtube") or {}).get("video_id"):
            data.setdefault("youtube", {})["video_id"] = vid
            migrated_vid += 1
            changed = True
        if not data.get("notes"):
            desc = extract_desc(yt.read_text(errors="ignore"))
            if desc:
                data["notes"] = desc
                seeded_notes += 1
                changed = True
        if changed:
            M.save(ep.name, data)  # validates + writes
        yt.unlink()
        deleted += 1

print(f"migrated video_id: {migrated_vid}  seeded notes: {seeded_notes}  youtube.txt deleted: {deleted}")
