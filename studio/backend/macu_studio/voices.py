"""OmniVoice voice-clone client for MACU Studio (the "Create Voice" feature).

OmniVoice is a consumer-lifecycle GPU service (container `omnivoice`, loopback
:3900) — normally STOPPED so its ~4.6 GB doesn't starve ComfyUI during renders.
A clone action start()s it on demand (mirrors llm.py / the render pipeline's
OmniVoice lifecycle) and leaves it running so the user can clone/test several in
a row; the render pipeline stops it when it next needs the VRAM.

Clone flow (same as voices/clone_one.sh, in Python):
  upload (mp3/wav/mp4/m4a/…) -> ffmpeg to 24kHz mono pcm_s16le wav -> POST
  /profiles (multipart name/language/ref_audio) -> {id, name}. Optionally POST
  /generate for a confirmation test clip.
"""
from __future__ import annotations

import re
import socket
import subprocess
import time
from pathlib import Path

import httpx

from . import config

OMNIVOICE_CONTAINER = "omnivoice"
OMNIVOICE_URL = "http://127.0.0.1:3900"

VOICES_DIR = config.SHARES / "voices"
REFS_DIR = VOICES_DIR / "refs"
TESTS_DIR = VOICES_DIR / "tests"
# Last-known profile roster, refreshed on every successful live list. Lets the
# voice picker show the full roster (e.g. the Announcer) even when OmniVoice is
# stopped — so the GPU doesn't have to spin up just to browse voices.
CACHE_FILE = VOICES_DIR / "profiles_cache.json"

_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _slug(name: str) -> str:
    s = _NAME_RE.sub("_", (name or "").strip()).strip("_")
    return s or "voice"


# --------------------------------------------------------------------------- #
# Container lifecycle (mirrors llm.py)
# --------------------------------------------------------------------------- #

def is_running(timeout: float = 1.5) -> bool:
    """True if :3900 answers GET /profiles right now (no container start)."""
    try:
        with socket.create_connection(("127.0.0.1", 3900), timeout=timeout):
            pass
        httpx.get(OMNIVOICE_URL + "/profiles", timeout=timeout)
        return True
    except Exception:
        return False


def ensure_up(wait_timeout: int = 180, poll_interval: int = 2) -> None:
    """`docker start omnivoice` and wait until GET /profiles answers. Idempotent."""
    if is_running():
        return
    r = subprocess.run(["docker", "start", OMNIVOICE_CONTAINER], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"docker start {OMNIVOICE_CONTAINER} failed: {r.stderr.strip() or r.stdout.strip()}")
    deadline = time.time() + wait_timeout
    last = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 3900), timeout=2):
                pass
            httpx.get(OMNIVOICE_URL + "/profiles", timeout=3)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(poll_interval)
    raise RuntimeError(f"omnivoice not ready in {wait_timeout}s (last error: {last!r})")


# --------------------------------------------------------------------------- #
# OmniVoice REST
# --------------------------------------------------------------------------- #

def _read_cache() -> list[dict]:
    try:
        import json
        data = json.loads(CACHE_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_cache(profiles: list[dict]) -> None:
    try:
        import json
        VOICES_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(profiles, indent=2))
    except Exception:
        pass


def list_profiles_safe() -> dict:
    """List cloned profiles. Never starts the container. When OmniVoice is up,
    returns the live roster and refreshes the on-disk cache; when it's down,
    returns the cached roster (flagged) so the picker still shows every voice."""
    if not is_running():
        return {"running": False, "cached": True, "profiles": _read_cache()}
    try:
        resp = httpx.get(OMNIVOICE_URL + "/profiles", timeout=10)
        resp.raise_for_status()
        profiles = [{"id": p.get("id"), "name": p.get("name")} for p in resp.json()]
        _write_cache(profiles)
        return {"running": True, "cached": False, "profiles": profiles}
    except Exception as e:  # noqa: BLE001
        return {"running": True, "cached": True, "profiles": _read_cache(), "error": str(e)}


def _convert_to_ref(src: Path, name: str) -> Path:
    """ffmpeg-normalize any audio/video to OmniVoice's ref format: 24kHz mono
    pcm_s16le wav. Works for mp3/wav/mp4/m4a/… (ffmpeg pulls the audio stream)."""
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    ref = REFS_DIR / f"{_slug(name)}.wav"
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(src), "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(ref)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not ref.exists():
        raise RuntimeError(f"ffmpeg could not read the audio: {r.stderr.strip()[:400] or 'unknown error'}")
    return ref


def _delete_same_name(name: str) -> None:
    """Remove any existing profile(s) with this (case-insensitive) name so a
    re-clone replaces rather than duplicates — matches clone_one.sh."""
    try:
        resp = httpx.get(OMNIVOICE_URL + "/profiles", timeout=10)
        resp.raise_for_status()
        for p in resp.json():
            if (p.get("name") or "").lower() == name.lower():
                httpx.delete(f"{OMNIVOICE_URL}/profiles/{p.get('id')}", timeout=10)
    except Exception:
        pass


def create_from_upload(name: str, language: str, test_text: str, src: Path) -> dict:
    """Full clone: ensure OmniVoice up → normalize ref → (replace same-name) →
    POST /profiles → optional test clip. Returns {id, name, ref, test_file?}."""
    name = (name or "").strip()
    if not name:
        raise ValueError("voice name is required")
    ensure_up()
    ref = _convert_to_ref(src, name)
    _delete_same_name(name)
    with open(ref, "rb") as fh:
        resp = httpx.post(
            OMNIVOICE_URL + "/profiles",
            data={"name": name, "language": language or "English"},
            files={"ref_audio": (ref.name, fh, "audio/wav")},
            timeout=120,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"OmniVoice rejected the profile ({resp.status_code}): {resp.text[:400]}")
    prof = resp.json()
    pid = prof.get("id")
    out: dict = {"id": pid, "name": name, "ref": ref.name}

    text = (test_text or "").strip() or (
        "In a world gone mad after the apocalypse, this is a test of the cloned voice.")
    try:
        TESTS_DIR.mkdir(parents=True, exist_ok=True)
        test_path = TESTS_DIR / f"{_slug(name)}_test.wav"
        gen = httpx.post(
            OMNIVOICE_URL + "/generate",
            data={"text": text, "profile_id": pid, "language": language or "English"},
            timeout=180,
        )
        if gen.status_code < 400:
            test_path.write_bytes(gen.content)
            out["test_file"] = test_path.name
    except Exception:
        pass  # test clip is a nicety, never fail the clone on it
    return out


def delete_profile(pid: str) -> dict:
    ensure_up()
    resp = httpx.delete(f"{OMNIVOICE_URL}/profiles/{pid}", timeout=10)
    return {"ok": resp.status_code < 400}


def test_clip_path(filename: str) -> Path:
    """Resolve a test-clip basename safely under TESTS_DIR (no traversal)."""
    safe = Path(filename).name
    if not safe.endswith(".wav"):
        raise ValueError("bad clip name")
    return TESTS_DIR / safe
