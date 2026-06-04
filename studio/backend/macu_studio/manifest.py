"""Manifest read/write + derived asset status."""
from __future__ import annotations
import hashlib, json, os, tempfile, time
from pathlib import Path
from typing import Any

from .episodes import episode_dir, manifest_path
from . import models


def load(slug: str) -> dict[str, Any]:
    return json.loads(manifest_path(slug).read_text())


def load_typed(slug: str) -> "models.Manifest":
    """Typed view of the manifest (for new code that wants attribute access)."""
    return models.parse(load(slug))


def save(slug: str, data: dict[str, Any], validate: bool = True) -> dict[str, Any]:
    """Atomic write: tmp file in same dir → rename.

    When `validate` is true, the dict is structurally validated through the
    pydantic models first (raises ValueError if malformed). The ORIGINAL raw
    `data` dict is persisted — never `model_dump()` — so LOCKED blocks
    (comfyui/subtitles) stay byte-identical.
    """
    path = manifest_path(slug)
    if validate:
        models.validate(data)
    # Validate that it's serializable round-trip.
    blob = json.dumps(data, indent=2, ensure_ascii=False)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o664
    fd, tmp = tempfile.mkstemp(prefix=".manifest.", suffix=".json.tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(blob)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"path": str(path), "mtime": path.stat().st_mtime, "bytes": len(blob)}


def _vo_cache_path(slug: str) -> Path:
    return episode_dir(slug) / "vo" / ".cache.json"


def _vo_cache(slug: str) -> dict[str, Any]:
    p = _vo_cache_path(slug)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _resolve_voice(voice: dict, speaker: str) -> dict:
    """Mirror pipeline/stage_1_vo.py::_resolve_voice."""
    vmap = (voice or {}).get("speaker_map") or {}
    if speaker in vmap:
        return vmap[speaker]
    return (voice or {}).get("default", {"engine": "piper"})


def _cue_hash(cue: dict, voice: dict) -> str:
    """16-hex cue hash. MUST stay byte-for-byte identical to
    pipeline/stage_1_vo.py::_cue_cache_key so the Studio recognizes the cache the
    pipeline writes to vo/.cache.json. If you change one, change BOTH. (Note: keys
    are 'vo'/'speaker' un-stripped — do not normalize, or hashes diverge.)"""
    hold = cue.get("hold_seconds")
    if hold is not None:
        payload = {"hold_seconds": float(hold)}
    else:
        vcfg = _resolve_voice(voice, cue.get("speaker") or "")
        payload = {
            "vo": cue.get("vo") or "",
            "speaker": cue.get("speaker") or "",
            "engine": vcfg.get("engine"),
            "profile_id": vcfg.get("profile_id"),
            "voice_name": vcfg.get("voice_name"),
            "speed": vcfg.get("speed"),
            "guidance_scale": vcfg.get("guidance_scale"),
            "seed": vcfg.get("seed"),
            "instruct": vcfg.get("instruct"),
        }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def derive_cues(slug: str, manifest: dict | None = None) -> list[dict]:
    """Flatten manifest.cues + filesystem state into UI-ready rows."""
    m = manifest or load(slug)
    ep = episode_dir(slug)
    vo_dir = ep / "vo"
    voice_block = m.get("voice") or {}
    speaker_map = voice_block.get("speaker_map") or {}

    rows: list[dict] = []
    for cue in m.get("cues") or []:
        cid = cue.get("id")
        speaker = cue.get("speaker") or ""
        text = cue.get("vo") or ""
        is_hold = not text and "hold_seconds" in cue
        wav = vo_dir / f"{cid}.wav"
        status: str
        duration: float | None = None
        if is_hold:
            # HOLD cues: silent placeholder; 'generated' once a wav exists.
            status = "generated" if wav.exists() else "missing"
            duration = float(cue.get("hold_seconds") or 0.0)
        else:
            # An existing wav is "generated". We deliberately do NOT hash-compare for
            # staleness here: the pipeline's vo/.cache.json hashes were written by
            # whatever hash scheme was current at render time (episodes 5-10 predate the
            # speed/guidance/seed/instruct fields in _cue_cache_key), so comparing them
            # to the current hash produces false "stale" for fully-generated assets. The
            # pipeline still does correct hash-based regen at render time; Studio status
            # just reflects existence. (_cue_hash is kept aligned for a future studio-owned
            # fresh-hash sidecar that could restore edit-staleness — see plan.)
            status = "generated" if wav.exists() else "missing"
        voice = _resolve_voice(voice_block, speaker)
        rows.append({
            "id": cid,
            "speaker": speaker,
            "text": text,
            "is_hold": is_hold,
            "hold_seconds": cue.get("hold_seconds"),
            "status": status,
            "duration_s": duration,
            "engine": voice.get("engine"),
            "profile_id": voice.get("profile_id"),
            "voice_name": voice.get("voice_name"),
            "segment": cue.get("segment"),
            "shots": cue.get("shots") or [],
            "wav_exists": wav.exists(),
            "wav_mtime": wav.stat().st_mtime if wav.exists() else None,
        })
    return rows


def derive_shots(slug: str, manifest: dict | None = None) -> list[dict]:
    """All character + b-roll keys, plus per-cue title slots, with status."""
    m = manifest or load(slug)
    ep = episode_dir(slug)
    clips_dir = ep / "clips"
    manifest_mtime = manifest_path(slug).stat().st_mtime

    rows: list[dict] = []
    chars = m.get("characters") or {}
    broll = m.get("broll") or {}

    for key, val in chars.items():
        rows.append(_shot_row(slug, key, "character", val, clips_dir, manifest_mtime))
    for key, val in broll.items():
        rows.append(_shot_row(slug, key, "broll", val, clips_dir, manifest_mtime))
    return rows


def _shot_row(slug: str, key: str, kind: str, val: Any, clips_dir: Path, manifest_mtime: float) -> dict:
    # Same path resolution rule as lib.staged_master_webp:
    if kind == "character":
        webp = clips_dir / ("safe_master.zs.webp" if key == "safe" else f"{key}_master.zs.webp")
    else:
        webp = clips_dir / ("c09_s1.zs.webp" if key == "empty_room" else f"broll_{key}.zs.webp")
    if isinstance(val, dict):
        seed = val.get("seed")
        prompt = val.get("core") or val.get("prompt") or ""
    else:
        seed = None
        prompt = str(val) if val else ""
    # Stage 2 writes no per-shot hash sidecar, so we can't prove a shot is stale —
    # an existing master is "rendered" (a manifest touch alone must not false-stale it,
    # which was the old mtime bug). "missing" only when the master is absent. (True
    # prompt/seed-edit staleness would need a studio-owned clips/.cache.json — deferred.)
    status = "rendered" if webp.exists() else "missing"
    return {
        "key": key,
        "kind": kind,
        "seed": seed,
        "prompt": prompt,
        "status": status,
        "webp_exists": webp.exists(),
        "webp_mtime": webp.stat().st_mtime if webp.exists() else None,
    }


def derive_titles(slug: str, manifest: dict | None = None) -> list[dict]:
    m = manifest or load(slug)
    ep = episode_dir(slug)
    titles_dir = ep / "titles"
    manifest_mtime = manifest_path(slug).stat().st_mtime

    rows: list[dict] = []
    for key, val in (m.get("title_assets") or {}).items():
        # title_assets[key] is either:
        #  - a string (legacy free-form hint; shared if it looks shared, otherwise local)
        #  - an object {source, composition, ...}; source="hyperframes" => locally rendered
        local = titles_dir / f"{key}.mp4"
        is_object = isinstance(val, dict)
        source = (val.get("source") if is_object else None) or ""
        if is_object:
            is_local = source == "hyperframes" or "episodes/" in str(val.get("path") or "")
            hint = val.get("path") or f"hyperframes:{val.get('composition') or key}"
            scope = "local" if is_local else "shared"
        else:
            is_local = isinstance(val, str) and ("episodes/" in val or val.startswith("titles/") or "(NEW" in val)
            hint = str(val) if val else ""
            scope = "local" if is_local else "shared"

        if is_local:
            if not local.exists():
                status = "missing"
            elif local.stat().st_mtime < manifest_mtime:
                status = "stale"
            else:
                status = "rendered"
        else:
            status = "shared"
        row = {
            "key": key,
            "hint": hint,
            "scope": scope,
            "status": status,
            "exists": local.exists() if is_local else True,
            "mtime": local.stat().st_mtime if local.exists() else None,
        }
        if is_object:
            row["composition"] = val.get("composition")
            row["resolution"] = val.get("resolution")
            row["duration_seconds"] = val.get("duration_seconds")
            row["fields"] = val.get("fields")
        rows.append(row)

    # Augment with any .html HyperFrames compositions present
    if titles_dir.exists():
        for html in sorted(titles_dir.glob("*.html")):
            rows.append({
                "key": html.stem,
                "hint": str(html),
                "scope": "hyperframes",
                "status": "draft",
                "exists": True,
                "mtime": html.stat().st_mtime,
            })
    return rows


def episode_pipeline_status(slug: str) -> list[dict]:
    """Crude 8-stage status snapshot based on filesystem artefacts.

    The 'live' status during a render comes from the SSE stream; this is the
    at-rest view shown when no job is running.
    """
    ep = episode_dir(slug)
    p = lambda *parts: ep.joinpath(*parts)
    manifest_mtime = manifest_path(slug).stat().st_mtime

    cues = (load(slug).get("cues")) or []
    vo_needed = [c for c in cues if c.get("vo")]
    vo_present = sum(1 for c in vo_needed if p("vo", f"{c['id']}.wav").exists())
    work_nosubs = p(".work", f"{slug}_nosubs.mp4")
    work_music = p(".work", f"{slug}_music_nosubs.mp4")
    final = p("final", f"{slug}.mp4")
    srt = p("final", f"{slug}.srt")
    clips_present = list(p("clips").glob("*_master.zs.webp")) if p("clips").exists() else []
    rife_dirs = [d for d in p(".rife_frames").iterdir() if d.is_dir()] if p(".rife_frames").exists() else []

    def stage(key: str, name: str, n: int, ok: bool, note: str, ref: Path | None) -> dict:
        last_iso = None
        if ref and ref.exists():
            last_iso = time.strftime("%H:%M:%S", time.localtime(ref.stat().st_mtime))
        return {"key": key, "name": name, "n": n,
                "status": "done" if ok else "idle",
                "last": last_iso or "—", "note": note}

    vo_files = [p("vo", f"{c['id']}.wav") for c in vo_needed]
    vo_files = [f for f in vo_files if f.exists()]
    newest_vo = max(vo_files, key=lambda x: x.stat().st_mtime, default=None)
    newest_clip = max(clips_present, key=lambda x: x.stat().st_mtime, default=None)
    newest_rife = max(rife_dirs, key=lambda x: x.stat().st_mtime, default=None)

    return [
        stage("vo", "Voiceover", 1,
              bool(vo_needed) and len(vo_files) == len(vo_needed),
              f"{len(vo_files)}/{len(vo_needed)} cues",
              newest_vo),
        stage("masters", "Masters", 2,
              bool(clips_present),
              f"{len(clips_present)} masters",
              newest_clip),
        stage("rife", "RIFE", 3,
              bool(rife_dirs),
              f"{len(rife_dirs)} dirs",
              newest_rife),
        stage("assemble", "Assemble", 4, work_nosubs.exists(), "nosubs.mp4", work_nosubs),
        stage("music", "Music", 5, work_music.exists(), "music_nosubs.mp4", work_music),
        stage("whisper", "Whisper", 6, Path(f"/tmp/macu_whisper_{slug}.json").exists(), "ASR cache", Path(f"/tmp/macu_whisper_{slug}.json")),
        stage("srt", "SRT", 7, srt.exists(), "subs", srt),
        stage("burn", "Burn-In", 8, final.exists(), "final mp4", final),
    ]


def final_info(slug: str) -> dict:
    ep = episode_dir(slug)
    final = ep / "final" / f"{slug}.mp4"
    thumb = ep / "final" / f"{slug}_thumbs.jpg"
    srt = ep / "final" / f"{slug}.srt"
    out = {
        "exists": final.exists(),
        "path": str(final),
        "size_mb": None,
        "duration_s": None,
        "mtime": None,
        "thumb_exists": thumb.exists(),
        "srt_exists": srt.exists(),
    }
    if final.exists():
        st = final.stat()
        out["size_mb"] = round(st.st_size / (1024 * 1024), 2)
        out["mtime"] = st.st_mtime
        # ffprobe is in the pipeline; ok to call here
        import subprocess
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(final)],
                capture_output=True, text=True, check=True, timeout=5,
            )
            out["duration_s"] = round(float(r.stdout.strip()), 2)
        except Exception:
            pass
    return out
