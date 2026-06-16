"""Higgsfield cloud-shot cache + hashing — the ONE canonical implementation.

Both sides import this file (they share the studio venv + repo checkout):
  - pipeline/stage_2b_cloud.py   (same directory)
  - studio macu_studio.hfcache   (loads it by path via importlib)

Semantics mirror vo/.cache.json (stage_1_vo): a 16-hex sha256 of the inputs
that cost money to regenerate. Matching hash + existing artifact ⇒ skip.
Crop / trim / jank are deliberately EXCLUDED — they're applied at assembly
(stage 4) from the cached clip, so editing them never re-bills.

Sidecars:
  clips/.hf_cache.json   {"version": 1, "shots":  {shot_id: hash}}
  stills/.cache.json     {"version": 1, "stills": {who: hash}}
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

CACHE_VERSION = 1
CLOUD_KINDS = ("higgsfield", "lipsync")


def is_mouthless(shot: dict, manifest: dict) -> bool:
    """True when a shot's subject has no visible mouth to sync (masked / paper-bag
    head, e.g. ep-022 masked_man). Flagged on the character as `no_lipsync` or
    `mouthless`. Such a shot animates from its still via the i2v video path instead
    of audio-driven lipsync — nothing to sync, and lipsync would warp the mask."""
    who = shot.get("who") or ""
    c = (manifest.get("characters") or {}).get(who)
    return bool(isinstance(c, dict) and (c.get("no_lipsync") or c.get("mouthless")))


def effective_kind(shot: dict, manifest: dict) -> str:
    """The kind a shot is actually RENDERED/ASSEMBLED as. A `lipsync` shot whose
    subject is mouthless routes through the `higgsfield` i2v video path (animate
    the still, no audio-driven mouth). Every stage that branches on shot kind for
    the lipsync-vs-video decision must use this, not the raw `kind`, so the render
    cache, generation, and assembly all agree."""
    k = shot.get("kind")
    if k == "lipsync" and is_mouthless(shot, manifest):
        return "higgsfield"
    return k

# Lipsync VO chunking: clips cap at 15s on every Higgsfield model; we chunk at
# ≤12s so a split point can slide a couple seconds to land on silence.
CHUNK_MAX_S = 12.0

DEFAULTS = {
    "model": "seedance_2_0",
    "image_model": "soul",
    "resolution": "720p",
    "aspect_ratio": "1:1",
    "duration": 8,
}


# ---- paths ---------------------------------------------------------------------

def clip_path(ep_dir: Path, shot_id: str) -> Path:
    return ep_dir / "clips" / f"hf_{shot_id}.mp4"


def still_path(ep_dir: Path, who: str) -> Path:
    return ep_dir / "stills" / f"{who}.png"


def clips_sidecar_path(ep_dir: Path) -> Path:
    return ep_dir / "clips" / ".hf_cache.json"


def stills_sidecar_path(ep_dir: Path) -> Path:
    return ep_dir / "stills" / ".cache.json"


# ---- sidecar io -----------------------------------------------------------------

def load_sidecar(path: Path, key: str) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text())
        return dict(d.get(key) or {})
    except Exception:
        return {}


def save_sidecar(path: Path, key: str, entries: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": CACHE_VERSION, key: entries},
                               indent=2, sort_keys=True))


# ---- hashing --------------------------------------------------------------------

def _h(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def file_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def hf_block(manifest: dict) -> dict:
    blk = dict(DEFAULTS)
    blk.update(manifest.get("higgsfield") or {})
    return blk


def resolve_prompt(shot: dict, manifest: dict) -> str:
    """Shot prompt, falling back to the referenced character/broll core prompt;
    the higgsfield style suffix (NOT the zeroscope-tuned style.suffix) appends."""
    blk = hf_block(manifest)
    base = (shot.get("prompt") or "").strip()
    if not base:
        who = shot.get("who") or ""
        c = (manifest.get("characters") or {}).get(who)
        b = (manifest.get("broll") or {}).get(who)
        if isinstance(c, dict):
            base = (c.get("core") or "").strip()
        elif isinstance(c, str):
            base = c.strip()
        elif isinstance(b, dict):
            base = (b.get("prompt") or "").strip()
        elif isinstance(b, str):
            base = b.strip()
    suffix = (blk.get("style_suffix") or "").strip()
    return (base + suffix) if base else base


# The neutral talking-head prompt for audio-driven lipsync (wan2_7 etc.). Identity
# comes from the still; the prompt must NOT carry the scene `core` or the model
# dramatizes the scene (subject looks away) and never lip-syncs — see
# macu-hf-lipsync-input-quality. Overridable per-shot/per-char with `lipsync_prompt`.
LIPSYNC_DEFAULT_PROMPT = ("talking head, speaking directly to camera, head and "
                          "shoulders, minimal movement, mouth synced to the voice, "
                          "subtle natural motion")


def lipsync_prompt(shot: dict, manifest: dict) -> str:
    """Prompt for an audio-driven lipsync shot. Precedence: per-shot `lipsync_prompt`
    → the referenced character's `lipsync_prompt` → the neutral talking-head default.
    It NEVER falls back to the scene/action `core` (resolve_prompt) — that's what
    made wan2_7 heads stop syncing on ep-022. The higgsfield style suffix appends,
    same as resolve_prompt, so the look matches the b-roll shots."""
    blk = hf_block(manifest)
    base = (shot.get("lipsync_prompt") or "").strip()
    if not base:
        who = shot.get("who") or ""
        c = (manifest.get("characters") or {}).get(who)
        if isinstance(c, dict):
            base = (c.get("lipsync_prompt") or "").strip()
    if not base:
        base = LIPSYNC_DEFAULT_PROMPT
    suffix = (blk.get("style_suffix") or "").strip()
    return base + suffix


def resolve_still(shot_or_char: dict, manifest: dict, ep_dir: Path) -> Path | None:
    """A shot's source_still is either a character key (→ stills/<who>.png) or a
    path relative to the episode dir."""
    ref = (shot_or_char.get("source_still") or "").strip()
    if not ref:
        return None
    if ref in (manifest.get("characters") or {}):
        return still_path(ep_dir, ref)
    return ep_dir / ref


# ---- lipsync still guards (SSA-145) --------------------------------------------

def _png_dims(path: Path) -> tuple[int, int] | None:
    """(width, height) from a PNG's IHDR — stdlib only, no PIL dep."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except Exception:
        return None


def _face_fraction(path: Path) -> float | None:
    """Largest frontal-face area as a fraction of the frame, via opencv's haar
    cascade. None when opencv isn't installed (the guard then falls back to the
    cheap dims/aspect check). 0.0 means a detector ran but found no face."""
    try:
        import cv2  # type: ignore
    except Exception:
        return None
    try:
        img = cv2.imread(str(path))
        if img is None:
            return None
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, 1.1, 4)
        if len(faces) == 0:
            return 0.0
        return max(fw * fh for (_x, _y, fw, fh) in faces) / float(w * h)
    except Exception:
        return None


def lipsync_still_warnings(shot: dict, manifest: dict, ep_dir: Path) -> list[str]:
    """Best-effort pre-submit checks for an audio-driven lipsync still (SSA-145).
    wan2_7 needs a findable mouth: a wide/small-face still animates the scene
    instead of lip-syncing (the ep-022 'static head' trap). Returns human-readable
    warning strings — never raises, never blocks the render.

      - face too small / not found  → no mouth to drive
      - landscape/wide still        → face likely small
      - on-disk still ≠ synced library take → stale / hand-swapped (wrong default_take)
    """
    warns: list[str] = []
    still = resolve_still(shot, manifest, ep_dir)
    if not still or not still.exists():
        return warns
    frac = _face_fraction(still)
    if frac is not None:
        if frac == 0.0:
            warns.append(f"no frontal face detected in {still.name} — wan2_7 may "
                         f"animate the scene instead of lip-syncing; use a tight "
                         f"head-and-shoulders take")
        elif frac < 0.06:
            warns.append(f"face fills only {frac*100:.1f}% of {still.name} — likely "
                         f"too small for wan2_7 to lip-sync; use a tighter frontal take")
    dims = _png_dims(still)
    if dims:
        w, h = dims
        if w > h * 1.3:
            warns.append(f"{still.name} is landscape ({w}x{h}) — frontal portrait/"
                         f"square stills lip-sync more reliably")
    who = shot.get("who") or ""
    entry = (manifest.get("characters") or {}).get(who)
    if isinstance(entry, dict) and entry.get("library_sha"):
        cur = file_sha(still)
        if cur and cur != entry["library_sha"]:
            ref = entry.get("library_ref") or "the library take"
            warns.append(f"still {still.name} differs from synced library take "
                         f"{ref} — re-sync the character (Use in episode) unless this "
                         f"is an intentional hand-swap")
    return warns


def shot_params(shot: dict, manifest: dict) -> dict:
    """The generation-shaping params for a higgsfield video shot (also the
    memoization shape for cost estimates)."""
    blk = hf_block(manifest)
    return {
        "model": shot.get("model") or blk["model"],
        "duration": int(shot.get("duration") or blk["duration"]),
        "resolution": shot.get("resolution") or blk["resolution"],
        "aspect_ratio": shot.get("aspect_ratio") or blk["aspect_ratio"],
    }


def shot_hash(shot: dict, manifest: dict, ep_dir: Path) -> str:
    p = shot_params(shot, manifest)
    still = resolve_still(shot, manifest, ep_dir)
    return _h({
        **p,
        "prompt": resolve_prompt(shot, manifest),
        "seed": shot.get("seed"),
        "still_sha": file_sha(still) if still else None,
    })


def lipsync_hash(shot: dict, manifest: dict, ep_dir: Path, cue_id: str,
                 engine: str = "higgsfield") -> str:
    p = shot_params(shot, manifest)
    still = resolve_still(shot, manifest, ep_dir)
    vo = ep_dir / "vo" / f"{cue_id}.wav"
    payload = {
        "still_sha": file_sha(still) if still else None,
        "vo_sha": file_sha(vo),
        "engine": engine,
    }
    # The resolved talking-head prompt shapes the generation on EVERY engine
    # (SSA-144): editing a per-char/per-shot lipsync_prompt must re-bill the clip.
    payload["prompt"] = lipsync_prompt(shot, manifest)
    if engine == "higgsfield":
        # Model/resolution shape the cloud generation; the local/remote
        # InfiniteTalk graph is fixed, so they'd only cause spurious staleness.
        payload.update({"model": lipsync_model(shot, manifest), "resolution": p["resolution"],
                        "aspect_ratio": p["aspect_ratio"], "chunk_max_s": CHUNK_MAX_S})
    else:
        # Sampler preset shapes local/remote output (fast vs quality).
        payload["preset"] = hf_block(manifest).get("lipsync_preset") or "quality"
    return _h(payload)


def lipsync_model(shot: dict, manifest: dict) -> str:
    """HF model for an audio-driven lipsync shot: per-shot override → the show's
    `lipsync_model` default → the general video model. Lets the operator pick a
    distinct lipsync model per show (SSA-131) without changing b-roll video."""
    blk = hf_block(manifest)
    return shot.get("model") or blk.get("lipsync_model") or blk["model"]


def still_hash(char: dict, manifest: dict) -> str:
    blk = hf_block(manifest)
    return _h({
        "still_prompt": (char.get("still_prompt") or "").strip(),
        "still_model": char.get("still_model") or blk["image_model"],
    })


def broll_still_prompt(manifest: dict, key: str) -> str:
    """The z-image seed-still prompt for a b-roll key under the wan_i2v masters
    backend: the b-roll's scene prompt + the show's style.suffix (which carries
    the B&W look), so the still matches the episode aesthetic before WAN animates
    it. b-roll has no separate still_prompt the way characters do — the scene
    prompt IS the still prompt."""
    b = (manifest.get("broll") or {}).get(key)
    core = ""
    if isinstance(b, dict):
        core = (b.get("prompt") or "").strip()
    elif isinstance(b, str):
        core = b.strip()
    suffix = (manifest.get("style") or {}).get("suffix", "")
    return (core + suffix) if core else core


def broll_still_hash(manifest: dict, key: str) -> str:
    blk = hf_block(manifest)
    return _h({
        "broll_still_prompt": broll_still_prompt(manifest, key),
        "still_model": blk["image_model"],
    })


# ---- manifest walks ----------------------------------------------------------------

def cloud_shots(manifest: dict) -> Iterator[tuple[dict, dict]]:
    """Yield (cue, shot) for every cloud-kind shot, in cue order."""
    for cue in manifest.get("cues") or []:
        for shot in cue.get("shots") or []:
            if shot.get("kind") in CLOUD_KINDS:
                yield cue, shot


def referenced_stills(manifest: dict) -> list[str]:
    """Character keys whose stills are referenced by cloud shots (deduped, ordered)."""
    chars = manifest.get("characters") or {}
    seen: list[str] = []
    for _cue, shot in cloud_shots(manifest):
        ref = (shot.get("source_still") or "").strip()
        if ref and ref in chars and ref not in seen:
            seen.append(ref)
    return seen


def shot_state(shot: dict, cue: dict, manifest: dict, ep_dir: Path,
               cached: dict[str, str], lipsync_engine: str = "higgsfield") -> dict:
    """Cache verdict for one cloud shot: {hash, exists, fresh}."""
    sid = shot.get("id") or ""
    if effective_kind(shot, manifest) == "lipsync":
        h = lipsync_hash(shot, manifest, ep_dir, cue.get("id") or "", lipsync_engine)
    else:
        h = shot_hash(shot, manifest, ep_dir)
    clip = clip_path(ep_dir, sid)
    exists = clip.exists()
    entry = cached.get(sid)
    # Migration-seed semantics (mirrors stage_1_vo): an artifact with no sidecar
    # entry is trusted — never re-bill for a clip we can't prove stale.
    fresh = exists and (entry is None or entry == h)
    return {"hash": h, "exists": exists, "fresh": fresh}
