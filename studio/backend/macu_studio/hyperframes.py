"""HyperFrames composition runner — scaffolds + renders title cards on demand.

Per-key dir: episodes/<slug>/hyperframes/<key>/
  index.html              ← templatized from assets/hyperframes/templates/<composition>/
  hyperframes.json        ← workspace config (auto-created)
  out/<key>.mp4           ← render target

After a successful render, out/<key>.mp4 is copied to episodes/<slug>/titles/<key>.mp4
and mtime is bumped past the manifest's so the asset shows as 'rendered'.

All renders are queued onto a single asyncio.Queue worker (one render at a time)
and surface progress through the same SSE channel as the pipeline runs. Each render
gets its own job_id ('hf-' prefix) so the studio frontend can tail it just like
macu-render jobs.
"""
from __future__ import annotations
import asyncio, json, os, shutil, subprocess, time, uuid
from pathlib import Path
from typing import AsyncIterator

from .config import SHARES
from .episodes import episode_dir
from . import manifest as manifest_mod
from . import versions as versions_mod


TEMPLATES = SHARES / "assets" / "hyperframes" / "templates"
WORKSPACE = SHARES / "hyperframes"

# Default composition fallback when manifest gives no fields hints
DEFAULT_FIELDS = {
    "kicker": "TONIGHT'S BULLETIN",
    "title_line_1": "THE MACU",
    "title_line_2": "REPORT",
    "sub": "FROM THE LAST TRANSMITTER.",
    "idtag": "MACU",
}


# ---- job state -----------------------------------------------------------

class Job:
    def __init__(self, job_id: str, slug: str, key: str,
                 kind: str = "title", composition: str | None = None,
                 fields: dict | None = None):
        self.id = job_id
        self.slug = slug
        self.key = key
        self.kind = kind           # title | thumb
        self.composition = composition
        self.fields = fields or {}
        self.state = "queued"       # queued | running | done | error
        self.events: list[dict] = []
        self.event_cond = asyncio.Condition()
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None

    async def emit(self, kind: str, **payload):
        ev = {"ts": time.time(), "kind": kind, **payload}
        async with self.event_cond:
            self.events.append(ev)
            self.event_cond.notify_all()


JOBS: dict[str, Job] = {}
QUEUE: asyncio.Queue[str] | None = None
_worker_started = False


def _ensure_worker(loop: asyncio.AbstractEventLoop) -> None:
    global QUEUE, _worker_started
    if QUEUE is None:
        QUEUE = asyncio.Queue()
    if not _worker_started:
        loop.create_task(_worker())
        _worker_started = True


async def _worker() -> None:
    assert QUEUE is not None
    while True:
        job_id = await QUEUE.get()
        job = JOBS.get(job_id)
        if not job:
            continue
        if job.kind == "thumb":
            await _run_thumb(job)
        else:
            await _run(job)


# ---- templating ----------------------------------------------------------

def _apply_fields(html: str, fields: dict) -> str:
    """Substitute ‹KEY› placeholders. Keys are uppercased + underscore-joined.
    Anything unset is left as the original placeholder, which prints visibly so
    the operator notices missing data."""
    def upper_key(k: str) -> str:
        return k.upper().replace(" ", "_")
    merged = {**DEFAULT_FIELDS, **fields}
    for k, v in merged.items():
        token = f"‹{upper_key(k)}›"
        html = html.replace(token, str(v))
    return html


def _scaffold(slug: str, key: str, composition: str, fields: dict) -> Path:
    """Create episodes/<slug>/hyperframes/<key>/ with templatized index.html
    + minimal hyperframes.json if not present. Returns the project dir."""
    project_dir = episode_dir(slug) / "hyperframes" / key
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "out").mkdir(exist_ok=True)

    template_dir = TEMPLATES / composition
    if not (template_dir / "index.html").exists():
        raise FileNotFoundError(f"template not found: {template_dir}")

    index = project_dir / "index.html"
    if not index.exists():
        raw = (template_dir / "index.html").read_text()
        index.write_text(_apply_fields(raw, fields))

    hf_json = project_dir / "hyperframes.json"
    if not hf_json.exists():
        hf_json.write_text(json.dumps({
            "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
            "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
            "paths": {"blocks": ".", "components": ".", "assets": "."},
        }, indent=2) + "\n")

    return project_dir


# ---- render --------------------------------------------------------------

NPX = "/home/mayorawesome/.nvm/versions/node/v22.22.3/bin/npx"
NODE_BIN = "/home/mayorawesome/.nvm/versions/node/v22.22.3/bin"


async def _run(job: Job) -> None:
    job.state = "running"
    job.started_at = time.time()
    await job.emit("job.started", slug=job.slug, key=job.key)
    try:
        m = manifest_mod.load(job.slug)
        ta = (m.get("title_assets") or {}).get(job.key)
        if not isinstance(ta, dict):
            raise RuntimeError(
                f"title_assets[{job.key!r}] is not the object form; "
                f"set it to {{ 'source':'hyperframes', 'composition':'intro' }} "
                f"to enable regen.")
        if ta.get("source") != "hyperframes":
            raise RuntimeError(
                f"title_assets[{job.key!r}].source != 'hyperframes'; "
                f"got {ta.get('source')!r}")
        composition = ta.get("composition") or job.key
        fields = ta.get("fields") or {}
        render_args = ta.get("render_args") or {}
        fps = str(render_args.get("fps", 8))
        quality = str(render_args.get("quality", "high"))

        project_dir = _scaffold(job.slug, job.key, composition, fields)
        out_mp4 = project_dir / "out" / f"{job.key}.mp4"
        await job.emit("stage.started", n=1, name="render",
                        project=str(project_dir), composition=composition)

        # Shell out to npx hyperframes render. PATH must include node 22.
        env = os.environ.copy()
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"
        env["NPM_CONFIG_PREFIX"] = ""

        proc = await asyncio.create_subprocess_exec(
            NPX, "--userconfig", "/dev/null", "hyperframes", "render",
            "--output", f"out/{job.key}.mp4",
            "--fps", fps,
            "--quality", quality,
            cwd=str(project_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout = []
        assert proc.stdout
        async for line in proc.stdout:
            decoded = line.decode("utf-8", errors="replace").rstrip()
            stdout.append(decoded)
            await job.emit("log", line=decoded)
        rc = await proc.wait()
        log = "\n".join(stdout[-80:])

        if rc != 0:
            await job.emit("stage.error", n=1, name="render", error=f"npx hyperframes render exit {rc}", log=log)
            await job.emit("job.error", error=f"render rc={rc}")
            job.state = "error"
            return

        if not out_mp4.exists():
            await job.emit("stage.error", n=1, name="render", error="render reported success but mp4 not found", log=log)
            await job.emit("job.error", error="missing mp4")
            job.state = "error"
            return

        # Copy into episodes/<slug>/titles/<key>.mp4 + bump mtime past manifest
        titles_dir = episode_dir(job.slug) / "titles"
        titles_dir.mkdir(exist_ok=True)
        final_path = titles_dir / f"{job.key}.mp4"
        shutil.copyfile(out_mp4, final_path)
        # mtime > manifest mtime so derive_titles flags as 'rendered' not 'stale'
        manifest_mtime = manifest_mod.manifest_path(job.slug).stat().st_mtime
        new_mtime = max(manifest_mtime + 1, time.time())
        os.utime(final_path, (new_mtime, new_mtime))

        await job.emit("stage.done", n=1, name="render", wall_s=round(time.time() - job.started_at, 2),
                        result={"mp4_path": str(final_path), "bytes": final_path.stat().st_size})
        await job.emit("job.done", final=str(final_path), bytes=final_path.stat().st_size,
                        wall_s=round(time.time() - job.started_at, 2))
        job.state = "done"
    except Exception as e:
        await job.emit("job.error", error=str(e))
        job.state = "error"
    finally:
        job.finished_at = time.time()


async def _run_thumb(job: Job) -> None:
    """Render a YouTube thumbnail into final/<slug>_thumb.png.

    The previous thumb has already been archived by submit_thumb() before the
    job was queued. Scaffolds the composition under hyperframes/_ythumb/, renders
    it, and produces a PNG at the canonical thumb path. If hyperframes emits an
    mp4, a single frame is extracted to PNG via ffmpeg."""
    job.state = "running"
    job.started_at = time.time()
    await job.emit("job.started", slug=job.slug, key=job.key)
    try:
        composition = job.composition or "youtube_thumb"
        fields = job.fields or {}

        # _ythumb is the scaffold key; reuses the per-key dir machinery.
        project_dir = _scaffold(job.slug, "_ythumb", composition, fields)
        out_mp4 = project_dir / "out" / "_ythumb.mp4"
        out_png = project_dir / "out" / "_ythumb.png"
        # Clear any stale renders so we don't promote an old frame.
        for stale in (out_mp4, out_png):
            if stale.exists():
                stale.unlink()

        await job.emit("stage.started", n=1, name="render",
                        project=str(project_dir), composition=composition)

        env = os.environ.copy()
        env["PATH"] = f"{NODE_BIN}:{env.get('PATH', '')}"
        env["NPM_CONFIG_PREFIX"] = ""

        proc = await asyncio.create_subprocess_exec(
            NPX, "--userconfig", "/dev/null", "hyperframes", "render",
            "--output", "out/_ythumb.mp4",
            "--fps", "8",
            "--quality", "high",
            cwd=str(project_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout = []
        assert proc.stdout
        async for line in proc.stdout:
            decoded = line.decode("utf-8", errors="replace").rstrip()
            stdout.append(decoded)
            await job.emit("log", line=decoded)
        rc = await proc.wait()
        log = "\n".join(stdout[-80:])

        if rc != 0:
            await job.emit("stage.error", n=1, name="render", error=f"npx hyperframes render exit {rc}", log=log)
            await job.emit("job.error", error=f"render rc={rc}")
            job.state = "error"
            return

        # Land a PNG. hyperframes may have produced a png directly or an mp4.
        final_dir = episode_dir(job.slug) / "final"
        final_dir.mkdir(exist_ok=True)
        final_png = final_dir / f"{job.slug}_thumb.png"

        if out_png.exists():
            shutil.copyfile(out_png, final_png)
        elif out_mp4.exists():
            await job.emit("log", line="extracting single frame from mp4 → png")
            ff = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(out_mp4), "-frames:v", "1", str(final_png),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert ff.stdout
            async for line in ff.stdout:
                await job.emit("log", line=line.decode("utf-8", errors="replace").rstrip())
            ffrc = await ff.wait()
            if ffrc != 0 or not final_png.exists():
                await job.emit("stage.error", n=1, name="render", error=f"ffmpeg frame extract exit {ffrc}")
                await job.emit("job.error", error="thumb png extract failed")
                job.state = "error"
                return
        else:
            await job.emit("stage.error", n=1, name="render", error="render reported success but no png/mp4 found", log=log)
            await job.emit("job.error", error="missing thumb output")
            job.state = "error"
            return

        await job.emit("stage.done", n=1, name="render", wall_s=round(time.time() - job.started_at, 2),
                        result={"png_path": str(final_png), "bytes": final_png.stat().st_size})
        await job.emit("job.done", final=str(final_png), bytes=final_png.stat().st_size,
                        wall_s=round(time.time() - job.started_at, 2))
        job.state = "done"
    except Exception as e:
        await job.emit("job.error", error=str(e))
        job.state = "error"
    finally:
        job.finished_at = time.time()


# ---- public API ----------------------------------------------------------

def list_templates() -> list[str]:
    """Names of subdirs under assets/hyperframes/templates/ (empty if missing)."""
    if not TEMPLATES.exists():
        return []
    return sorted(p.name for p in TEMPLATES.iterdir() if p.is_dir())


async def submit(slug: str, key: str) -> str:
    """Queue a render. Returns the job_id."""
    loop = asyncio.get_event_loop()
    _ensure_worker(loop)
    assert QUEUE is not None
    job_id = "hf-" + uuid.uuid4().hex[:10]
    JOBS[job_id] = Job(job_id, slug, key)
    QUEUE.put_nowait(job_id)
    return job_id


async def submit_new(slug: str, key: str, composition: str, fields: dict) -> str:
    """Create a new title_assets[key] entry from a composition + fields, then
    queue its render. Returns the job_id."""
    m = manifest_mod.load(slug)
    ta = m.setdefault("title_assets", {})
    ta[key] = {"source": "hyperframes", "composition": composition, "fields": fields or {}}
    manifest_mod.save(slug, m)
    return await submit(slug, key)


async def submit_thumb(slug: str, fields: dict, composition: str = "youtube_thumb") -> str:
    """Queue a YouTube thumbnail render. Archives the current thumb first, then
    scaffolds + renders the composition into final/<slug>_thumb.png. Returns the
    job_id. Raises FileNotFoundError if the template is missing."""
    template_dir = TEMPLATES / composition
    if not (template_dir / "index.html").exists():
        raise FileNotFoundError(
            f"youtube thumbnail template not found: {template_dir}/index.html")
    # Archive the outgoing thumb into version history before overwriting.
    versions_mod.archive_current(slug, "ythumb", slug)
    loop = asyncio.get_event_loop()
    _ensure_worker(loop)
    assert QUEUE is not None
    job_id = "hf-" + uuid.uuid4().hex[:10]
    JOBS[job_id] = Job(job_id, slug, slug, kind="thumb",
                       composition=composition, fields=fields or {})
    QUEUE.put_nowait(job_id)
    return job_id


def status(job_id: str) -> dict | None:
    job = JOBS.get(job_id)
    if not job:
        return None
    return {
        "id": job.id,
        "slug": job.slug,
        "key": job.key,
        "state": job.state,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "event_count": len(job.events),
        "last_events": job.events[-12:],
    }


async def stream(job_id: str, since: int = 0) -> AsyncIterator[bytes]:
    """SSE stream for a job's events."""
    job = JOBS.get(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'job not found'})}\n\n".encode()
        return
    yield f": hyperframes job={job_id} since={since}\n\n".encode()
    sent = since
    while True:
        async with job.event_cond:
            while sent >= len(job.events) and job.state in ("queued", "running"):
                try:
                    await asyncio.wait_for(job.event_cond.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    break
            batch = job.events[sent:]
            sent = len(job.events)
        for ev in batch:
            yield f"data: {json.dumps(ev)}\n\n".encode()
            if ev.get("kind") in ("job.done", "job.error"):
                yield b"event: end\ndata: {}\n\n"
                return
        if not batch:
            yield b": ping\n\n"
            if job.state in ("done", "error"):
                yield b"event: end\ndata: {}\n\n"
                return
