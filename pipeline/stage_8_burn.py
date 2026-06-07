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

def run(cmd, timeout=1800):
    # Per-call cap so a hung NVENC burn fails the stage (releasing the render lock)
    # instead of blocking forever. 30 min is well above any real full-episode burn.
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        print("FAIL:", " ".join(cmd[:6])); print(e.stderr[-1500:]); raise
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT after {timeout}s:", " ".join(cmd[:6])); raise

def main(slug, src=None, srt=None, final=None, font=None):
    ensure_dirs(slug)
    p = episode_paths(slug)
    m = load_manifest(slug)
    if src is None:
        src = p["music_nosubs"] if os.path.exists(p["music_nosubs"]) else p["nosubs"]
    if srt is None:
        srt = p["out_srt"]
    if final is None:
        final = p["out_mp4"]

    subs = m.get("subtitles") or {}
    # `font` override lets the dub path swap in a script-appropriate face (e.g. Noto for
    # CJK/Arabic/Indic) without touching the manifest; English burns are unchanged.
    font_name = font or subs.get("font", "DejaVu Sans")
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

    # Strip any FontName/Fontsize from the manifest's force_style so the
    # resolved values win — libass takes the last occurrence in force_style,
    # and a stale FontName=Better VCR in the manifest would override the
    # fc-scan'd Better VCR-JP, causing a silent default-font fallback.
    extra_parts = [p for p in (s.strip() for s in extra.split(","))
                   if p and not p.lower().startswith(("fontname=", "fontsize="))]
    style = ",".join([f"FontName={font_name}", f"Fontsize={fontsize}", *extra_parts])
    srt_esc = srt.replace(":","\\:")
    sub_filter = (f"subtitles='{srt_esc}':fontsdir='{fontsdir}':force_style='{style}'")

    # Render to a temp file first, then version the previous final (rename it with its
    # render timestamp) and move the new one into place. Doing it in this order means a
    # failed burn never destroys the existing final, and prior renders are kept as
    # final/<slug>.<YYYYmmdd-HHMMSS>.mp4 archives (the live file stays final/<slug>.mp4).
    base, ext = os.path.splitext(final)
    tmp = f"{base}.part{ext}"
    start = time.time()
    run(["ffmpeg","-y","-i", src,"-vf", sub_filter,
         "-c:v","h264_nvenc","-preset","p5","-tune","hq","-cq","22",
         "-c:a","copy","-movflags","+faststart", tmp])
    archived = None
    if os.path.exists(final):
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(os.path.getmtime(final)))
        archive = f"{base}.{stamp}{ext}"
        n = 1
        while os.path.exists(archive):
            archive = f"{base}.{stamp}-{n}{ext}"; n += 1
        os.rename(final, archive)
        archived = os.path.basename(archive)
        print(f"[stage 8 burn] archived previous final -> {archived}")
    os.replace(tmp, final)
    size_mb = os.path.getsize(final) / (1024*1024)
    print(f"[stage 8 burn] {final} {round(size_mb,1)} MB "
          f"({round(time.time()-start,2)}s)")
    return {"final": final, "size_mb": round(size_mb,2),
            "font_used": font_name, "archived": archived,
            "wall_s": round(time.time()-start,2)}

if __name__ == "__main__":
    main(sys.argv[1])
