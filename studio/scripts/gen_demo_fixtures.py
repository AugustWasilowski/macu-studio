#!/usr/bin/env python3
"""Generate static demo fixtures for the macu-web Studio demo.

The demo serves Studio's REAL production frontend build, but with no backend:
a Service Worker (studio/demo/sw.js) intercepts every /api/* call and serves the
JSON + media this script bakes out of a real, fully-rendered episode.

We reuse the exact same backend derive functions the live API calls
(macu_studio.manifest.derive_*, episode_pipeline_status, etc.) so the fixtures
never drift from the real data shapes. System endpoints (activity, sysstat,
version, ...) are canned to a healthy/idle box.

Layout written under <out>/data/:
    api/<mirror of the GET URL path>.json   # one file per read endpoint
    media/...                               # copied/transcoded binaries
    media-map.json                          # request-path (no query) -> media file

Run:  PYTHONPATH=studio/backend python studio/scripts/gen_demo_fixtures.py ep-005 --out <dir>

Tolerant by design: a missing input warns and is skipped rather than aborting,
so the script survives episode-to-episode differences and Studio data-model drift.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import macu_studio.episodes as ep_mod
import macu_studio.manifest as mf_mod
import macu_studio.script as script_mod
from macu_studio.config import SHARES


def warn(msg: str) -> None:
    print(f"  ! {msg}", file=sys.stderr)


def write_json(root: Path, url_path: str, payload) -> None:
    """Write `payload` to <root>/data/api/<url_path>.json (mirrors the GET URL)."""
    dest = root / "data" / "api" / (url_path.strip("/") + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2))


def ffprobe_duration(p: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(p)],
            capture_output=True, text=True, timeout=30,
        )
        return round(float(out.stdout.strip()), 3)
    except Exception as e:  # noqa: BLE001
        warn(f"ffprobe failed for {p.name}: {e}")
        return None


# ---- shot media resolution: mirror main.py get_shot_preview() candidate order ----
def resolve_shot_file(ep_dir: Path, key: str) -> Path | None:
    candidates = [
        ep_dir / "clips" / f"{key}_master.zs.webp",
        ep_dir / "clips" / f"broll_{key}.zs.webp",
    ]
    if key == "safe":
        candidates.insert(0, ep_dir / "clips" / "safe_master.zs.webp")
    if key == "empty_room":
        candidates.insert(0, ep_dir / "clips" / "c09_s1.zs.webp")
    return next((c for c in candidates if c.exists()), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?", default="ep-005")
    ap.add_argument("--out", required=True, help="staging dir (data/ is written under it)")
    ap.add_argument("--show", default="the-macu-report")
    args = ap.parse_args()
    slug = args.slug

    out = Path(args.out)
    media = out / "data" / "media"
    media.mkdir(parents=True, exist_ok=True)
    ep_dir = ep_mod.episode_dir(slug)
    print(f">>> fixtures for {slug}  ({ep_dir})  ->  {out}")

    manifest = mf_mod.load(slug)
    media_map: dict[str, str] = {}

    def copy_media(src: Path, rel: str, request_path: str) -> None:
        if not src.exists():
            warn(f"missing media {src}")
            return
        dest = media / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        media_map[request_path] = f"media/{rel}"

    # ---------------- episode-derived read endpoints (real shapes) ----------------
    # /api/episodes — demo shows ONLY this one episode.
    summaries = [e for e in ep_mod.list_episodes(args.show) if e.slug == slug]
    if not summaries:
        warn(f"{slug} not in list_episodes({args.show}); synthesizing a summary")
        summaries = [ep_mod.EpisodeSummary(
            slug=slug, title=manifest.get("title", slug),
            modified_iso="2026-05-30T15:35:00-05:00", done_stages=8,
            season=1, episode_num=5, se_label="S01-E5", synced=True,
            show=args.show, published=True)]
    summaries[0].done_stages = 8  # fully rendered for the demo
    write_json(out, "episodes", {"episodes": [s.__dict__ for s in summaries]})

    base = f"episodes/{slug}"
    write_json(out, f"{base}/manifest", manifest)
    write_json(out, f"{base}/script", script_mod.read(slug))
    write_json(out, f"{base}/cues", {"cues": mf_mod.derive_cues(slug)})
    write_json(out, f"{base}/shots", {"shots": mf_mod.derive_shots(slug)})
    write_json(out, f"{base}/titles", {"titles": mf_mod.derive_titles(slug)})
    write_json(out, f"{base}/pipeline/active", {"job_id": None})
    write_json(out, f"{base}/script/versions", {"versions": [
        {"id": "working", "kind": "working", "label": "Working copy", "short": None, "iso": None}]})
    write_json(out, f"{base}/localize", {
        "rendered": False,
        "engines": [{"id": "argos", "caveat": "offline NMT"}, {"id": "qwen", "caveat": "LLM"}],
        "languages": []})

    # Pipeline: this episode IS fully rendered (its final assets are named ep5.* not
    # {slug}.*, so the live status check reads some stages as idle). Force all done.
    stages = mf_mod.episode_pipeline_status(slug)
    for s in stages:
        s["status"] = "done"
        if not s.get("note"):
            s["note"] = "rendered"
    write_json(out, f"{base}/pipeline", {"stages": stages})

    # ---------------- final video / thumb / srt (named ep5.*, handled explicitly) ----
    final_dir = ep_dir / "final"
    src_final = final_dir / "ep5.mp4"
    src_thumb = final_dir / "ep5_thumbs.jpg"
    src_srt = final_dir / "ep5.srt"

    duration = ffprobe_duration(src_final) if src_final.exists() else None
    if src_final.exists():
        dest_final = media / "final.mp4"
        print("    transcoding final -> 480p (this takes a bit)…")
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src_final), "-vf", "scale=-2:480",
             "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
             "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dest_final)],
            capture_output=True, text=True)
        if r.returncode != 0:
            warn(f"final transcode failed, copying original: {r.stderr[-400:]}")
            shutil.copy2(src_final, dest_final)
        media_map[f"/api/{base}/final/video"] = "media/final.mp4"
        size_mb = round(dest_final.stat().st_size / 1_048_576, 1)
    else:
        warn("no final mp4")
        size_mb = None

    copy_media(src_thumb, "final-thumb.jpg", f"/api/{base}/final/thumb")
    write_json(out, f"{base}/final", {
        "exists": src_final.exists(),
        "path": f"final/{slug}.mp4",
        "size_mb": size_mb,
        "duration_s": duration,
        "mtime": int(src_final.stat().st_mtime) if src_final.exists() else None,
        "thumb_exists": src_thumb.exists(),
        "srt_exists": src_srt.exists(),
    })

    # SRT — parse ep5.srt directly into {text, entries[], exists}.
    if src_srt.exists():
        write_json(out, f"{base}/srt", parse_srt(src_srt.read_text()))
    else:
        warn("no srt")
        write_json(out, f"{base}/srt", {"text": "", "entries": [], "exists": False})

    # ---------------- media: per-cue VO, per-shot preview, per-title preview ----------
    for cue in mf_mod.derive_cues(slug):
        if cue.get("wav_exists"):
            copy_media(ep_dir / "vo" / f"{cue['id']}.wav", f"vo/{cue['id']}.wav",
                       f"/api/{base}/cue/{cue['id']}/audio")
    for shot in mf_mod.derive_shots(slug):
        if shot.get("webp_exists"):
            src = resolve_shot_file(ep_dir, shot["key"])
            if src:
                copy_media(src, f"shots/{shot['key']}.webp",
                           f"/api/{base}/shot/{shot['key']}/preview")
            else:
                warn(f"shot {shot['key']} marked rendered but no file resolved")
    for title in mf_mod.derive_titles(slug):
        if title.get("exists"):
            src = ep_dir / "titles" / f"{title['key']}.mp4"
            if not src.exists():
                src = SHARES / "assets" / "titles" / f"{title['key']}.mp4"
            copy_media(src, f"titles/{title['key']}.mp4",
                       f"/api/{base}/title/{title['key']}/preview")

    (out / "data" / "media-map.json").write_text(json.dumps(media_map, indent=2))

    # ---------------- canned system endpoints (healthy / idle / up-to-date) ----------
    speaker_map = (manifest.get("voice") or {}).get("speaker_map") or {}
    profiles = [{"id": (v.get("profile_id") or k).lower(),
                 "name": v.get("voice_name") or k.title()}
                for k, v in speaker_map.items()] or [{"id": "ron", "name": "Ron"}]

    canned = {
        "health": {"ok": True, "episodes_dir": "/demo", "render_url": "demo"},
        "activity": {"state": "idle", "label": ""},
        "sysstat": {"cpu_pct": 4.0, "gpu_pct": 0.0, "gpu_mem_used_mib": 512,
                    "gpu_mem_total_mib": 11264, "disk_read_mibps": 0.0,
                    "disk_write_mibps": 0.0, "disk_busy_pct": 0.0, "disk_dev": "demo"},
        "version": {
            "current": {"commit": "demo000000000000", "short": "demo000", "branch": "main",
                        "subject": "Demo build", "committed_iso": "2026-06-07T00:00:00-05:00",
                        "dirty": False, "upstream": "origin/main", "can_autorestart": False},
            "check": {"ts": None, "behind": 0, "ahead": 0, "update_available": False,
                      "incoming": [], "remote_short": None, "error": None, "upstream": "origin/main"},
            "update": {"phase": "idle", "log": [], "error": None, "started": None}},
        "shows": {"shows": [{"id": args.show, "name": manifest.get("show_name", "The MACU Report"),
                             "episodes_dir": "/demo", "assets_dir": None,
                             "title_prefix": "The MACU Report — ", "episode_count": 1,
                             "is_default": True}], "default": args.show},
        "voices": {"running": True, "cached": True, "profiles": profiles},
        "card-types": {"card_types": ["cold-open", "sponsor", "sign-off", "lower-third"]},
        "macu-web/status": {"connected": False, "base": None},
        "docs": {"docs": []},
        "youtube/uploads": {"uploads": []},
        "youtube/matches": {"matches": {}, "episodes": [{"slug": slug, "title": manifest.get("title", slug)}]},
        "youtube/auth": {"has_client": False, "connected": False},
        "hf/templates": {"templates": ["title-card", "lower-third", "bumper"]},
    }
    for path, payload in canned.items():
        write_json(out, path, payload)

    print(f">>> done: {len(media_map)} media files, fixtures under {out/'data'/'api'}")
    return 0


def parse_srt(text: str) -> dict:
    entries = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        try:
            idx = int(lines[0])
        except ValueError:
            continue
        if "-->" not in lines[1]:
            continue
        start, end = (p.strip() for p in lines[1].split("-->"))
        entries.append({"i": idx, "start": start, "end": end, "text": "\n".join(lines[2:])})
    return {"text": text, "entries": entries, "exists": True}


if __name__ == "__main__":
    raise SystemExit(main())
