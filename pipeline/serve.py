#!/usr/bin/env python3
"""macu-render HTTP service.

Drives the 8-stage pipeline (run.py) via HTTP for Leo's macu-report skill (or
any caller). Single-worker queue (GPU is the bottleneck; one render at a time).

Endpoints
---------
POST /render                {"slug":"epN", "from_stage":1, "only":null}
    -> 202 {"job_id":"uuid", "queued":true}    or 400 if manifest missing

GET  /jobs                                    list all known jobs (in-mem + disk)
GET  /status/{job_id}                         current state + last-known events
GET  /events/{job_id}?since=N                 SSE stream of events.jsonl,
                                              one `data: <event-json>` per line,
                                              starting from the Nth event
GET  /health                                  liveness check

Job state directory: /var/lib/macu-render/jobs/<job_id>/
  - events.jsonl    structured events emitted by run.py
  - run.log         combined stdout+stderr of run.py
  - meta.json       job-level metadata

Bind: 127.0.0.1:8773 by default (no auth). Set MACU_RENDER_HOST=0.0.0.0 to reach it
from another device on a trusted LAN.
"""
import os, re, sys, json, uuid, time, threading, queue, subprocess, signal
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PIPELINE = os.path.dirname(os.path.abspath(__file__))


def _jobs_root() -> str:
    """Per-job state dir (events/log/meta). MACU_RENDER_JOBS wins; else prefer the
    system path /var/lib/macu-render/jobs (Max/systemd), falling back to an XDG
    state dir under $HOME when /var/lib isn't writable — e.g. a fresh non-root
    install on WSL, where creating under /var/lib raises PermissionError."""
    env = os.environ.get("MACU_RENDER_JOBS")
    if env:
        return env
    sys_default = "/var/lib/macu-render/jobs"
    try:
        os.makedirs(sys_default, exist_ok=True)
        if os.access(sys_default, os.W_OK):
            return sys_default
    except OSError:
        pass
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "macu-render", "jobs")


JOBS_ROOT = _jobs_root()
# Default episodes dir; a job may override it (multi-show support). Sourced from
# lib (single source of truth, env-driven via MACU_EPISODES). Importing lib also
# loads the repo-root .env.
sys.path.insert(0, PIPELINE)
import lib  # noqa: E402
SHARES_EP = lib.EPISODES_ROOT
RUN_PY = f"{PIPELINE}/run.py"
PORT = 8773
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")

os.makedirs(JOBS_ROOT, exist_ok=True)

# ----- job model -----------------------------------------------------------

class Job:
    def __init__(self, job_id, slug, from_stage=1, only=None, episodes_dir=None,
                 dub_lang=None, dub_engine=None, subs_only=False, comfy_url=None):
        self.id = job_id
        self.slug = slug
        self.from_stage = from_stage
        self.only = only
        self.episodes_dir = episodes_dir   # None → use the server default (MACU)
        self.comfy_url = comfy_url         # None → lib.py's MACU_COMFY_URL default
        self.dub_lang = dub_lang           # set → run.py --dub (localize, not a render)
        self.dub_engine = dub_engine
        self.subs_only = subs_only
        self.state = "queued"       # queued | running | done | error
        self.created_at = time.time()
        self.started_at = None
        self.finished_at = None
        self.proc = None
        self.events_path = f"{JOBS_ROOT}/{job_id}/events.jsonl"
        self.log_path    = f"{JOBS_ROOT}/{job_id}/run.log"
        self.meta_path   = f"{JOBS_ROOT}/{job_id}/meta.json"
        os.makedirs(f"{JOBS_ROOT}/{job_id}", exist_ok=True)
        # Touch the events file so SSE tail can open it immediately
        open(self.events_path, "a").close()
        self._persist()

    def to_dict(self):
        return {
            "id": self.id, "slug": self.slug,
            "from_stage": self.from_stage, "only": self.only,
            "episodes_dir": self.episodes_dir,
            "comfy_url": getattr(self, "comfy_url", None),
            "dub_lang": self.dub_lang, "dub_engine": self.dub_engine,
            "subs_only": self.subs_only,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "events_path": self.events_path,
            "log_path": self.log_path,
        }

    def _persist(self):
        with open(self.meta_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

JOBS = {}        # job_id -> Job
JOBS_LOCK = threading.Lock()
WORK_Q = queue.Queue()

def load_existing_jobs():
    for jid in os.listdir(JOBS_ROOT):
        meta = f"{JOBS_ROOT}/{jid}/meta.json"
        if not os.path.exists(meta):
            continue
        try:
            with open(meta) as f:
                d = json.load(f)
            j = Job.__new__(Job)
            j.id = d["id"]; j.slug = d["slug"]
            j.from_stage = d.get("from_stage", 1); j.only = d.get("only")
            j.episodes_dir = d.get("episodes_dir")
            j.dub_lang = d.get("dub_lang"); j.dub_engine = d.get("dub_engine")
            j.subs_only = d.get("subs_only", False)
            j.state = d.get("state", "unknown")
            j.created_at = d.get("created_at"); j.started_at = d.get("started_at")
            j.finished_at = d.get("finished_at")
            j.events_path = d["events_path"]; j.log_path = d["log_path"]
            j.meta_path = meta; j.proc = None
            # Treat any still-running job as orphaned after a restart
            if j.state in ("queued","running"):
                j.state = "abandoned"
                j._persist()
            JOBS[j.id] = j
        except Exception as e:
            print(f"WARN load job {jid}: {e}", file=sys.stderr)

# ----- worker thread -------------------------------------------------------

def worker():
    while True:
        job_id = WORK_Q.get()
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if not job:
            continue
        job.state = "running"; job.started_at = time.time(); job._persist()
        cmd = [sys.executable, RUN_PY, job.slug,
               "--events-out", job.events_path]
        if getattr(job, "dub_lang", None):
            # Localize job: bypass the 8-stage render, run the dub path instead.
            cmd += ["--dub", job.dub_lang, "--engine", job.dub_engine or "qwen"]
            if getattr(job, "subs_only", False):
                cmd += ["--subs-only"]
        else:
            if job.from_stage and job.from_stage != 1:
                cmd += ["--from", str(job.from_stage)]
            if job.only:
                cmd += ["--only", str(job.only)]
        # Per-job episodes dir (multi-show). The whole stage tree reads
        # MACU_EPISODES via lib.episode_paths, so setting it here points run.py
        # and every child stage at the right show's dir. Unset → server default.
        env = os.environ.copy()
        if getattr(job, "episodes_dir", None):
            env["MACU_EPISODES"] = job.episodes_dir
        # Per-job ComfyUI endpoint (engine routing in Studio). lib.py reads
        # MACU_COMFY_URL, so every stage follows with zero stage changes.
        if getattr(job, "comfy_url", None):
            env["MACU_COMFY_URL"] = job.comfy_url
        try:
            with open(job.log_path, "wb") as log:
                # start_new_session so the whole render tree (run.py + ffmpeg/rife children)
                # is a process group we can kill in one shot via /kill.
                p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True, env=env)
                job.proc = p
                p.wait()
            job.state = "done" if p.returncode == 0 else "error"
        except Exception as e:
            job.state = "error"
            with open(job.events_path, "a") as f:
                f.write(json.dumps({"ts": time.time(), "kind": "job.error",
                                    "error": str(e)}) + "\n")
        finally:
            job.finished_at = time.time(); job._persist()

threading.Thread(target=worker, daemon=True).start()

# ----- http handler --------------------------------------------------------

def _json(handler, code, body):
    payload = json.dumps(body).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(payload)

class Handler(BaseHTTPRequestHandler):
    server_version = "macu-render/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}\n")

    # GET ---------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return _json(self, 200, {"ok": True, "uptime_s": int(time.time()-START)})

        if u.path == "/jobs":
            with JOBS_LOCK:
                items = [j.to_dict() for j in sorted(JOBS.values(), key=lambda j: -j.created_at)]
            return _json(self, 200, {"jobs": items})

        if u.path.startswith("/status/"):
            job_id = u.path.split("/",2)[2]
            with JOBS_LOCK:
                j = JOBS.get(job_id)
            if not j:
                return _json(self, 404, {"error": "job not found"})
            # Tail the last N events for state quick-view
            events = []
            if os.path.exists(j.events_path):
                with open(j.events_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try: events.append(json.loads(line))
                        except json.JSONDecodeError: pass
            return _json(self, 200, {"job": j.to_dict(),
                                      "event_count": len(events),
                                      "last_events": events[-12:]})

        if u.path.startswith("/events/"):
            job_id = u.path.split("/",2)[2]
            with JOBS_LOCK:
                j = JOBS.get(job_id)
            if not j:
                return _json(self, 404, {"error": "job not found"})
            since = int(parse_qs(u.query).get("since", ["0"])[0])
            return self._sse_stream(j, since)

        if u.path == "/" or u.path == "/index":
            return _json(self, 200, {
                "service": "macu-render",
                "endpoints": ["POST /render", "GET /jobs", "GET /status/{id}",
                              "GET /events/{id}?since=N", "GET /health"],
            })

        _json(self, 404, {"error": "not found"})

    # POST --------------------------------------------------------------
    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/kill":
            return self._kill()
        if u.path != "/render":
            return _json(self, 404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length)) if length else {}
        except json.JSONDecodeError:
            return _json(self, 400, {"error": "invalid json"})
        slug = body.get("slug")
        # This endpoint is unauthenticated (LAN-only by design) and both slug and
        # episodes_dir flow into filesystem paths + the child process env. Validate
        # them: slug to a strict pattern, episodes_dir confined under the shares root.
        if not slug or not _SLUG_RE.match(str(slug)):
            return _json(self, 400, {"error": "invalid slug"})
        req_ed = body.get("episodes_dir")
        if req_ed:
            root = os.path.realpath(str(lib.SHARES))
            cand = os.path.realpath(str(req_ed))
            if cand != root and not cand.startswith(root + os.sep):
                return _json(self, 400, {"error": "episodes_dir must be under the shares root"})
            episodes_dir = req_ed
        else:
            episodes_dir = SHARES_EP
        manifest = f"{episodes_dir}/{slug}/manifest.json"
        if not os.path.exists(manifest):
            return _json(self, 400, {"error": f"manifest not found: {manifest}"})
        # Optional dub block → a Localize job (run.py --dub) instead of a render.
        dub = body.get("dub")
        dub_lang = dub_engine = None
        subs_only = False
        if isinstance(dub, dict):
            dub_lang = str(dub.get("lang") or "")
            if not re.match(r"^[a-zA-Z][a-zA-Z-]{1,8}$", dub_lang):
                return _json(self, 400, {"error": "invalid dub.lang"})
            dub_engine = dub.get("engine") or "qwen"
            if dub_engine not in ("qwen", "argos"):
                return _json(self, 400, {"error": "dub.engine must be qwen or argos"})
            subs_only = bool(dub.get("subs_only"))
        # Optional per-job ComfyUI endpoint (Studio engine routing). It lands in a
        # child-process env var, so hold it to a plain http(s) URL shape.
        comfy_url = body.get("comfy_url")
        if comfy_url is not None:
            comfy_url = str(comfy_url).rstrip("/")
            if not re.match(r"^https?://[\w.\-]+(:\d+)?$", comfy_url):
                return _json(self, 400, {"error": "invalid comfy_url"})
        job_id = uuid.uuid4().hex[:12]
        job = Job(job_id, slug,
                  from_stage=int(body.get("from_stage", 1)),
                  only=body.get("only"),
                  episodes_dir=(body.get("episodes_dir") or None),
                  dub_lang=dub_lang, dub_engine=dub_engine, subs_only=subs_only,
                  comfy_url=comfy_url)
        with JOBS_LOCK:
            JOBS[job_id] = job
        WORK_Q.put(job_id)
        return _json(self, 202, {"job_id": job_id, "queued": True,
                                  "events_url": f"/events/{job_id}",
                                  "status_url": f"/status/{job_id}"})

    # KILL --------------------------------------------------------------
    def _kill(self):
        """Emergency stop: SIGTERM (then SIGKILL) every running job's process group so the
        run.py tree + its ffmpeg/rife children all die, and mark the jobs errored so the
        render lock clears."""
        with JOBS_LOCK:
            running = [j for j in JOBS.values() if j.state == "running" and getattr(j, "proc", None)]
        killed = []
        for j in running:
            p = j.proc
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if p.poll() is not None:
                    break
                try:
                    os.killpg(os.getpgid(p.pid), sig)
                except Exception:
                    try: p.send_signal(sig)
                    except Exception: pass
                time.sleep(0.8)
            j.state = "error"
            try: j._persist()
            except Exception: pass
            killed.append(j.id)
        return _json(self, 200, {"killed": killed})

    # SSE ---------------------------------------------------------------
    def _sse_stream(self, job, since):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            # Disable buffering for nginx-likes
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
        except Exception:
            return

        def write(line):
            self.wfile.write(line.encode())
            self.wfile.flush()

        write(f": connected job={job.id} since={since}\n\n")
        sent = 0
        idle_pings = 0
        with open(job.events_path) as f:
            # Skip already-sent events
            for _ in range(since):
                if not f.readline():
                    break
                sent += 1
            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line:
                        try:
                            write(f"data: {line}\n\n")
                            sent += 1
                            try:
                                evt = json.loads(line)
                                if evt.get("kind") in ("job.done", "job.error"):
                                    write("event: end\ndata: {}\n\n")
                                    return
                            except json.JSONDecodeError:
                                pass
                        except (BrokenPipeError, ConnectionResetError):
                            return
                    idle_pings = 0
                else:
                    # No new data; reflect job state
                    if job.state in ("done", "error", "abandoned"):
                        try:
                            write("event: end\ndata: {}\n\n")
                        except Exception:
                            pass
                        return
                    idle_pings += 1
                    if idle_pings >= 30:  # 15s of nothing
                        try:
                            write(": ping\n\n")
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        idle_pings = 0
                    time.sleep(0.5)

# ----- main ----------------------------------------------------------------

START = time.time()

def main():
    load_existing_jobs()
    # Loopback by default (no auth on this service). Studio reaches it on localhost.
    # Set MACU_RENDER_HOST=0.0.0.0 only to drive renders from another device on a trusted LAN.
    host = os.environ.get("MACU_RENDER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host == "0.0.0.0":
        print("WARNING: MACU_RENDER_HOST=0.0.0.0 — macu-render is reachable by anyone on your "
              "network, with NO auth. Use 127.0.0.1 unless you mean to share it.", flush=True)
    server = ThreadingHTTPServer((host, PORT), Handler)
    print(f"macu-render serving on {host}:{PORT}  jobs={len(JOBS)}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
