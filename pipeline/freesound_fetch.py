#!/usr/bin/env python3
"""freesound_fetch.py — CC0 SFX acquisition helper for the MACU pipeline.

Usage:
  freesound_fetch.py <query> <out_basename> [--duration-max N] [--license cc0|all]
                     [--no-normalize] [--dest <dir>]

  query           Freesound text-search query, e.g. "coins drop slot machine"
  out_basename    Output filename (no extension), e.g. "coins_insert"
  --duration-max  Reject results longer than N seconds (default: 4.0)
  --license       "cc0" (default; strict — only Creative Commons 0)
                  or "all" (also accepts CC-BY / CC-Sampling+)
  --no-normalize  Skip the 24kHz mono PCM s16 + −3 dBFS step (keep original)
  --dest          Output dir (default: $MACU_ASSETS/sfx)

Returns 0 on success, 2 if nothing matched the filter, 3 on auth error.
Top match wins (sorted by score). Mark the catalog row in assets/sfx/README.md
with the freesound URL + license + sound id when you accept the file.

Creds: ~/.config/freesound/credentials.env (FREESOUND_API_KEY required;
client id is informational).
"""

import argparse, json, os, pathlib, shutil, subprocess, sys, tempfile, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lib  # env-driven asset/share paths (loads the repo-root .env)

CREDS_PATH = pathlib.Path.home() / ".config/freesound/credentials.env"
DEFAULT_DEST = pathlib.Path(lib.ASSETS) / "sfx"
API = "https://freesound.org/apiv2"

CC0_URIS = {
    "http://creativecommons.org/publicdomain/zero/1.0/",
}
CC_PERMISSIVE_URIS = CC0_URIS | {
    "http://creativecommons.org/licenses/by/4.0/",
    "http://creativecommons.org/licenses/by/3.0/",
    "http://creativecommons.org/licenses/sampling+/1.0/",
}


def load_key() -> str:
    if not CREDS_PATH.exists():
        sys.exit(f"missing creds at {CREDS_PATH}")
    for line in CREDS_PATH.read_text().splitlines():
        if line.startswith("FREESOUND_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("FREESOUND_API_KEY not found in creds file")


def http_get_json(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Token {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 401:
            sys.exit(3)
        return json.loads(r.read().decode("utf-8"))


def http_download(url: str, key: str, dest: pathlib.Path):
    req = urllib.request.Request(url, headers={"Authorization": f"Token {key}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def normalize(src: pathlib.Path, dst: pathlib.Path):
    """24 kHz mono PCM s16, peak-normalized to −3 dBFS — matches the kit standard."""
    # First pass: detect peak
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(src),
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    peak_db = 0.0
    for line in out.stderr.splitlines():
        if "max_volume" in line:
            peak_db = float(line.split()[4])
            break
    boost = -3.0 - peak_db
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
         "-af", f"volume={boost:.2f}dB", "-ac", "1", "-ar", "24000",
         "-c:a", "pcm_s16le", str(dst)],
        check=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("out_basename")
    ap.add_argument("--duration-max", type=float, default=4.0)
    ap.add_argument("--license", choices=["cc0", "all"], default="cc0")
    ap.add_argument("--no-normalize", action="store_true")
    ap.add_argument("--dest", default=str(DEFAULT_DEST))
    args = ap.parse_args()

    key = load_key()
    dest_dir = pathlib.Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / f"{args.out_basename}.wav"

    if out_path.exists():
        print(f"already exists: {out_path}")
        return 0

    # search/text returns matching sounds; we ask for fields we need to filter
    fields = "id,name,duration,license,previews,download,url"
    q = urllib.parse.urlencode({"query": args.query, "fields": fields, "page_size": 30})
    res = http_get_json(f"{API}/search/text/?{q}", key)
    candidates = res.get("results", [])
    allow = CC0_URIS if args.license == "cc0" else CC_PERMISSIVE_URIS
    filtered = [r for r in candidates
                if r["license"] in allow
                and r["duration"] <= args.duration_max]
    if not filtered:
        print(f"no CC0 match (of {len(candidates)} hits) under {args.duration_max}s for: {args.query}")
        return 2

    pick = filtered[0]
    print(f"picked sound {pick['id']}: {pick['name']} ({pick['duration']:.2f}s, {pick['license'].rsplit('/',2)[-2] or 'cc0'})")
    print(f"  freesound: {pick['url']}")

    # Anonymous API key access can fetch the high-quality preview MP3 directly.
    # Full-quality original-format download requires OAuth2 token, not API key.
    preview = pick["previews"]["preview-hq-mp3"]
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = pathlib.Path(tmp.name)
    try:
        http_download(preview, key, tmp_path)
        if args.no_normalize:
            shutil.move(tmp_path, out_path.with_suffix(".mp3"))
            print(f"wrote {out_path.with_suffix('.mp3')} (raw mp3)")
        else:
            normalize(tmp_path, out_path)
            print(f"wrote {out_path}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
