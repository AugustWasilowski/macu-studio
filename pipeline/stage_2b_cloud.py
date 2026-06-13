#!/usr/bin/env python3
"""Stage 2b: cloud (Higgsfield) shots — character stills, t2v/i2v video shots,
and audio-driven lipsync shots.

Runs concurrently with the local ComfyUI loop (stage_2_masters starts this in a
thread: cloud is network-bound, zeroscope is GPU-bound). All Higgsfield traffic
goes through the Studio backend's broker routes (:8774) — Studio is the only
token holder; this script never speaks MCP/OAuth itself.

Idempotent via clips/.hf_cache.json (see hf_cache.py): a clip whose hash matches
is skipped; the sidecar is updated after EACH success so a failed batch resumes
where it stopped. Lipsync VO longer than the 15s model cap is chunked at silence
boundaries and chained segment→segment via last-frame → start_image; segments
are conformed to their exact chunk duration so the concat is sample-aligned with
the VO that stage 4 muxes.

Usage: python3 stage_2b_cloud.py <slug>
"""
import json, math, mimetypes, os, random, re, subprocess, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import hf_cache as hfc
from lib import COMFY_URL, episode_paths, load_manifest, ensure_dirs, probe_dur, progress_tick

STUDIO_URL = os.environ.get("MACU_STUDIO_URL", "http://127.0.0.1:8774").rstrip("/")
MAX_CONCURRENT = 3        # parallel cloud jobs (Higgsfield free tier ~10; stay polite)
JOB_TIMEOUT = 900         # per-generation ceiling
STILL_TIMEOUT = 600
WORKFLOWS_DIR = Path(__file__).resolve().parent / "workflows"
LIPSYNC_FPS = 25          # the InfiniteTalk graph renders 25fps; stage 4 conforms to 24

# Sampler presets for the local/remote InfiniteTalk engines (manifest knob:
# higgsfield.lipsync_preset). quality = stronger lip lock, ~2x slower.
LIPSYNC_PRESETS = {
    "quality": {"steps": 10, "audio_cfg_scale": 3.0},
    "fast":    {"steps": 6,  "audio_cfg_scale": 1.0},
}

def _lipsync_preset(m):
    name = (m.get("higgsfield") or {}).get("lipsync_preset") or "quality"
    return name, LIPSYNC_PRESETS.get(name, LIPSYNC_PRESETS["quality"])

# Models whose media schema accepts a plain "image" reference role; everything
# else gets "start_image". Server-side auto-coercion covers the gray area.
_IMAGE_ROLE_MODELS = {"seedance_2_0", "video_standard", "cinematic_studio_3_0",
                      "cinematic_studio_video", "cinematic_studio_video_v2",
                      "marketing_studio_video", "wan2_6", "higgsfield_preset"}


# ---- Studio broker -----------------------------------------------------------------

def _api(method, path, body=None, timeout=120):
    url = f"{STUDIO_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:300]
        except Exception:
            pass
        raise RuntimeError(f"Studio {method} {path} -> {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"MACU Studio not reachable at {STUDIO_URL} ({e.reason}) — cloud shots "
            f"are brokered through it (systemctl start macu-studio, or remove the "
            f"higgsfield/lipsync shots from the manifest)") from None


def _wait_job(job_id, timeout=JOB_TIMEOUT, label=""):
    deadline = time.time() + timeout
    while True:
        res = _api("GET", f"/api/higgsfield/jobs/{job_id}?sync=true", timeout=120)
        st = str(res.get("status") or res.get("state") or "").lower()
        if any(s in st for s in ("completed", "succeeded", "success", "done")):
            urls = res.get("urls") or []
            if not urls:
                raise RuntimeError(f"{label}: job {job_id} finished but returned no media URLs")
            return urls
        if any(s in st for s in ("failed", "error", "nsfw", "cancel", "reject")):
            detail = res.get("error") or res.get("detail") or st
            raise RuntimeError(f"{label}: Higgsfield job {st} — {detail}")
        if time.time() > deadline:
            raise RuntimeError(f"{label}: job {job_id} still '{st or 'pending'}' after {int(timeout)}s")
        time.sleep(5)


def _download(url, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=600) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def _upload(path) -> str:
    return _api("POST", "/api/higgsfield/media/upload", {"path": str(path)}, timeout=600)["media_id"]


def _ff(args, label):
    r = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{label}: ffmpeg failed — {r.stderr[-800:]}")


# ---- stills -------------------------------------------------------------------------

def _ensure_stills(slug, m, ep):
    """Generate missing/stale character stills (via the Studio still routes, which
    own the image-gen flow + sidecar stamping)."""
    chars = m.get("characters") or {}
    made = 0
    for who in hfc.referenced_stills(m):
        char = chars.get(who) if isinstance(chars.get(who), dict) else {}
        p = hfc.still_path(ep, who)
        entries = hfc.load_sidecar(hfc.stills_sidecar_path(ep), "stills")
        fresh = p.exists() and (entries.get(who) is None or entries.get(who) == hfc.still_hash(char, m))
        if fresh:
            continue
        if not (char.get("still_prompt") or "").strip():
            if p.exists():
                continue  # hand-placed still, no prompt — trust it
            raise RuntimeError(
                f"[stage 2b cloud] character '{who}' is referenced by a cloud shot but has "
                f"no still ({p}) and no still_prompt to generate one")
        print(f"[stage 2b cloud] generating still for {who} ...")
        _api("POST", f"/api/episodes/{slug}/characters/{who}/still/regen", {}, timeout=60)
        deadline = time.time() + STILL_TIMEOUT
        while time.time() < deadline:
            st = _api("GET", f"/api/episodes/{slug}/characters/{who}/still/status", timeout=30)
            job = st.get("job") or {}
            if job.get("state") == "error":
                raise RuntimeError(f"[stage 2b cloud] still for {who} failed: {job.get('error')}")
            if job.get("state") == "done" or st.get("fresh"):
                made += 1
                break
            time.sleep(3)
        else:
            raise RuntimeError(f"[stage 2b cloud] still for {who} timed out after {STILL_TIMEOUT}s")
    return made


# ---- video shots ----------------------------------------------------------------------

def _media_role(model):
    return "image" if model in _IMAGE_ROLE_MODELS else "start_image"


def _gen_video_shot(slug, m, ep, cue, shot):
    sid = shot["id"]
    params = hfc.shot_params(shot, m)
    prompt = hfc.resolve_prompt(shot, m)
    if not prompt:
        raise RuntimeError(f"shot {sid}: empty prompt (no prompt field and '{shot.get('who')}' "
                           f"has no core prompt)")
    medias = []
    if shot.get("source_still"):
        still = hfc.resolve_still(shot, m, ep)
        if not still or not still.exists():
            raise RuntimeError(f"shot {sid}: source_still '{shot.get('source_still')}' not found at {still}")
        medias.append({"value": _upload(still), "role": _media_role(params["model"])})
    body = {"tool": "generate_video",
            "params": {**params, "prompt": prompt, "count": 1,
                       **({"medias": medias} if medias else {})}}
    job = _api("POST", "/api/higgsfield/generate", body, timeout=300)
    urls = _wait_job(job["job_id"], label=f"shot {sid}")
    mp4s = [u for u in urls if ".mp4" in u.split("?")[0].lower()] or urls
    _download(mp4s[0], hfc.clip_path(ep, sid))
    return sid


# ---- lipsync: local ComfyUI (wan21_infinitetalk) -----------------------------------------

def _comfy_upload(path: Path) -> str:
    """Upload a file into ComfyUI's input dir via /upload/image (it accepts any
    file type — LoadAudio reads the same input dir). Returns the stored name."""
    boundary = "----macu" + "".join(random.choices("0123456789abcdef", k=16))
    ct = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
        f"Content-Type: {ct}\r\n\r\n"
    ).encode() + path.read_bytes() + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{COMFY_URL}/upload/image", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    return out.get("name") or path.name


def _bind_workflow(workflow_id: str, **params):
    """Minimal mirror of the Studio registry's bind(): deep-copy the graph and
    apply params along meta.inputs paths."""
    wf = json.loads((WORKFLOWS_DIR / f"{workflow_id}.json").read_text())
    meta, graph = wf["meta"], json.loads(json.dumps(wf["graph"]))
    applied = dict(meta.get("defaults") or {})
    applied.update({k: v for k, v in params.items() if v is not None})
    if applied.get("seed") is None:
        applied["seed"] = random.randint(0, 2**32 - 1)
    for name, (node, key, field) in (meta.get("inputs") or {}).items():
        if name in applied:
            graph[str(node)][key][field] = applied[name]
    return graph, meta["output_node"]


def _conform_to_vo(raw: Path, out: Path, vo_dur: float, label: str) -> None:
    """Talking-head mp4 (25fps, model audio) → pipeline clip: video-only, 24fps,
    exactly vo_dur (stage 4 muxes the canonical VO wav)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    _ff(["-i", str(raw), "-an", "-r", "24",
         "-vf", f"tpad=stop_mode=clone:stop_duration={vo_dur:.4f}",
         "-t", f"{vo_dur:.4f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(out)], label)


def _gen_lipsync_local(slug, m, ep, cue, shot):
    """One-shot whole-VO talking head on the local/routed ComfyUI — InfiniteTalk's
    sliding window handles long audio natively, so no chunking here."""
    sid, cid = shot["id"], cue["id"]
    vo = ep / "vo" / f"{cid}.wav"
    if not vo.exists():
        raise RuntimeError(f"lipsync shot {sid}: vo/{cid}.wav missing — run stage 1 first")
    still = hfc.resolve_still(shot, m, ep)
    if not still or not still.exists():
        raise RuntimeError(f"lipsync shot {sid}: source_still required")
    vo_dur = probe_dur(str(vo))

    img_name = _comfy_upload(still)
    wav_name = _comfy_upload(vo)
    pname, preset = _lipsync_preset(m)
    graph, out_node = _bind_workflow(
        "wan21_infinitetalk",
        prompt=hfc.resolve_prompt(shot, m) or None,
        image=img_name, audio=wav_name,
        seed=shot.get("seed"),
        max_frames=int(vo_dur * LIPSYNC_FPS) + 1,
        steps=preset["steps"],
        audio_cfg_scale=preset["audio_cfg_scale"],
        filename_prefix=f"macu_lipsync_{slug}_{sid}",
    )
    req = urllib.request.Request(
        f"{COMFY_URL}/prompt",
        data=json.dumps({"prompt": graph, "client_id": f"macu-lipsync-{slug}"}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            pid = json.loads(r.read())["prompt_id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"lipsync {sid}: ComfyUI rejected the workflow ({e.code}): "
                           f"{e.read().decode()[:400]} — are the talking-head models + "
                           f"WanVideoWrapper/VHS/KJNodes installed (--with-talking-head)?")

    # Slow renders (minutes per VO second on small GPUs). Stall-based watchdog:
    # as long as ComfyUI's queue is busy we keep waiting, up to a hard ceiling.
    HARD_S = 3 * 3600
    STALL_S = 600
    start = time.time()
    last_busy = time.time()
    files = None
    while True:
        time.sleep(10)
        try:
            with urllib.request.urlopen(f"{COMFY_URL}/history/{pid}", timeout=30) as r:
                entry = json.loads(r.read()).get(pid)
        except Exception:
            entry = None
        if entry and entry.get("status", {}).get("completed"):
            outs = entry.get("outputs", {}).get(out_node, {}) or {}
            files = outs.get("gifs") or outs.get("videos") or outs.get("images") or []
            if not files:
                raise RuntimeError(f"lipsync {sid}: graph finished but node {out_node} "
                                   f"produced no video output")
            break
        if entry and entry.get("status", {}).get("status_str") == "error":
            msgs = [x for x in entry.get("status", {}).get("messages", [])
                    if x and x[0] == "execution_error"]
            detail = (msgs[0][1].get("exception_message") if msgs else "") or "execution error"
            raise RuntimeError(f"lipsync {sid}: ComfyUI error — {str(detail)[:400]}")
        try:
            with urllib.request.urlopen(f"{COMFY_URL}/queue", timeout=15) as r:
                q = json.loads(r.read())
            busy = bool(q.get("queue_running") or q.get("queue_pending"))
        except Exception:
            busy = False
        if busy:
            last_busy = time.time()
        elif time.time() - last_busy > STALL_S and not entry:
            raise RuntimeError(f"lipsync {sid}: ComfyUI lost the job (idle queue, "
                               f"no history) — it likely crashed or was restarted")
        if time.time() - start > HARD_S:
            raise RuntimeError(f"lipsync {sid}: still rendering after {HARD_S//3600}h — giving up")

    f0 = files[0]
    from urllib.parse import urlencode
    url = f"{COMFY_URL}/view?" + urlencode({
        "filename": f0["filename"], "subfolder": f0.get("subfolder", ""),
        "type": f0.get("type", "output")})
    work = ep / ".work" / f"hf_{sid}"
    work.mkdir(parents=True, exist_ok=True)
    raw = work / "local_raw.mp4"
    _download(url, raw)
    _conform_to_vo(raw, hfc.clip_path(ep, sid), vo_dur, f"lipsync {sid} conform")
    print(f"  lipsync {sid}: local ComfyUI done ({vo_dur:.1f}s VO, "
          f"{round(time.time()-start)}s wall)")
    return sid


# ---- lipsync: remote render service (leo-render :8779 API) --------------------------------

# The remote box OOMs on long single passes (observed: 258 frames / 10.3s died,
# 220 frames survived on Leo's GPU). Chunk anything longer than this and chain
# via last-frame → next start image, exactly like the Higgsfield path.
REMOTE_MAX_S = 7.0


def _remote_one(base_url, name, image_path, audio_path, dur, preset, raw_dest):
    """One remote render: submit, poll, land the raw mp4 at raw_dest."""
    body = {"name": name,
            "image_path": str(image_path), "audio_path": str(audio_path),
            "params": {"frames": int(dur * LIPSYNC_FPS) + 1, **preset}}
    req = urllib.request.Request(f"{base_url}/render", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            job_id = json.loads(r.read())["job_id"]
    except urllib.error.URLError as e:
        raise RuntimeError(f"{name}: remote render service unreachable at "
                           f"{base_url} ({getattr(e, 'reason', e)}) — start it, or "
                           f"reroute lipsync in Settings → Engines")
    deadline = time.time() + max(1800.0, dur * 240)   # cold start + queue headroom
    while True:
        time.sleep(20)
        with urllib.request.urlopen(f"{base_url}/status/{job_id}", timeout=30) as r:
            st = json.loads(r.read())
        if st.get("status") == "done":
            output = st.get("output")
            break
        if st.get("status") == "error":
            raise RuntimeError(f"{name}: remote render failed — {st.get('error')}")
        if st.get("status") is None:
            # service restarted and lost the queue — the job is gone, not slow
            raise RuntimeError(f"{name}: remote render lost job {job_id} "
                               f"(service restart?) — re-run to retry")
        if time.time() > deadline:
            raise RuntimeError(f"{name}: remote render still "
                               f"'{st.get('status')}' after {int(deadline)}s")
    src = Path(output) if output else None
    if src and src.exists():
        import shutil
        shutil.copyfile(src, raw_dest)
    else:
        _download(f"{base_url}/result/{job_id}", raw_dest)
    return raw_dest


def _gen_lipsync_remote(slug, m, ep, cue, shot, base_url):
    sid, cid = shot["id"], cue["id"]
    vo = ep / "vo" / f"{cid}.wav"
    if not vo.exists():
        raise RuntimeError(f"lipsync shot {sid}: vo/{cid}.wav missing — run stage 1 first")
    still = hfc.resolve_still(shot, m, ep)
    if not still or not still.exists():
        raise RuntimeError(f"lipsync shot {sid}: source_still required")
    vo_dur = probe_dur(str(vo))
    pname, preset = _lipsync_preset(m)
    start = time.time()
    work = ep / ".work" / f"hf_{sid}"
    work.mkdir(parents=True, exist_ok=True)

    if vo_dur <= REMOTE_MAX_S:
        raw = work / "remote_raw.mp4"
        _remote_one(base_url, f"{slug}-{sid}", still, vo, vo_dur, preset, raw)
        _conform_to_vo(raw, hfc.clip_path(ep, sid), vo_dur, f"lipsync {sid} conform")
        print(f"  lipsync {sid}: remote render done ({vo_dur:.1f}s VO, "
              f"{round(time.time()-start)}s wall)")
        return sid

    # Long VO: chunk at silence boundaries + chain last frame → next start image.
    # Resume guard mirrors the Higgsfield chain (segments only reusable for the
    # same VO/still/preset/cap fingerprint).
    state_p = work / "chain_state.json"
    fingerprint = {"vo_sha": hfc.file_sha(vo), "still_sha": hfc.file_sha(still),
                   "engine": "remote_render", "preset": pname, "cap": REMOTE_MAX_S}
    try:
        old_fp = json.loads(state_p.read_text())
    except Exception:
        old_fp = None
    if old_fp != fingerprint:
        for f in work.iterdir():
            f.unlink()
        state_p.write_text(json.dumps(fingerprint, indent=2))

    chunks = _chunk_bounds(vo_dur, vo, cap=REMOTE_MAX_S)
    print(f"  lipsync {sid}: {vo_dur:.1f}s VO -> {len(chunks)} remote segment(s)")
    prev_image = still
    segs = []
    for i, (a, b) in enumerate(chunks):
        cdur = b - a
        seg = work / f"seg{i:02d}.mp4"
        segs.append(seg)
        if seg.exists():
            last = work / f"last{i:02d}.png"
            if not last.exists():
                _ff(["-sseof", "-0.05", "-i", str(seg), "-frames:v", "1", str(last)],
                    f"lipsync {sid} lastframe {i}")
            prev_image = last
            print(f"    seg{i:02d} cached")
            continue
        chunk_wav = work / f"chunk{i:02d}.wav"
        _ff(["-i", str(vo), "-ss", f"{a:.4f}", "-t", f"{cdur:.4f}",
             "-c:a", "pcm_s16le", str(chunk_wav)], f"lipsync {sid} chunk {i}")
        raw = work / f"raw{i:02d}.mp4"
        _remote_one(base_url, f"{slug}-{sid}-seg{i}", prev_image, chunk_wav,
                    cdur, preset, raw)
        _ff(["-i", str(raw), "-an", "-r", "24",
             "-vf", f"tpad=stop_mode=clone:stop_duration={cdur:.4f}",
             "-t", f"{cdur:.4f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", str(seg)], f"lipsync {sid} conform {i}")
        last = work / f"last{i:02d}.png"
        _ff(["-sseof", "-0.05", "-i", str(seg), "-frames:v", "1", str(last)],
            f"lipsync {sid} lastframe {i}")
        prev_image = last
        print(f"    seg{i:02d} done ({cdur:.1f}s)")

    clist = work / "concat.txt"
    clist.write_text("".join(f"file '{x}'\n" for x in segs))
    raw_full = work / "chained.mp4"
    _ff(["-f", "concat", "-safe", "0", "-i", str(clist),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", "24", str(raw_full)], f"lipsync {sid} concat")
    _conform_to_vo(raw_full, hfc.clip_path(ep, sid), vo_dur, f"lipsync {sid} conform")
    print(f"  lipsync {sid}: remote chain done ({vo_dur:.1f}s VO, {len(chunks)} segs, "
          f"{round(time.time()-start)}s wall)")
    return sid


# ---- lipsync shots (Higgsfield cloud: chunk + chain) ---------------------------------------

def _silence_midpoints(wav):
    """[(midpoint_s)] of detected silences — candidate chunk boundaries."""
    r = subprocess.run(["ffmpeg", "-i", str(wav), "-af",
                        "silencedetect=noise=-35dB:d=0.25", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def _chunk_bounds(dur, wav, cap=None):
    """Split [0,dur] into ≤cap chunks, snapping each boundary to the nearest
    silence midpoint (tolerance scales with the cap) so seams land in pauses."""
    cap = cap or hfc.CHUNK_MAX_S
    if dur <= cap:
        return [(0.0, dur)]
    n = math.ceil(dur / cap)
    targets = [dur * i / n for i in range(1, n)]
    tol = min(2.5, cap * 0.15)
    silences = _silence_midpoints(wav)
    bounds = [0.0]
    for t in targets:
        near = [s for s in silences if abs(s - t) <= tol and s > bounds[-1] + 1.0]
        pick = min(near, key=lambda s: abs(s - t)) if near else t
        bounds.append(min(pick, dur - 1.0))
    bounds.append(dur)
    # Re-validate (a snapped boundary can stretch a chunk past the cap).
    out = []
    for a, b in zip(bounds, bounds[1:]):
        seg = b - a
        if seg > cap + tol:
            mid = a + seg / 2
            out += [(a, mid), (mid, b)]
        else:
            out.append((a, b))
    return out


def _gen_lipsync_shot(slug, m, ep, cue, shot):
    sid, cid = shot["id"], cue["id"]
    vo = ep / "vo" / f"{cid}.wav"
    if not vo.exists():
        raise RuntimeError(f"lipsync shot {sid}: vo/{cid}.wav missing — run stage 1 first")
    still = hfc.resolve_still(shot, m, ep)
    if not still or not still.exists():
        raise RuntimeError(f"lipsync shot {sid}: source_still required (character key with a "
                           f"generated still, or an episode-relative image path)")
    params = hfc.shot_params(shot, m)
    model = params["model"]
    dur = probe_dur(str(vo))
    work = ep / ".work" / f"hf_{sid}"
    work.mkdir(parents=True, exist_ok=True)

    # Resume guard: segments are only reusable for the same VO + still + model.
    state_p = work / "chain_state.json"
    fingerprint = {"vo_sha": hfc.file_sha(vo), "still_sha": hfc.file_sha(still),
                   "model": model, "chunk_max_s": hfc.CHUNK_MAX_S}
    try:
        old = json.loads(state_p.read_text())
    except Exception:
        old = None
    if old != fingerprint:
        for f in work.iterdir():
            f.unlink()
        state_p.write_text(json.dumps(fingerprint, indent=2))

    chunks = _chunk_bounds(dur, vo)
    print(f"  lipsync {sid}: {dur:.1f}s VO -> {len(chunks)} segment(s)")
    prev_image = still
    segs = []
    for i, (a, b) in enumerate(chunks):
        cdur = b - a
        seg = work / f"seg{i:02d}.mp4"
        segs.append(seg)
        if seg.exists():
            # Resume: reuse the conformed segment; re-extract its last frame if
            # the png didn't survive (it seeds the next segment's start_image).
            last = work / f"last{i:02d}.png"
            if not last.exists():
                _ff(["-sseof", "-0.05", "-i", str(seg), "-frames:v", "1", str(last)],
                    f"lipsync {sid} lastframe {i}")
            prev_image = last
            print(f"    seg{i:02d} cached")
            continue
        chunk_wav = work / f"chunk{i:02d}.wav"
        _ff(["-i", str(vo), "-ss", f"{a:.4f}", "-t", f"{cdur:.4f}",
             "-c:a", "pcm_s16le", str(chunk_wav)], f"lipsync {sid} chunk {i}")
        body = {"tool": "generate_video",
                "params": {**params,
                           "duration": max(2, min(15, math.ceil(cdur))),
                           "prompt": hfc.resolve_prompt(shot, m)
                                     or "talking head, mouth synced to the voice, subtle natural motion",
                           "count": 1,
                           "medias": [
                               {"value": _upload(prev_image), "role": _media_role(model)},
                               {"value": _upload(chunk_wav), "role": "audio"},
                           ]}}
        job = _api("POST", "/api/higgsfield/generate", body, timeout=300)
        urls = _wait_job(job["job_id"], label=f"lipsync {sid} seg{i}")
        mp4s = [u for u in urls if ".mp4" in u.split("?")[0].lower()] or urls
        raw = work / f"raw{i:02d}.mp4"
        _download(mp4s[0], raw)
        # Conform to the exact chunk duration (clone-pad if the model came back
        # short, cut if long) — keeps the concat sample-aligned with the VO.
        _ff(["-i", str(raw), "-an", "-r", "24",
             "-vf", f"tpad=stop_mode=clone:stop_duration={cdur:.4f}",
             "-t", f"{cdur:.4f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", str(seg)], f"lipsync {sid} conform {i}")
        last = work / f"last{i:02d}.png"
        _ff(["-sseof", "-0.05", "-i", str(seg), "-frames:v", "1", str(last)],
            f"lipsync {sid} lastframe {i}")
        prev_image = last
        print(f"    seg{i:02d} done ({cdur:.1f}s)")

    out = hfc.clip_path(ep, sid)
    out.parent.mkdir(parents=True, exist_ok=True)
    if len(segs) == 1:
        import shutil
        shutil.copy2(segs[0], out)
    else:
        clist = work / "concat.txt"
        clist.write_text("".join(f"file '{s}'\n" for s in segs))
        _ff(["-f", "concat", "-safe", "0", "-i", str(clist),
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-r", "24", str(out)], f"lipsync {sid} concat")
    return sid


# ---- main ----------------------------------------------------------------------------

def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    ep = Path(p["base"])

    cloud = list(hfc.cloud_shots(m))
    if not cloud:
        return {"cloud_rendered": 0, "cloud_skipped": 0}

    # Engine routing (Settings → Engines). Lipsync can run on Higgsfield, the
    # local/routed ComfyUI (wan21_infinitetalk), or a remote render service.
    eng_cfg = _api("GET", "/api/engines", timeout=30)
    lipsync_engine = (eng_cfg.get("routing") or {}).get("lipsync") or "higgsfield"
    remote_ep = (eng_cfg.get("endpoints") or {}).get("remote_render") or {}
    remote_url = remote_ep.get("url", "").rstrip("/") if remote_ep.get("enabled") else ""
    if lipsync_engine == "remote_render" and not remote_url:
        raise RuntimeError("[stage 2b cloud] lipsync is routed to the remote render "
                           "service but its URL isn't set/enabled — Settings → Engines")

    needs_hf = any(s.get("kind") == "higgsfield" for _c, s in cloud) \
        or (lipsync_engine == "higgsfield"
            and any(s.get("kind") == "lipsync" for _c, s in cloud))
    if needs_hf:
        auth = _api("GET", "/api/higgsfield/auth", timeout=30)
        if not auth.get("connected"):
            raise RuntimeError("[stage 2b cloud] Higgsfield not connected — connect in "
                               "Studio Settings → Higgsfield (or reroute/remove the cloud shots)")

    stills_made = _ensure_stills(slug, m, ep)

    sc_path = hfc.clips_sidecar_path(ep)
    lock = threading.Lock()
    entries = hfc.load_sidecar(sc_path, "shots")
    todo = []
    for cue, shot in cloud:
        st = hfc.shot_state(shot, cue, m, ep, entries, lipsync_engine=lipsync_engine)
        if st["fresh"]:
            continue
        todo.append((cue, shot, st["hash"]))
    skipped = len(cloud) - len(todo)
    print(f"[stage 2b cloud] {len(todo)} shot(s) to generate, {skipped} cached, "
          f"{stills_made} still(s) made (lipsync engine: {lipsync_engine})")
    if not todo:
        return {"cloud_rendered": 0, "cloud_skipped": skipped, "stills": stills_made}

    start = time.time()
    done = 0
    errors = []

    def work_one(item):
        cue, shot, h = item
        if shot.get("kind") == "lipsync":
            if lipsync_engine == "local_wan":
                sid = _gen_lipsync_local(slug, m, ep, cue, shot)
            elif lipsync_engine == "remote_render":
                sid = _gen_lipsync_remote(slug, m, ep, cue, shot, remote_url)
            else:
                sid = _gen_lipsync_shot(slug, m, ep, cue, shot)
        else:
            sid = _gen_video_shot(slug, m, ep, cue, shot)
        with lock:
            cur = hfc.load_sidecar(sc_path, "shots")
            cur[sid] = h
            hfc.save_sidecar(sc_path, "shots", cur)
        return sid

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as ex:
        futs = {ex.submit(work_one, it): it for it in todo}
        for fut in as_completed(futs):
            cue, shot, _h = futs[fut]
            try:
                sid = fut.result()
                done += 1
                print(f"  done {sid:24} +{round(time.time()-start, 1)}s")
            except Exception as e:
                errors.append(f"{shot.get('id')}: {e}")
            progress_tick(2, "cloud", (done + len(errors)) / len(todo))

    if errors:
        raise RuntimeError(f"[stage 2b cloud] {len(errors)}/{len(todo)} shot(s) failed "
                           f"({done} succeeded and are cached):\n  " + "\n  ".join(errors))
    return {"cloud_rendered": done, "cloud_skipped": skipped, "stills": stills_made,
            "cloud_wall_s": round(time.time() - start, 2)}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=2))
