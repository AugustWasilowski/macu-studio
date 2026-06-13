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
from lib import (episode_paths, load_manifest, ensure_dirs, probe_dur,
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


def _omnivoice(text, profile_id, out_path, speed=None, guidance_scale=None, seed=None,
               instruct=None, language="English", duration=None):
    boundary = "----macu" + uuid.uuid4().hex
    parts = []
    fields = [("text", text), ("profile_id", profile_id), ("language", language)]
    for k, v in (("speed", speed), ("guidance_scale", guidance_scale),
                 ("seed", seed), ("instruct", instruct), ("duration", duration)):
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


def _omnivoice_profiles():
    """Live OmniVoice roster → (live_ids:set, name_to_id:dict). Empty on any error
    (caller treats that as 'no profiles loaded' and fails loud rather than guessing)."""
    try:
        with urllib.request.urlopen(OMNIVOICE_URL + "/profiles", timeout=10) as r:
            data = json.loads(r.read())
    except Exception:
        return set(), {}
    ids, name_to_id = set(), {}
    for p in (data or []):
        pid, nm = p.get("id"), p.get("name")
        if pid:
            ids.add(pid)
        if nm and pid:
            name_to_id.setdefault(nm, pid)
    return ids, name_to_id


def _heal_pid(voice_cfg, live_ids, name_to_id):
    """Resolve the OmniVoice profile_id to actually POST for a cue. The manifest's
    profile_id is machine-specific; if it isn't in the running engine we fall back
    to resolving by the (portable) voice_name. Returns (profile_id, status) where
    status is 'ok' (manifest id is live), 'healed' (resolved by name), or 'missing'
    (neither resolves — the caller fails loud rather than render a wrong voice)."""
    pid = voice_cfg.get("profile_id")
    vname = voice_cfg.get("voice_name")
    if pid and pid in live_ids:
        return pid, "ok"
    if vname and vname in name_to_id:
        return name_to_id[vname], "healed"
    return pid, "missing"


def _heal_todo(todo, live_ids, name_to_id):
    """Resolve every OmniVoice cue's profile_id against the live roster. Returns
    (resolved_todo, healed[list], missing[list]). On any missing the caller must
    fail loud — silent fallback to a generic voice is exactly the bug this guards."""
    resolved, healed, missing = [], [], []
    for t in todo:
        cid, spk, text, out, voice, hold = t
        if hold is None and voice.get("engine") == "omnivoice":
            pid, status = _heal_pid(voice, live_ids, name_to_id)
            if status == "missing":
                missing.append((cid, spk, voice.get("voice_name"), voice.get("profile_id")))
            elif status == "healed":
                voice = dict(voice); voice["profile_id"] = pid
                healed.append((voice.get("voice_name"), pid))
                t = (cid, spk, text, out, voice, hold)
        resolved.append(t)
    return resolved, healed, missing


class CastingError(RuntimeError):
    """Raised when a cue is cast to OmniVoice but no live profile resolves for it —
    by id or by voice_name. Fails the stage loud so casting gets fixed (import the
    voice) before a render silently uses a generic fallback voice."""


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
        # Self-heal casting: the manifest's profile_id is machine-specific, so
        # resolve each OmniVoice cue against the LIVE roster (by id, else by the
        # portable voice_name). If a cue resolves by neither, fail LOUD instead of
        # letting OmniVoice fall back to a generic voice — the exact bug from the
        # cross-machine smoke test.
        live_ids, name_to_id = _omnivoice_profiles()
        todo, healed, missing = _heal_todo(todo, live_ids, name_to_id)
        if missing:
            if started_omni and not keep_omni:
                omnivoice_stop()
            lines = "; ".join(
                f"cue {cid} speaker {spk!r} (voice_name={vn!r}, profile_id={pid!r})"
                for cid, spk, vn, pid in missing)
            raise CastingError(
                f"{len(missing)} cue(s) cast to OmniVoice have no matching profile "
                f"(by id or voice_name) in the running engine ({len(live_ids)} profiles "
                f"loaded): {lines}. Import/clone the voice (e.g. import_voices) so it "
                f"resolves, then re-render. Refusing to render a fallback voice.")
        if healed:
            uniq = sorted(set(healed))
            print(f"[stage 1 vo] self-healed {len(uniq)} voice(s) by name: "
                  + ", ".join(f"{vn}->{pid[:8]}" for vn, pid in uniq))

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


# ---------------------------------------------------------------------------
# Dub VO — re-render per-cue voiceover in a target language, FIT to the original
# cue's duration so the already-rendered picture and music/SFX offsets stay valid.
# Separate entry point from main(): the English render path above is untouched.
# ---------------------------------------------------------------------------

DUB_CACHE_VERSION = 1


def _fit_duration(path, target_dur, tol=0.04):
    """Hard-fit a wav to target_dur (seconds): atempo to correct drift > tol, then an
    exact -t trim / silence-pad so the result is target_dur to the sample. Guarantees
    the dubbed cue exactly fills its slot regardless of OmniVoice's best-effort sizing."""
    try:
        cur = probe_dur(path)
    except Exception:
        return
    if cur <= 0 or target_dur <= 0:
        return
    ratio = cur / target_dur
    work = path
    if abs(cur - target_dur) / target_dur > tol:
        # atempo only spans [0.5, 2.0]; chain two stages for extremes.
        tempo = max(0.25, min(4.0, ratio))
        chain = []
        t = tempo
        while t > 2.0:
            chain.append("atempo=2.0"); t /= 2.0
        while t < 0.5:
            chain.append("atempo=0.5"); t /= 0.5
        chain.append(f"atempo={t:.5f}")
        stretched = path + ".fit.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", path, "-af", ",".join(chain),
                        "-ac", "1", "-ar", str(TARGET_SR), "-c:a", "pcm_s16le", stretched],
                       check=True)
        work = stretched
    # Exact-length pad-or-trim: pad with silence then hard-cut to target_dur.
    out = path + ".exact.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", work, "-af", "apad", "-t", f"{target_dur:.4f}",
                    "-ac", "1", "-ar", str(TARGET_SR), "-c:a", "pcm_s16le", out],
                   check=True)
    os.replace(out, path)
    if work != path and os.path.exists(work):
        os.unlink(work)


def _dub_cache_key(lang, text, voice_cfg, target_dur):
    payload = {"lang": lang, "text": text or "", "profile_id": voice_cfg.get("profile_id"),
               "speed": voice_cfg.get("speed"), "guidance_scale": voice_cfg.get("guidance_scale"),
               "seed": voice_cfg.get("seed"), "instruct": voice_cfg.get("instruct"),
               "target_dur": round(float(target_dur), 3)}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def dub_vo(slug, lang, translations, ov_language, progress=None):
    """Re-render each DIALOGUE cue's VO in `lang` (OmniVoice name `ov_language`), fit to
    the English cue's duration, into vo/<lang>/<cue_id>.wav. Hold cues are skipped (the
    remux leaves their slot silent). Non-OmniVoice (piper/robot) cues keep their English
    wav (copied) — robot voices don't translate. Cached in vo/<lang>/.cache.json.
    Returns {rendered, skipped, copied, drifted, total}."""
    p = episode_paths(slug)
    m = load_manifest(slug)
    eng_vo = p["vo"]
    out_dir = f"{eng_vo}/{lang}"
    os.makedirs(out_dir, exist_ok=True)
    cache_path = f"{out_dir}/{CACHE_FILE_NAME}"
    cache = _load_cache(cache_path)

    dialogue = [c for c in m["cues"]
                if c.get("hold_seconds") is None and (c.get("vo") or "").strip()]
    needs_omni = any(_resolve_voice(m, c.get("speaker") or "").get("engine") == "omnivoice"
                     for c in dialogue)
    started = False
    live_ids, name_to_id = set(), {}
    if needs_omni:
        omnivoice_start(); started = True
        live_ids, name_to_id = _omnivoice_profiles()

    rendered = skipped = copied = drifted = 0
    cur_keys = {}
    try:
        for i, cue in enumerate(dialogue):
            cid = cue["id"]
            eng_wav = f"{eng_vo}/{cid}.wav"
            if not os.path.exists(eng_wav):
                continue  # no English wav to size against → skip
            target = probe_dur(eng_wav)
            voice = _resolve_voice(m, cue.get("speaker") or "")
            text = translations.get(cid) or cue.get("vo") or ""
            out = f"{out_dir}/{cid}.wav"
            key = _dub_cache_key(lang, text, voice, target)
            cur_keys[cid] = key
            if os.path.exists(out) and os.path.getsize(out) > 0 and cache.get(cid) == key:
                skipped += 1
                if progress:
                    progress(i + 1, len(dialogue))
                continue
            if voice.get("engine") == "omnivoice":
                pid, status = _heal_pid(voice, live_ids, name_to_id)
                if status == "missing":
                    if started:
                        omnivoice_stop()
                    raise CastingError(
                        f"dub: speaker {cue.get('speaker')!r} (voice_name="
                        f"{voice.get('voice_name')!r}) has no matching OmniVoice profile "
                        f"by id or name; import/clone the voice then re-run the dub.")
                _omnivoice(text, pid, out,
                           speed=voice.get("speed"), guidance_scale=voice.get("guidance_scale"),
                           seed=voice.get("seed"), instruct=voice.get("instruct"),
                           language=ov_language, duration=round(target, 3))
                before = probe_dur(out)
                _fit_duration(out, target)
                if abs(before - target) / target > 0.10:
                    drifted += 1
                rendered += 1
            else:
                # robot/piper voice — keep English audio for this line.
                _normalize(eng_wav, out)
                copied += 1
            cache[cid] = key
            _save_cache(cache_path, cache)
            if progress:
                progress(i + 1, len(dialogue))
    finally:
        if started:
            omnivoice_stop()
    return {"rendered": rendered, "skipped": skipped, "copied": copied,
            "drifted": drifted, "total": len(dialogue)}


if __name__ == "__main__":
    main(sys.argv[1])
