#!/usr/bin/env python3
"""SRT that uses manifest VO text (proper case + punctuation) at Whisper timings.

Approach:
 1. Concat all 27 manifest cue VO texts in order → "ground truth" word stream.
 2. Whisper gave us a word stream with timings on the assembled audio.
 3. Greedy align: walk both streams; whisper sometimes splits/skips/garbles, so
    we use a small lookahead window on the whisper side to find each
    manifest word, matching loosely on lowercased letters-only.
 4. Chunk the manifest stream into <=7-word / <=3.0s lines, breaking at
    punctuation boundaries when possible.
 5. Use the matched whisper start/end as the SRT timings."""
import json, re, sys

MANIFEST = "/mnt/storage/shares/MACU/episodes/ep5/manifest.json"
WHISPER  = "/tmp/ep5_whisper.json"
SRT_OUT  = "/mnt/storage/shares/MACU/episodes/ep5/final/ep5.srt"

MAX_WORDS = 7
MAX_DUR   = 3.0
MIN_DUR   = 0.7
END_PAD   = 0.08
BREAK_AT  = set(".!?")
SOFT_BREAK= set(",;:")

def norm(w):
    return re.sub(r"[^a-z']", "", w.lower())

def srt_ts(t):
    t = max(0.0, t)
    h = int(t // 3600); m = int((t % 3600) // 60); s = t - h*3600 - m*60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".",",")

# 1. Load manifest, build word stream with original tokens
with open(MANIFEST) as f:
    m = json.load(f)

manifest_words = []  # list of {tok, norm, cue_id}
for cue in m["cues"]:
    for tok in re.findall(r"\S+", cue["vo"]):
        n = norm(tok)
        if n:
            manifest_words.append({"tok": tok, "norm": n, "cue": cue["id"]})

# 2. Load whisper words
with open(WHISPER) as f:
    wh = json.load(f)
wh_words = []
for seg in wh["segments"]:
    for w in seg["words"]:
        n = norm(w["w"])
        if n:
            wh_words.append({"norm": n, "s": w["s"], "e": w["e"]})

print(f"manifest words: {len(manifest_words)}  whisper words: {len(wh_words)}")

# 3. Sequence-align (difflib) the two normalized streams. Whisper drops/splits
# words, so a greedy one-way walk gets stuck — DP finds the matching blocks.
from difflib import SequenceMatcher
m_norms = [w["norm"] for w in manifest_words]
w_norms = [w["norm"] for w in wh_words]
sm = SequenceMatcher(a=m_norms, b=w_norms, autojunk=False)
# matched_pairs[mi] = wi if matched, else None
matched_pairs = [None] * len(manifest_words)
for block in sm.get_matching_blocks():
    for k in range(block.size):
        matched_pairs[block.a + k] = block.b + k

# Fill timings: matched ones get whisper time; unmatched interpolate linearly
# between neighbours.
last_e = 0.0
matched = 0
for mi, mw in enumerate(manifest_words):
    wi = matched_pairs[mi]
    if wi is not None:
        mw["s"] = wh_words[wi]["s"]
        mw["e"] = wh_words[wi]["e"]
        mw["matched"] = True
        matched += 1
        last_e = mw["e"]
    else:
        mw["matched"] = False
# Second pass: interpolate unmatched between matched neighbours
mi = 0
while mi < len(manifest_words):
    if manifest_words[mi]["matched"]:
        mi += 1
        continue
    # Find run [a, b) of unmatched
    a = mi
    while mi < len(manifest_words) and not manifest_words[mi]["matched"]:
        mi += 1
    b = mi
    prev_e = manifest_words[a-1]["e"] if a > 0 else 0.0
    next_s = manifest_words[b]["s"] if b < len(manifest_words) else (prev_e + 0.4*(b-a))
    span = max(0.05, next_s - prev_e)
    per = span / (b - a + 1)
    for k, j in enumerate(range(a, b)):
        manifest_words[j]["s"] = prev_e + per * (k + 0.1)
        manifest_words[j]["e"] = prev_e + per * (k + 0.9)

matched = sum(1 for w in manifest_words if w.get("matched"))
print(f"matched {matched}/{len(manifest_words)} ({100*matched/len(manifest_words):.1f}%)")

# 4. Chunk into SRT entries
chunks = []
i = 0
while i < len(manifest_words):
    j = i
    while j < len(manifest_words):
        n = j - i + 1
        dur = manifest_words[j]["e"] - manifest_words[i]["s"]
        last_char = manifest_words[j]["tok"][-1]
        if n >= MAX_WORDS:
            break
        if dur >= MAX_DUR:
            break
        # Hard break at sentence-ending punctuation
        if last_char in BREAK_AT and n >= 2:
            break
        # Soft break at comma if we already have decent length
        if last_char in SOFT_BREAK and n >= 5:
            break
        # Cue boundary forces a break
        if j+1 < len(manifest_words) and manifest_words[j+1]["cue"] != manifest_words[i]["cue"]:
            break
        j += 1

    s = manifest_words[i]["s"]
    e = max(manifest_words[j]["e"] + END_PAD, s + MIN_DUR)
    text = " ".join(w["tok"] for w in manifest_words[i:j+1])
    chunks.append({"s": s, "e": e, "text": text})
    i = j + 1

# Prevent overlaps
for k in range(len(chunks)-1):
    if chunks[k]["e"] > chunks[k+1]["s"] - 0.02:
        chunks[k]["e"] = max(chunks[k]["s"] + MIN_DUR, chunks[k+1]["s"] - 0.02)

with open(SRT_OUT,"w") as f:
    for idx, c in enumerate(chunks, 1):
        f.write(f"{idx}\n{srt_ts(c['s'])} --> {srt_ts(c['e'])}\n{c['text']}\n\n")

import statistics
durs = [c["e"]-c["s"] for c in chunks]
wc   = [len(c["text"].split()) for c in chunks]
print(f"Wrote {SRT_OUT}  ({len(chunks)} cues)")
print(f"  dur:   mean={statistics.mean(durs):.2f}s  max={max(durs):.2f}s  min={min(durs):.2f}s")
print(f"  words: mean={statistics.mean(wc):.1f}  max={max(wc)}  min={min(wc)}")
