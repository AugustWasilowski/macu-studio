#!/usr/bin/env python3
"""Stage 5: mix manifest.music beds + manifest.sfx one-shots into the nosubs
audio.

Both music beds (intro/outro/cue-anchored, optionally looped) and sfx clips
(short cue-pinned one-shots from assets/sfx/) feed the same amix filter graph.
SFX is independent of music.enabled — set music.enabled=false but keep sfx[] to
get an episode with no music bed and still get the cricket chirps.

Idempotent: if there's no music AND no sfx, copies nosubs over to music_nosubs
unchanged.

Usage: python3 stage_5_music.py <slug>
"""
import sys, os, json, random, subprocess, shutil
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths, load_manifest, ensure_dirs, probe_dur, ASSETS

SFX_DIR = f"{ASSETS}/sfx"


def run(cmd, timeout=900):
    # Per-call cap so a deadlocked ffmpeg mix fails the stage instead of hanging the lock.
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        print("FAIL:", " ".join(cmd[:6])); print(e.stderr[-1500:]); raise
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT after {timeout}s:", " ".join(cmd[:6])); raise


def _build_music_bed(bed, music, cum, cue_dur, total_dur, music_dir):
    """Render a single music bed wav. Returns (wav_path, ep_start_s, info)."""
    sum_dur = sum(cue_dur[c] for c in bed["cues"])
    bed_len = min(sum_dur, bed["max_seconds"])
    clip = random.choice(music["clips"])
    clip_seconds = music["clip_seconds"]
    loop = bool(bed.get("loop")) and clip_seconds < bed_len
    if loop:
        # Offset is seek-into-source; clamp inside one clip period.
        offset = random.uniform(0.0, max(0.0, clip_seconds - 0.5))
    else:
        max_offset = max(0.0, clip_seconds - bed_len)
        offset = random.uniform(0.0, max_offset) if max_offset > 0 else 0.0
    gain = bed.get("gain", music["gain"])
    fade_in = bed.get("fade_in", music["fade_in"])
    fade_out = bed.get("fade_out", music["fade_out"])
    fade_out_start = max(0.0, bed_len - fade_out)
    af = (f"volume={gain},"
          f"afade=t=in:st=0:d={fade_in},"
          f"afade=t=out:st={fade_out_start}:d={fade_out},"
          f"aresample=22050")
    wav = f"{music_dir}/{bed['name']}.wav"
    ff = ["ffmpeg", "-y", "-ss", f"{offset:.4f}"]
    if loop:
        ff += ["-stream_loop", "-1"]
    ff += ["-i", f"{music['source_dir']}/{clip}",
           "-t", f"{bed_len:.4f}",
           "-af", af, "-ac", "1", wav]
    run(ff)
    if bed["anchor"] == "start":
        ep_start = cum[bed["cues"][0]]
    elif bed["anchor"] == "end":
        ep_start = total_dur - bed_len
    elif bed["anchor"] == "cues":
        ep_start = cum[bed["cues"][0]]
    else:
        raise ValueError(bed["anchor"])
    info = {"name": bed["name"], "clip": clip,
            "offset_s": round(offset, 3),
            "bed_len_s": round(bed_len, 3),
            "ep_start_s": round(ep_start, 3),
            "delay_ms": int(round(ep_start * 1000)),
            "looped": loop,
            "gain": gain}
    return wav, ep_start, info


def _build_sfx(sfx, cum, cue_dur, music_dir):
    """Render a single sfx wav with gain + optional fades + delay nudge.
    Returns (wav_path, ep_start_s, info) or (None, None, info) on missing source."""
    src = os.path.join(SFX_DIR, sfx["file"])
    if not os.path.exists(src):
        info = {"file": sfx["file"], "cue": sfx.get("cue"),
                "skipped": True, "reason": "source not found"}
        print(f"[stage 5 sfx] WARN source missing: {src} — skipped")
        return None, None, info
    cue = sfx["cue"]
    if cue not in cum:
        info = {"file": sfx["file"], "cue": cue,
                "skipped": True, "reason": f"cue {cue} not in manifest"}
        print(f"[stage 5 sfx] WARN cue {cue} not found — {sfx['file']} skipped")
        return None, None, info
    src_dur = probe_dur(src)
    at = sfx.get("at", "start")
    if at == "start":
        ep_start = cum[cue]
    elif at == "end":
        ep_start = cum[cue] + cue_dur[cue] - src_dur
    else:
        raise ValueError(f"sfx.at must be 'start' or 'end', got {at!r}")
    # Optional signed-seconds delay nudge.
    ep_start += float(sfx.get("delay", 0.0))
    # Clamp to >=0 — adelay can't go negative.
    if ep_start < 0:
        print(f"[stage 5 sfx] WARN {sfx['file']} delay pushed before t=0; "
              f"clamping (was {ep_start:.3f}s)")
        ep_start = 0.0
    gain = float(sfx.get("gain", 0.4))
    fade_in = float(sfx.get("fade_in", 0.0))
    fade_out = float(sfx.get("fade_out", 0.0))
    af_parts = [f"volume={gain}"]
    if fade_in > 0:
        af_parts.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        fade_out_start = max(0.0, src_dur - fade_out)
        af_parts.append(f"afade=t=out:st={fade_out_start}:d={fade_out}")
    af_parts.append("aresample=22050")
    af = ",".join(af_parts)
    name = os.path.splitext(sfx["file"])[0]
    wav = f"{music_dir}/sfx_{name}_{cue}_{at}.wav"
    run(["ffmpeg", "-y", "-i", src, "-af", af, "-ac", "1", wav])
    info = {"file": sfx["file"], "cue": cue, "at": at,
            "src_dur_s": round(src_dur, 3),
            "ep_start_s": round(ep_start, 3),
            "delay_ms": int(round(ep_start * 1000)),
            "gain": gain, "fade_in": fade_in, "fade_out": fade_out,
            "delay": float(sfx.get("delay", 0.0)),
            "skipped": False}
    return wav, ep_start, info


def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    music = m.get("music") or {}
    # SFX can be a bare list of {file,cue,at,gain,...} OR a dict with metadata:
    # {enabled, source_dir, note, wishlist, cues:[...]}. Both forms supported.
    sfx_raw = m.get("sfx") or []
    if isinstance(sfx_raw, dict):
        if sfx_raw.get("enabled") is False:
            sfx_entries = []
        else:
            sfx_entries = sfx_raw.get("cues") or []
    else:
        sfx_entries = sfx_raw
    music_nosubs = p["music_nosubs"]

    music_enabled = bool(music.get("enabled"))
    if not music_enabled and not sfx_entries:
        print("[stage 5 music] no music + no sfx, passing through")
        shutil.copy2(p["nosubs"], music_nosubs)
        return {"skipped": True, "music_nosubs": music_nosubs}

    # Cue durations from stage 4
    cdurs_path = f"{p['work']}/cue_durs.json"
    if os.path.exists(cdurs_path):
        with open(cdurs_path) as f:
            cue_dur = json.load(f)
    else:
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

    # Collect overlay wavs (music beds first, then sfx). Each entry =
    # (wav_path, delay_ms). The filter graph uses the same adelay→amix pattern
    # for both — sfx is just "another stream to overlay at this offset."
    overlays = []     # [(wav_path, delay_ms)]
    beds_info = []
    sfx_info = []

    if music_enabled:
        for bed in music["beds"]:
            wav, ep_start, info = _build_music_bed(
                bed, music, cum, cue_dur, total_dur, p["music_dir"])
            overlays.append((wav, int(round(ep_start * 1000))))
            beds_info.append(info)

    for sfx in sfx_entries:
        wav, ep_start, info = _build_sfx(sfx, cum, cue_dur, p["music_dir"])
        sfx_info.append(info)
        if wav is not None:
            overlays.append((wav, int(round(ep_start * 1000))))

    if not overlays:
        # All sfx were missing/skipped and no music — passthrough.
        print("[stage 5 music] all overlays skipped, passing through")
        shutil.copy2(p["nosubs"], music_nosubs)
        return {"skipped": True, "music_nosubs": music_nosubs,
                "beds": beds_info, "sfx": sfx_info}

    # Build filter_complex: [0:a] passthrough + each overlay adelayed → amix
    streams = []
    for i, (_, delay_ms) in enumerate(overlays, start=1):
        streams.append(f"[{i}]adelay={delay_ms}:all=1[m{i}]")
    mix = "[0:a]" + "".join(f"[m{i}]" for i in range(1, len(overlays) + 1))
    mix += f"amix=inputs={len(overlays) + 1}:normalize=0[a]"
    fc = ";".join(streams + [mix])

    inputs = ["-i", p["nosubs"]]
    for wav, _ in overlays:
        inputs += ["-i", wav]
    run(["ffmpeg", "-y", *inputs,
         "-filter_complex", fc,
         "-map", "0:v", "-c:v", "copy",
         "-map", "[a]", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", music_nosubs])

    report = {"beds": beds_info, "sfx": sfx_info, "total_dur": total_dur}
    with open(f"{p['music_dir']}/music_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"[stage 5 music] beds={[b['name'] for b in beds_info]} "
          f"sfx={[s['file'] for s in sfx_info if not s.get('skipped')]}")
    return {"skipped": False, "music_nosubs": music_nosubs,
            "beds": beds_info, "sfx": sfx_info}


if __name__ == "__main__":
    main(sys.argv[1])
