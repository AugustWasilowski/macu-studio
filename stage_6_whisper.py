#!/usr/bin/env python3
"""Stage 6: ASR the music-mixed nosubs audio via faster-whisper (CPU int8).

Idempotent: skips if /tmp/macu_whisper_<slug>.json exists.
Usage: python3 stage_6_whisper.py <slug>
"""
import sys, os, json, time, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths

WHISPER_VENV = "/tmp/whisper-venv/bin/python"

def main(slug):
    p = episode_paths(slug)
    src = p["music_nosubs"] if os.path.exists(p["music_nosubs"]) else p["nosubs"]
    wav = f"/tmp/macu_{slug}_audio.wav"
    out = f"/tmp/macu_whisper_{slug}.json"

    if os.path.exists(out) and os.path.getmtime(out) > os.path.getmtime(src):
        print(f"[stage 6 whisper] cached: {out}")
        return {"cached": True, "whisper": out}

    start = time.time()
    subprocess.run(["ffmpeg","-y","-i", src,"-vn","-ac","1","-ar","16000",
                    "-c:a","pcm_s16le", wav],
                   check=True, capture_output=True)

    script = f"""
import json, time
from faster_whisper import WhisperModel
model = WhisperModel("large-v3", device="cpu", compute_type="int8")
t0 = time.time()
segments, info = model.transcribe("{wav}", language="en", word_timestamps=True,
    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=300))
out_segs = []
for seg in segments:
    out_segs.append({{"id":seg.id,"start":round(seg.start,3),"end":round(seg.end,3),
                      "text":seg.text.strip(),
                      "words":[{{"w":w.word,"s":round(w.start,3),"e":round(w.end,3)}}
                               for w in (seg.words or [])]}})
with open("{out}","w") as f:
    json.dump({{"segments":out_segs,"duration":info.duration,"language":info.language}},f)
print(f"whisper: {{len(out_segs)}} segs, {{sum(len(s['words']) for s in out_segs)}} words, {{time.time()-t0:.1f}}s")
"""
    subprocess.run([WHISPER_VENV, "-c", script], check=True)
    print(f"[stage 6 whisper] {out} ({round(time.time()-start,2)}s)")
    return {"cached": False, "whisper": out, "wall_s": round(time.time()-start,2)}

if __name__ == "__main__":
    main(sys.argv[1])
