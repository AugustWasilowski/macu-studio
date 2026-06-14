#!/usr/bin/env python3
"""render_watch.py — block until a MACU render reaches a milestone, then exit.

The cron/non-MCP twin of the Studio MCP tool `await_render`. An orchestrating
agent (or a shell script) runs this, and it parks until a render checkpoint
instead of blind-polling every minute and burning the caller's context. Both this
and `await_render` key off the SAME per-stage status the Studio app already
serves at /api/episodes/<slug>/pipeline (stage `status` flips idle -> done/error).

MCP-driven agents should prefer the `await_render` tool; reach for this script for
cron jobs, CI, or a plain shell driver with no MCP client.

Usage:
  render_watch.py --slug ep-021 --job <job_id> [--until final] [--interval 60]
  render_watch.py --slug ep-021 --until masters         # await purely on stage status

  --until   stage number 1-8 or an alias: vo(1) masters(2) rife(3) assemble(4)
            music(5) whisper(6) srt/subs(7) burn/final(8)   [default: final]
  --studio  Studio base URL   [default http://127.0.0.1:8774]
  --render  Render base URL   [default http://127.0.0.1:8773]

Exit codes:
  0  milestone reached (target stage done/error, or the job finished)
  2  services unreachable (10 consecutive failures)
  3  bad arguments

Note: the masters stage reports `idle` until shot 1's file is written even though
ComfyUI is already crunching — so "idle / 0 masters" early in a run is normal, not
a stall.
"""
import argparse
import json
import sys
import time
import urllib.request

STAGES = {"vo": 1, "masters": 2, "rife": 3, "assemble": 4, "music": 5,
          "whisper": 6, "srt": 7, "subs": 7, "burn": 8, "final": 8}
JOB_TERMINAL = {"done", "error", "abandoned", "cancelled", "failed"}


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.load(r), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def main() -> int:
    ap = argparse.ArgumentParser(description="Block until a MACU render milestone.")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--job", default="", help="render job id (optional but recommended)")
    ap.add_argument("--until", default="final")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--studio", default="http://127.0.0.1:8774")
    ap.add_argument("--render", default="http://127.0.0.1:8773")
    a = ap.parse_args()

    try:
        target = STAGES.get(a.until.strip().lower()) or int(a.until)
    except (ValueError, TypeError):
        print(f"bad --until '{a.until}': use 1-8 or {sorted(STAGES)}", file=sys.stderr)
        return 3
    if not 1 <= target <= 8:
        print("--until stage must be 1..8", file=sys.stderr)
        return 3

    interval = max(2, min(a.interval, 300))
    studio = a.studio.rstrip("/")
    render = a.render.rstrip("/")
    errs = 0
    last = None
    while True:
        pipe, e1 = _get(f"{studio}/api/episodes/{a.slug}/pipeline")
        job, e2 = (None, None)
        if a.job:
            job, e2 = _get(f"{render}/status/{a.job}")
        if pipe is None or (a.job and job is None):
            errs += 1
            if errs >= 10:
                print(f"EXIT services unreachable: studio={e1} render={e2}", flush=True)
                return 2
            time.sleep(interval)
            continue
        errs = 0

        rows = pipe.get("stages") if isinstance(pipe, dict) else pipe
        st = next((s for s in (rows or []) if s.get("n") == target), {})
        job_state = None
        if isinstance(job, dict):
            inner = job.get("job") if isinstance(job.get("job"), dict) else job
            job_state = inner.get("state") if isinstance(inner, dict) else None

        line = f"job={job_state} | stage{target}={st.get('status')} ({st.get('note')})"
        if line != last:
            print(time.strftime("%H:%M:%S"), line, flush=True)
            last = line

        if st.get("status") in ("done", "error"):
            print(f"EXIT stage {target} {st.get('status')}", flush=True)
            return 0
        if job_state in JOB_TERMINAL:
            print(f"EXIT job {job_state}", flush=True)
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
