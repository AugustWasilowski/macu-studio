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
import json, math, os, re, subprocess, sys, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import hf_cache as hfc
from lib import episode_paths, load_manifest, ensure_dirs, probe_dur, progress_tick

STUDIO_URL = os.environ.get("MACU_STUDIO_URL", "http://127.0.0.1:8774").rstrip("/")
MAX_CONCURRENT = 3        # parallel cloud jobs (Higgsfield free tier ~10; stay polite)
JOB_TIMEOUT = 900         # per-generation ceiling
STILL_TIMEOUT = 600

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


# ---- lipsync shots -----------------------------------------------------------------------

def _silence_midpoints(wav):
    """[(midpoint_s)] of detected silences — candidate chunk boundaries."""
    r = subprocess.run(["ffmpeg", "-i", str(wav), "-af",
                        "silencedetect=noise=-35dB:d=0.25", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def _chunk_bounds(dur, wav):
    """Split [0,dur] into ≤CHUNK_MAX_S chunks, snapping each boundary to the
    nearest silence midpoint within ±2.5s so seams land in pauses."""
    if dur <= hfc.CHUNK_MAX_S:
        return [(0.0, dur)]
    n = math.ceil(dur / hfc.CHUNK_MAX_S)
    targets = [dur * i / n for i in range(1, n)]
    silences = _silence_midpoints(wav)
    bounds = [0.0]
    for t in targets:
        near = [s for s in silences if abs(s - t) <= 2.5 and s > bounds[-1] + 1.0]
        pick = min(near, key=lambda s: abs(s - t)) if near else t
        bounds.append(min(pick, dur - 1.0))
    bounds.append(dur)
    # Re-validate the cap (a snapped boundary can stretch a chunk past 15s).
    out = []
    for a, b in zip(bounds, bounds[1:]):
        seg = b - a
        if seg > 15.0:
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

    auth = _api("GET", "/api/higgsfield/auth", timeout=30)
    if not auth.get("connected"):
        raise RuntimeError("[stage 2b cloud] Higgsfield not connected — connect in "
                           "Studio Settings → Higgsfield (or remove the cloud shots)")

    stills_made = _ensure_stills(slug, m, ep)

    sc_path = hfc.clips_sidecar_path(ep)
    lock = threading.Lock()
    entries = hfc.load_sidecar(sc_path, "shots")
    todo = []
    for cue, shot in cloud:
        st = hfc.shot_state(shot, cue, m, ep, entries)
        if st["fresh"]:
            continue
        todo.append((cue, shot, st["hash"]))
    skipped = len(cloud) - len(todo)
    print(f"[stage 2b cloud] {len(todo)} shot(s) to generate, {skipped} cached, "
          f"{stills_made} still(s) made")
    if not todo:
        return {"cloud_rendered": 0, "cloud_skipped": skipped, "stills": stills_made}

    start = time.time()
    done = 0
    errors = []

    def work_one(item):
        cue, shot, h = item
        if shot.get("kind") == "lipsync":
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
