#!/usr/bin/env python3
"""Render missing VO via Piper HAL. Reads manifest cues, skips c09-c13 (cached)."""
import json, os, urllib.request, concurrent.futures, time

MANIFEST = "/mnt/storage/shares/MACU/episodes/ep5/manifest.json"
VO_DIR = "/mnt/storage/shares/MACU/episodes/ep5/vo"
PIPER = "http://10.0.0.245:5050/"

SKIP_CUES = {"c09","c10","c11","c12","c13"}

with open(MANIFEST) as f:
    m = json.load(f)

todo = [(c["id"], c["vo"]) for c in m["cues"] if c["id"] not in SKIP_CUES]
print(f"to render: {len(todo)} cues ({todo[0][0]}..{todo[-1][0]})")

def tts_one(cue_id, text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(PIPER, data=body,
        headers={"Content-Type":"application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        wav = r.read()
    out = f"{VO_DIR}/{cue_id}.wav"
    with open(out, "wb") as f:
        f.write(wav)
    return cue_id, len(wav), round(time.time()-t0, 2)

start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
    futs = [ex.submit(tts_one, cid, txt) for cid, txt in todo]
    for f in concurrent.futures.as_completed(futs):
        try:
            cid, sz, dt = f.result()
            print(f"  {cid}: {sz/1024:.1f} KB ({dt}s)")
        except Exception as e:
            print(f"  ERROR: {e}")
print(f"\ntotal: {round(time.time()-start,2)}s, all VO at {VO_DIR}")
