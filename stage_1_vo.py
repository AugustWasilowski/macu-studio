#!/usr/bin/env python3
"""Stage 1: render per-cue VO. Dispatches by manifest.voice.speaker_map.

For each cue, looks up cue["speaker"] in manifest.voice.speaker_map:
  - engine="piper"    -> POST /  on PIPER_URL, body {"text": "..."}
  - engine="omnivoice" -> POST /generate on OMNIVOICE_URL with profile_id
Falls back to manifest.voice.default (piper HAL) for unmapped speakers.

All outputs are normalized to 24kHz mono PCM s16 so stage_4_assemble's concat
copy doesn't trip over sample-rate mismatches.

Idempotent via a sidecar cache at vo/.cache.json. Each entry is a 16-hex hash
of the inputs that determine a cue's rendered wav (vo text, speaker, voice
engine/profile/voice_name, or hold_seconds for silent cues). Stage 1 skips a
cue when the wav exists AND the sidecar's stored hash matches the current
hash. So a manifest edit that doesn't touch a given cue won't invalidate that
cue's wav — and hand-tuned wavs (e.g. swapping c25.wav over c23.wav) survive
any manifest edit that doesn't change c23's own text/voice.

First-run migration: when a wav exists but the sidecar has no entry for it,
that wav is treated as cached and the sidecar is seeded with the current
hash. So deploying this skill onto an existing episode dir doesn't force a
full VO regen.

Usage: python3 stage_1_vo.py <slug>
"""
import sys, json, os, urllib.request, urllib.parse, concurrent.futures
import time, subprocess, tempfile, uuid, hashlib
sys.path.insert(0, os.path.dirname(__file__))
from lib import (episode_paths, load_manifest, ensure_dirs,
                 PIPER_URL, OMNIVOICE_URL,
                 omnivoice_start, omnivoice_stop)

TARGET_SR = 24000

CACHE_FILE_NAME = ".cache.json"
CACHE_VERSION = 1


def _cue_cache_key(cue, voice_cfg):
    """Stable 16-hex hash of everything that determines a cue's rendered wav.

    For hold cues (vo:"" + hold_seconds:N), only the duration matters — silence
    is silence regardless of voice config. Including voice_cfg here would mean
    a speaker_map edit (unrelated to silence) needlessly invalidates hold wavs.
    For dialogue cues, the hash covers the text, the speaker label, and the
    resolved voice config (engine + profile_id + voice_name) so any tweak that
    would change what TTS produces will invalidate the cache.
    """
    hold = cue.get("hold_seconds")
    if hold is not None:
        payload = {"hold_seconds": float(hold)}
    else:
        payload = {
            "vo": cue.get("vo") or "",
            "speaker": cue.get("speaker") or "",
            "engine": voice_cfg.get("engine"),
            "profile_id": voice_cfg.get("profile_id"),
            "voice_name": voice_cfg.get("voice_name"),
            "speed": voice_cfg.get("speed"),
            "guidance_scale": voice_cfg.get("guidance_scale"),
            "seed": voice_cfg.get("seed"),
            "instruct": voice_cfg.get("instruct"),
        }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _load_cache(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if data.get("version") != CACHE_VERSION:
        return {}
    return data.get("cues", {})


def _save_cache(path, cues):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"version": CACHE_VERSION, "cues": cues},
                  f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _normalize(src_path, dst_path):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", src_path, "-ac", "1", "-ar", str(TARGET_SR),
        "-c:a", "pcm_s16le", dst_path,
    ], check=True)


def _piper(text, out_path):
    req = urllib.request.Request(
        PIPER_URL + "/",
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        wav = r.read()
    tmp = f"{out_path}.raw.wav"
    with open(tmp, "wb") as f:
        f.write(wav)
    _normalize(tmp, out_path)
    os.unlink(tmp)


def _silent(seconds, out_path):
    """Write a silent wav of the requested duration in the same format as TTS
    output (24kHz mono PCM s16). Used for cues that declare hold_seconds — a
    no-dialogue reaction beat — so stage 4's per-shot math (vo_dur / N shots)
    works without any cue-shape branching downstream."""
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r={TARGET_SR}:cl=mono",
        "-t", f"{float(seconds):.4f}",
        "-ac", "1", "-ar", str(TARGET_SR), "-c:a", "pcm_s16le", out_path,
    ], check=True)


def _omnivoice(text, profile_id, out_path, speed=None, guidance_scale=None, seed=None, instruct=None):
    boundary = "----macu" + uuid.uuid4().hex
    parts = []
    fields = [("text", text), ("profile_id", profile_id), ("language", "English")]
    for k, v in (("speed", speed), ("guidance_scale", guidance_scale),
                 ("seed", seed), ("instruct", instruct)):
        if v is not None and v != "":
            fields.append((k, str(v)))
    for name, val in fields:
        parts.append(f"--{boundary}\r\n"
                     f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                     f"{val}\r\n")
    body = ("".join(parts) + f"--{boundary}--\r\n").encode()
    req = urllib.request.Request(
        OMNIVOICE_URL + "/generate", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        wav = r.read()
    tmp = f"{out_path}.raw.wav"
    with open(tmp, "wb") as f:
        f.write(wav)
    # OmniVoice already returns 24kHz mono PCM, but normalize to enforce.
    _normalize(tmp, out_path)
    os.unlink(tmp)


def render_one(cue_id, speaker, text, out_path, voice_cfg, hold_seconds=None):
    """Render a single cue's VO. If hold_seconds is set, emit silence of that
    length instead of routing to a TTS engine."""
    t0 = time.time()
    if hold_seconds is not None:
        _silent(hold_seconds, out_path)
        engine = "hold"
        vname = f"{hold_seconds:.2f}s"
    else:
        engine = voice_cfg.get("engine", "piper")
        if engine == "omnivoice":
            _omnivoice(text, voice_cfg["profile_id"], out_path,
                       speed=voice_cfg.get("speed"),
                       guidance_scale=voice_cfg.get("guidance_scale"),
                       seed=voice_cfg.get("seed"),
                       instruct=voice_cfg.get("instruct"))
        else:
            _piper(text, out_path)
        vname = voice_cfg.get("voice_name", engine)
    return cue_id, engine, vname, \
        os.path.getsize(out_path), round(time.time() - t0, 2)


def _resolve_voice(manifest, speaker):
    vmap = manifest["voice"].get("speaker_map", {})
    if speaker in vmap:
        return vmap[speaker]
    return manifest["voice"].get("default", {"engine": "piper"})


def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    cache_path = f"{p['vo']}/{CACHE_FILE_NAME}"
    cache = _load_cache(cache_path)

    todo = []
    skipped = 0
    seeded = 0
    cur_keys = {}  # cue_id -> current key; used to update cache on render success
    for cue in m["cues"]:
        out = f"{p['vo']}/{cue['id']}.wav"
        voice = _resolve_voice(m, cue.get("speaker") or "")
        key = _cue_cache_key(cue, voice)
        cur_keys[cue["id"]] = key
        if os.path.exists(out) and os.path.getsize(out) > 0:
            stored = cache.get(cue["id"])
            if stored == key:
                # Real cache hit.
                skipped += 1
                continue
            if stored is None:
                # Migration: wav exists but no sidecar entry yet (first run
                # after deploy, or hand-tuned wav). Trust the wav and seed the
                # sidecar with the current hash. Does NOT regenerate.
                cache[cue["id"]] = key
                seeded += 1
                skipped += 1
                continue
            # else stored != key and stored is not None → text/voice changed → regen.
        hold = cue.get("hold_seconds")
        todo.append((cue["id"], cue.get("speaker") or "",
                     cue.get("vo") or "", out, voice, hold))

    # Prune sidecar entries for cues that no longer exist in the manifest. Old
    # vo/<id>.wav files are left on disk (harmless, may have been hand-saved).
    stale = [k for k in cache if k not in cur_keys]
    for k in stale:
        del cache[k]

    if seeded or stale:
        _save_cache(cache_path, cache)
        notes = []
        if seeded:
            notes.append(f"seeded {seeded} entries from existing wavs")
        if stale:
            notes.append(f"pruned {len(stale)} stale entries")
        print(f"[stage 1 vo] cache: {'; '.join(notes)}")

    print(f"[stage 1 vo] {len(todo)} to render, {skipped} cached")
    if not todo:
        return {"rendered": 0, "skipped": skipped}

    # OmniVoice is ~4.6 GB of VRAM and starves ComfyUI's lowvram threshold in
    # stage 2. Start it only if some non-cached cue actually needs it, and
    # stop it on the way out (regardless of failure) so the GPU is clean for
    # the masters stage. Set MACU_KEEP_OMNIVOICE=1 to suppress the stop — useful
    # when iterating just on VO via `--only 1`.
    # A cue needs OmniVoice only if it's NOT a hold AND its voice engine is omnivoice.
    # Hold cues are silent ffmpeg passes — they don't touch any TTS engine.
    needs_omni = any(t[5] is None and t[4].get("engine") == "omnivoice"
                     for t in todo)
    started_omni = False
    keep_omni = os.environ.get("MACU_KEEP_OMNIVOICE") == "1"
    if needs_omni:
        omnivoice_start()
        started_omni = True

    start = time.time()
    try:
        # Serial: OmniVoice's torch.compile + cudagraphs path asserts under
        # concurrent /generate calls on the same model.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            futs = [ex.submit(render_one, *t) for t in todo]
            for f in concurrent.futures.as_completed(futs):
                cid, eng, vname, sz, dt = f.result()
                print(f"  {cid} [{eng}:{vname}] {sz/1024:.1f} KB ({dt}s)")
                # Persist after each successful render so partial runs are
                # resumable — a crash mid-batch keeps the wavs already written
                # genuinely cached on the next run.
                cache[cid] = cur_keys[cid]
                _save_cache(cache_path, cache)
    finally:
        if started_omni and not keep_omni:
            omnivoice_stop()
    print(f"[stage 1 vo] {len(todo)} rendered in {round(time.time()-start,2)}s")
    return {"rendered": len(todo), "skipped": skipped,
            "wall_s": round(time.time()-start, 2)}


if __name__ == "__main__":
    main(sys.argv[1])
