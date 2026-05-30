#!/usr/bin/env python3
"""Stage 8: burn manifest.subtitles SRT on the music-mixed nosubs via NVENC.

Usage: python3 stage_8_burn.py <slug>
"""
import sys, os, subprocess, time
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths, load_manifest, ensure_dirs, ASSETS

DEFAULT_STYLE = ("BorderStyle=1,Outline=2,Shadow=1,"
                 "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                 "MarginV=32,Alignment=2")

def run(cmd):
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print("FAIL:", " ".join(cmd[:6])); print(e.stderr[-1500:]); raise

def main(slug):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    src = p["music_nosubs"] if os.path.exists(p["music_nosubs"]) else p["nosubs"]
    srt = p["out_srt"]
    final = p["out_mp4"]

    subs = m.get("subtitles") or {}
    font_name = subs.get("font", "DejaVu Sans")
    fontsize = subs.get("fontsize", 18)
    fontsdir = subs.get("fontsdir", f"{ASSETS}/fonts")
    extra = subs.get("force_style", DEFAULT_STYLE)

    # If manifest's font isn't actually present, fall back to fc-scan'ing the dir
    # for the first non-default family (handles the BetterVCR vs BetterVCR-JP gotcha).
    try:
        check = subprocess.run(["fc-list", "-q", f":family={font_name}"], capture_output=True)
        if check.returncode != 0:
            # Look for any TTF in fontsdir and grab its family name
            import glob
            ttfs = sorted(glob.glob(f"{fontsdir}/*.ttf") + glob.glob(f"{fontsdir}/*.otf"))
            if ttfs:
                r = subprocess.run(["fc-scan","--format","%{family}", ttfs[0]],
                                   capture_output=True, text=True)
                resolved = r.stdout.strip().split(",")[0]
                if resolved:
                    print(f"[stage 8 burn] font '{font_name}' not registered; "
                          f"using fc-scan'd '{resolved}' from {ttfs[0]}")
                    font_name = resolved
    except FileNotFoundError:
        pass  # fc-list/fc-scan not installed — proceed with manifest name

    style = f"FontName={font_name},Fontsize={fontsize},{extra}"
    srt_esc = srt.replace(":","\\:")
    sub_filter = (f"subtitles='{srt_esc}':fontsdir='{fontsdir}':force_style='{style}'")

    start = time.time()
    run(["ffmpeg","-y","-i", src,"-vf", sub_filter,
         "-c:v","h264_nvenc","-preset","p5","-tune","hq","-cq","22",
         "-c:a","copy","-movflags","+faststart", final])
    size_mb = os.path.getsize(final) / (1024*1024)
    print(f"[stage 8 burn] {final} {round(size_mb,1)} MB "
          f"({round(time.time()-start,2)}s)")
    return {"final": final, "size_mb": round(size_mb,2),
            "font_used": font_name,
            "wall_s": round(time.time()-start,2)}

if __name__ == "__main__":
    main(sys.argv[1])
