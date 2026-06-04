#!/usr/bin/env python3
"""Run faster-whisper on /tmp/ep5.wav with word timestamps; dump JSON."""
import json, time
from faster_whisper import WhisperModel

t0 = time.time()
# large-v3 already cached. Use GPU if available, else CPU int8.
model = WhisperModel("large-v3", device="cpu", compute_type="int8")
print(f"using CPU int8 ({time.time()-t0:.1f}s to load)")

t0 = time.time()
segments, info = model.transcribe(
    "/tmp/ep5.wav",
    language="en",
    word_timestamps=True,
    vad_filter=True,
    vad_parameters=dict(min_silence_duration_ms=300),
)

out_segs = []
for seg in segments:
    out_segs.append({
        "id": seg.id,
        "start": round(seg.start, 3),
        "end": round(seg.end, 3),
        "text": seg.text.strip(),
        "words": [{"w": w.word, "s": round(w.start,3), "e": round(w.end,3)}
                  for w in (seg.words or [])],
    })

dt = time.time() - t0
print(f"transcribed in {dt:.1f}s: {len(out_segs)} segments, {sum(len(s['words']) for s in out_segs)} words")
print(f"audio duration: {info.duration:.1f}s, RTF: {dt/info.duration:.2f}")

with open("/tmp/ep5_whisper.json","w") as f:
    json.dump({"segments": out_segs, "duration": info.duration,
               "language": info.language}, f, indent=2)
print("wrote /tmp/ep5_whisper.json")
