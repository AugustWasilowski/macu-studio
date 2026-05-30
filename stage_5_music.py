#!/usr/bin/env python3
"""Stage 5: mix manifest.music beds into the nosubs audio.

Idempotent: if manifest.music is absent or .enabled=false, copies nosubs over to
music_nosubs unchanged. Otherwise builds the beds + amix.

Usage: python3 stage_5_music.py <slug>
"""
import sys, os, json, random, subprocess, shutil
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths, load_manifest, ensure_dirs, probe_dur

def run(cmd):
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print("FAIL:", " ".join(cmd[:6])); print(e.stderr[-1500:]); raise

def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    music = m.get("music") or {}
    music_nosubs = p["music_nosubs"]

    if not music.get("enabled"):
        print("[stage 5 music] disabled, passing through")
        shutil.copy2(p["nosubs"], music_nosubs)
        return {"skipped": True, "music_nosubs": music_nosubs}

    # Cue durations from stage 4
    cdurs_path = f"{p['work']}/cue_durs.json"
    if os.path.exists(cdurs_path):
        with open(cdurs_path) as f:
            cue_dur = json.load(f)
    else:
        # Re-probe per-cue mp4s
        cue_dur = {}
        for cue in m["cues"]:
            cue_dur[cue["id"]] = probe_dur(f"{p['work']}/{cue['id']}.mp4")
    total_dur = probe_dur(p["nosubs"])

    # Cumulative starts
    cum = {}; t = 0.0
    for cue in m["cues"]:
        cum[cue["id"]] = t
        t += cue_dur[cue["id"]]

    random.seed()
    beds_info = []
    bed_wavs = []
    for bed in music["beds"]:
        sum_dur = sum(cue_dur[c] for c in bed["cues"])
        bed_len = min(sum_dur, bed["max_seconds"])
        clip = random.choice(music["clips"])
        max_offset = max(0.0, music["clip_seconds"] - bed_len)
        offset = random.uniform(0.0, max_offset) if max_offset > 0 else 0.0
        wav = f"{p['music_dir']}/{bed['name']}.wav"
        fade_out_start = max(0.0, bed_len - music["fade_out"])
        af = (f"volume={music['gain']},"
              f"afade=t=in:st=0:d={music['fade_in']},"
              f"afade=t=out:st={fade_out_start}:d={music['fade_out']},"
              f"aresample=22050")
        run(["ffmpeg","-y","-ss", f"{offset:.4f}", "-t", f"{bed_len:.4f}",
             "-i", f"{music['source_dir']}/{clip}",
             "-af", af, "-ac","1", wav])
        if bed["anchor"] == "start":
            ep_start = cum[bed["cues"][0]]
        elif bed["anchor"] == "end":
            ep_start = total_dur - bed_len
        else:
            raise ValueError(bed["anchor"])
        bed_wavs.append(wav)
        beds_info.append({"name": bed["name"], "clip": clip,
                          "offset_s": round(offset,3),
                          "bed_len_s": round(bed_len,3),
                          "ep_start_s": round(ep_start,3),
                          "delay_ms": int(round(ep_start*1000))})

    # Build filter_complex
    streams = []
    for i, b in enumerate(beds_info, start=1):
        streams.append(f"[{i}]adelay={b['delay_ms']}:all=1[m{i}]")
    mix = "[0:a]" + "".join(f"[m{i}]" for i in range(1, len(beds_info)+1))
    mix += f"amix=inputs={len(beds_info)+1}:normalize=0[a]"
    fc = ";".join(streams + [mix])

    inputs = ["-i", p["nosubs"]]
    for w in bed_wavs:
        inputs += ["-i", w]
    run(["ffmpeg","-y", *inputs,
         "-filter_complex", fc,
         "-map","0:v","-c:v","copy",
         "-map","[a]","-c:a","aac","-b:a","128k",
         "-movflags","+faststart", music_nosubs])

    with open(f"{p['music_dir']}/music_report.json","w") as f:
        json.dump({"beds": beds_info, "total_dur": total_dur}, f, indent=2)

    print(f"[stage 5 music] beds={[b['name'] for b in beds_info]}")
    return {"skipped": False, "music_nosubs": music_nosubs, "beds": beds_info}

if __name__ == "__main__":
    main(sys.argv[1])
