#!/usr/bin/env python3
"""Stage 1: render Piper HAL VO for every cue.

Idempotent: skips cues whose vo/<cue_id>.wav already exists with size > 0.
Usage: python3 stage_1_vo.py <slug>
"""
import sys, json, os, urllib.request, concurrent.futures, time
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths, load_manifest, ensure_dirs, PIPER_URL

def tts_one(cue_id, text, out_path):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(PIPER_URL + "/", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        wav = r.read()
    with open(out_path, "wb") as f:
        f.write(wav)
    return cue_id, len(wav), round(time.time() - t0, 2)

def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    todo = []
    skipped = 0
    for cue in m["cues"]:
        out = f"{p['vo']}/{cue['id']}.wav"
        if os.path.exists(out) and os.path.getsize(out) > 0:
            skipped += 1
            continue
        todo.append((cue["id"], cue["vo"], out))
    print(f"[stage 1 vo] {len(todo)} to render, {skipped} cached")
    if not todo:
        return {"rendered": 0, "skipped": skipped}
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(tts_one, *t) for t in todo]
        for f in concurrent.futures.as_completed(futs):
            cid, sz, dt = f.result()
            print(f"  {cid} {sz/1024:.1f} KB ({dt}s)")
    print(f"[stage 1 vo] {len(todo)} rendered in {round(time.time()-start,2)}s")
    return {"rendered": len(todo), "skipped": skipped,
            "wall_s": round(time.time()-start, 2)}

if __name__ == "__main__":
    main(sys.argv[1])
