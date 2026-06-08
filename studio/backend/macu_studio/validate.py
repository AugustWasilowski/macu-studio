"""Best-effort content validation, mirroring macu-web's enforcement (src/lib/sanitize.ts).

Studio is OPEN SOURCE, so this is **not** a security boundary — anyone can push straight to
the git endpoint. macu-web (closed source) is the authoritative gate; this layer just gives
creators early feedback in the Publish UI so they don't ship content the web will clamp/skip.

KEEP THESE LIMITS IN SYNC with macu-web's src/lib/sanitize.ts (macu-web is authoritative).
"""
from __future__ import annotations

import json
import re

LIMITS = {
    "title": 200,
    "synopsis": 600,  # manifest `notes`
    "authored_by": 120,
    "char_name": 80,
    "char_core": 2000,
    "slug": 64,
    "max_episodes": 500,
    "max_characters": 1000,
}

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


def is_valid_video_id(s) -> bool:
    return isinstance(s, str) and bool(_VIDEO_ID.match(s))


def is_valid_episode_slug(s) -> bool:
    return isinstance(s, str) and bool(_SLUG.match(s))


def _keep(ch: str) -> bool:
    o = ord(ch)
    # Keep TAB and LF; drop the rest of C0 (<32), DEL (127), and C1 (128-159).
    return ch in ("\t", "\n") or (o >= 32 and o != 127 and not (0x80 <= o <= 0x9F))


def clamp_text(v, max_len: int) -> "str | None":
    """Trim, strip control chars, truncate to max_len (… suffix). None if empty."""
    if v is None:
        return None
    s = "".join(ch for ch in str(v) if _keep(ch)).strip()
    if not s:
        return None
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def bundle_warnings(entries: dict[str, bytes]) -> list[str]:
    """Scan a publish bundle ({arcname: bytes}) for fields macu-web will clamp/skip.
    Returns human-readable, non-blocking warnings (capped)."""
    warns: list[str] = []
    manifests = [
        (k, v) for k, v in entries.items()
        if k.startswith("episodes/") and k.endswith("/manifest.json")
    ]
    if len(manifests) > LIMITS["max_episodes"]:
        warns.append(f"{len(manifests)} episodes exceeds the {LIMITS['max_episodes']} cap — extras dropped on the web.")

    str_fields = (("title", "title"), ("description", "synopsis"), ("authored_by", "authored_by"))
    manifest_key = {"title": "title", "synopsis": "notes", "authored_by": "authored_by"}

    for arc, data in manifests:
        slug = arc.split("/")[1]
        if not is_valid_episode_slug(slug):
            warns.append(f"{slug}: invalid episode slug — skipped on the web.")
        try:
            m = json.loads(data)
        except Exception:
            warns.append(f"{slug}: manifest.json is not valid JSON.")
            continue
        for label, limit_key in str_fields:
            v = m.get(manifest_key[limit_key])
            if isinstance(v, str) and len(v) > LIMITS[limit_key]:
                warns.append(f"{slug}: {label} is {len(v)} chars (clamped to {LIMITS[limit_key]} on the web).")
        yt = (m.get("youtube") or {}).get("video_id") if isinstance(m.get("youtube"), dict) else None
        if yt and not is_valid_video_id(yt):
            warns.append(f"{slug}: youtube.video_id isn't a valid 11-char id — the web won't embed it.")
        chars = m.get("characters")
        if isinstance(chars, dict) and len(chars) > LIMITS["max_characters"]:
            warns.append(f"{slug}: {len(chars)} characters exceeds the {LIMITS['max_characters']} cap.")
    return warns[:50]
