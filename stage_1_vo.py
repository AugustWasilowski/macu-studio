#!/usr/bin/env python3
"""Stage 1: render per-cue VO. Dispatches by manifest.voice.speaker_map.

For each cue, looks up cue["speaker"] in manifest.voice.speaker_map:
  - engine="piper"    -> POST /  on PIPER_URL, body {"text": "..."}
  - engine="omnivoice" -> POST /generate on OMNIVOICE_URL with profile_id
Falls back to manifest.voice.default (piper HAL) for unmapped speakers.

All outputs are normalized to 24kHz mono PCM s16 so stage_4_assemble's concat
copy doesn't trip over sample-rate mismatches.

Idempotent: skips cues whose vo/<cue_id>.wav already exists with size > 0
AND is newer than the manifest. Touch the manifest to invalidate.

Usage: python3 stage_1_vo.py <slug>
"""
import sys, json, os, urllib.request, urllib.parse, concurrent.futures
import time, subprocess, tempfile, uuid
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths, load_manifest, ensure_dirs, PIPER_URL, OMNIVOICE_URL

TARGET_SR = 24000


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


def _omnivoice(text, profile_id, out_path):
    boundary = "----macu" + uuid.uuid4().hex
    parts = []
    for name, val in [("text", text), ("profile_id", profile_id),
                      ("language", "English")]:
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


def render_one(cue_id, speaker, text, out_path, voice_cfg):
    engine = voice_cfg.get("engine", "piper")
    t0 = time.time()
    if engine == "omnivoice":
        _omnivoice(text, voice_cfg["profile_id"], out_path)
    else:
        _piper(text, out_path)
    return cue_id, engine, voice_cfg.get("voice_name", engine), \
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
    manifest_mtime = os.path.getmtime(p["manifest"])

    todo = []
    skipped = 0
    for cue in m["cues"]:
        out = f"{p['vo']}/{cue['id']}.wav"
        if (os.path.exists(out) and os.path.getsize(out) > 0
                and os.path.getmtime(out) > manifest_mtime):
            skipped += 1
            continue
        voice = _resolve_voice(m, cue["speaker"])
        todo.append((cue["id"], cue["speaker"], cue["vo"], out, voice))

    print(f"[stage 1 vo] {len(todo)} to render, {skipped} cached")
    if not todo:
        return {"rendered": 0, "skipped": skipped}

    start = time.time()
    # Serial: OmniVoice's torch.compile + cudagraphs path asserts under
    # concurrent /generate calls on the same model.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        futs = [ex.submit(render_one, *t) for t in todo]
        for f in concurrent.futures.as_completed(futs):
            cid, eng, vname, sz, dt = f.result()
            print(f"  {cid} [{eng}:{vname}] {sz/1024:.1f} KB ({dt}s)")
    print(f"[stage 1 vo] {len(todo)} rendered in {round(time.time()-start,2)}s")
    return {"rendered": len(todo), "skipped": skipped,
            "wall_s": round(time.time()-start, 2)}


if __name__ == "__main__":
    main(sys.argv[1])
