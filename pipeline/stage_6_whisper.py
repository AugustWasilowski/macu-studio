#!/usr/bin/env python3
"""Stage 6: ASR the music-mixed nosubs audio via faster-whisper (CPU int8).

Idempotent: skips if /tmp/macu_whisper_<slug>.json exists.
Usage: python3 stage_6_whisper.py <slug>
"""
import sys, os, json, time, subprocess, threading
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths, progress_tick

WHISPER_VENV = "/tmp/whisper-venv/bin/python"

# Estimated wall-time multiplier for faster-whisper large-v3 CPU int8 on max.
# Empirically ~10 min for a 4-min episode = 2.5×, padded a bit.
WHISPER_WALL_MULTIPLIER = 2.5


def _probe_duration(path):
    """Return audio duration in seconds, or None if ffprobe fails."""
    try:
        r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                            "-of","default=noprint_wrappers=1:nokey=1", path],
                           capture_output=True, text=True, check=True, timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return None


def main(slug):
    p = episode_paths(slug)
    src = p["nosubs"]   # transcribe clean VO (no music) for accurate sub timing
    wav = f"/tmp/macu_{slug}_audio.wav"
    out = f"/tmp/macu_whisper_{slug}.json"

    if os.path.exists(out) and os.path.getmtime(out) > os.path.getmtime(src):
        print(f"[stage 6 whisper] cached: {out}")
        return {"cached": True, "whisper": out}

    start = time.time()
    subprocess.run(["ffmpeg","-y","-i", src,"-vn","-ac","1","-ar","16000",
                    "-c:a","pcm_s16le", wav],
                   check=True, capture_output=True, timeout=900)

    # Background ticker: estimates fraction from elapsed / (audio_dur × multiplier),
    # capped at 0.95 so the post-subprocess tick(1.0) is the one that finalizes the zone.
    audio_dur = _probe_duration(wav)
    estimated_total = (audio_dur or 240.0) * WHISPER_WALL_MULTIPLIER
    stop_ticker = threading.Event()

    def _ticker():
        t0 = time.time()
        while not stop_ticker.wait(2.0):
            frac = min(0.95, (time.time() - t0) / estimated_total)
            progress_tick(6, "whisper", frac)

    th = threading.Thread(target=_ticker, daemon=True)
    th.start()

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
    try:
        # Cap the transcription so a wedged whisper process fails the stage (releasing
        # the render lock) instead of hanging. 30 min is far above a real episode's ASR.
        subprocess.run([WHISPER_VENV, "-c", script], check=True, timeout=1800)
    finally:
        stop_ticker.set()
    progress_tick(6, "whisper", 1.0)
    print(f"[stage 6 whisper] {out} ({round(time.time()-start,2)}s)")
    return {"cached": False, "whisper": out, "wall_s": round(time.time()-start,2)}

if __name__ == "__main__":
    main(sys.argv[1])
