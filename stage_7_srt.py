#!/usr/bin/env python3
"""Stage 7: align manifest VO text against whisper words; emit SRT.

Usage: python3 stage_7_srt.py <slug>
"""
import sys, os, re, json
from difflib import SequenceMatcher
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths, load_manifest

MAX_WORDS = 7
MAX_DUR = 3.0
MIN_DUR = 0.7
END_PAD = 0.08
BREAK = set(".!?")
SOFT  = set(",;:")

def norm(w): return re.sub(r"[^a-z']", "", w.lower())

def srt_ts(t):
    t = max(0.0, t)
    h = int(t//3600); m = int((t%3600)//60); s = t - h*3600 - m*60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".",",")

def main(slug):
    p = episode_paths(slug)
    out_srt = p["out_srt"]
    whisper_path = f"/tmp/macu_whisper_{slug}.json"
    if not os.path.exists(whisper_path):
        raise FileNotFoundError(whisper_path)

    m = load_manifest(slug)
    with open(whisper_path) as f:
        wh = json.load(f)

    manifest_words = []
    for cue in m["cues"]:
        for tok in re.findall(r"\S+", cue["vo"]):
            n = norm(tok)
            if n:
                manifest_words.append({"tok": tok, "norm": n, "cue": cue["id"]})
    wh_words = []
    for seg in wh["segments"]:
        for w in seg["words"]:
            n = norm(w["w"])
            if n: wh_words.append({"norm": n, "s": w["s"], "e": w["e"]})

    sm = SequenceMatcher(a=[w["norm"] for w in manifest_words],
                         b=[w["norm"] for w in wh_words], autojunk=False)
    matched = [None]*len(manifest_words)
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            matched[block.a+k] = block.b+k

    last_e = 0.0
    n_match = 0
    for mi, mw in enumerate(manifest_words):
        wi = matched[mi]
        if wi is not None:
            mw["s"] = wh_words[wi]["s"]; mw["e"] = wh_words[wi]["e"]
            mw["matched"] = True; last_e = mw["e"]; n_match += 1
        else:
            mw["matched"] = False
    # Interpolate unmatched runs
    i = 0
    while i < len(manifest_words):
        if manifest_words[i]["matched"]:
            i += 1; continue
        a = i
        while i < len(manifest_words) and not manifest_words[i]["matched"]:
            i += 1
        b = i
        prev_e = manifest_words[a-1]["e"] if a > 0 else 0.0
        next_s = manifest_words[b]["s"] if b < len(manifest_words) else (prev_e + 0.4*(b-a))
        span = max(0.05, next_s - prev_e)
        per = span / (b - a + 1)
        for k, j in enumerate(range(a, b)):
            manifest_words[j]["s"] = prev_e + per*(k+0.1)
            manifest_words[j]["e"] = prev_e + per*(k+0.9)

    chunks = []
    i = 0
    while i < len(manifest_words):
        j = i
        while j < len(manifest_words):
            n = j - i + 1
            dur = manifest_words[j]["e"] - manifest_words[i]["s"]
            last = manifest_words[j]["tok"][-1]
            if n >= MAX_WORDS or dur >= MAX_DUR: break
            if last in BREAK and n >= 2: break
            if last in SOFT and n >= 5: break
            if j+1 < len(manifest_words) and manifest_words[j+1]["cue"] != manifest_words[i]["cue"]: break
            j += 1
        s = manifest_words[i]["s"]
        e = max(manifest_words[j]["e"] + END_PAD, s + MIN_DUR)
        chunks.append({"s": s, "e": e,
                       "text": " ".join(w["tok"] for w in manifest_words[i:j+1])})
        i = j + 1
    for k in range(len(chunks)-1):
        if chunks[k]["e"] > chunks[k+1]["s"] - 0.02:
            chunks[k]["e"] = max(chunks[k]["s"]+MIN_DUR, chunks[k+1]["s"]-0.02)
    with open(out_srt,"w") as f:
        for idx, c in enumerate(chunks, 1):
            f.write(f"{idx}\n{srt_ts(c['s'])} --> {srt_ts(c['e'])}\n{c['text']}\n\n")
    print(f"[stage 7 srt] {len(chunks)} cues, "
          f"{n_match}/{len(manifest_words)} matched -> {out_srt}")
    return {"cues": len(chunks), "matched_pct": round(100*n_match/len(manifest_words),1),
            "srt": out_srt}

if __name__ == "__main__":
    main(sys.argv[1])
