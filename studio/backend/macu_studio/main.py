"""MACU Studio FastAPI app.

Endpoints under /api ; SPA mounted at /. Runs as `uvicorn macu_studio.main:app`.
"""
from __future__ import annotations
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import episodes as ep_mod
from . import manifest as manifest_mod
from . import gen_manifest as genman_mod
from . import script as script_mod
from . import scriptdiff as scriptdiff_mod
from . import srt as srt_mod
from . import pipeline as pipeline_mod
from . import media as media_mod
from . import regen as regen_mod
from . import sfx as sfx_mod
from . import agen as agen_mod
from . import assets as assets_mod
from . import sysstat as sysstat_mod
from . import hyperframes as hf_mod
from . import events as events_mod
from . import chat as chat_mod
from . import shotgen as shotgen_mod
from . import sfxgen as sfxgen_mod
from . import cardgen as cardgen_mod
from . import compgen as compgen_mod
from . import corpus as corpus_mod
from . import emergency as emergency_mod
from . import activity as activity_mod
from . import engines as engines_mod
from . import routes_assets, routes_graphics, routes_writers, routes_youtube, routes_docs, routes_gitsync, routes_shows, routes_voices, routes_version, routes_diag, routes_localize, routes_publish, routes_higgsfield, routes_engines, routes_characters, routes_sync
from . import mcp_server
from . import version as version_mod
from . import shows as shows_mod
from .config import EPISODES, FRONTEND_DIST, CORS_DEV_ORIGINS, CHAT_WEBHOOK_TOKEN, SHARES


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[macu-studio] EPISODES={EPISODES} FRONTEND_DIST={FRONTEND_DIST}")
    # Materialize the editable Ollama prompt files into docs/ so they appear on
    # the Docs page even before the first generation. No-op once they exist.
    try:
        shotgen_mod.ensure_prompt_seeded()
        sfxgen_mod.ensure_prompt_seeded()
        cardgen_mod.ensure_prompt_seeded()
        compgen_mod.ensure_prompt_seeded()
    except Exception as e:
        print(f"[macu-studio] prompt seed skipped: {e}")
    # Best-effort startup check for a newer build, in the background so a slow or
    # offline `git fetch` never delays boot. Populates the UI's "update available"
    # badge without the user having to click Check.
    try:
        import threading
        from . import version as version_mod
        threading.Thread(target=lambda: version_mod.check(do_fetch=True),
                         daemon=True, name="macu-version-check").start()
    except Exception as e:
        print(f"[macu-studio] startup version check skipped: {e}")
    # The MCP endpoint's session manager must run for the app's lifetime —
    # without it every POST /mcp 500s with "task group not initialized".
    async with mcp_server.session_manager().run():
        yield


# App version tracks the git release tag (v0.2.2 → "0.2.2"); see version.release().
app = FastAPI(title="MACU Studio",
              version=(version_mod.release() or "v0.0.0-dev").lstrip("v"),
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_DEV_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "release": version_mod.release(),
            "episodes_dir": str(EPISODES), "render_url": pipeline_mod.RENDER_URL}


@app.get("/api/sysstat")
async def get_sysstat():
    """CPU % + GPU % + GPU RAM for the topbar readout (poll ~every 2s)."""
    return await sysstat_mod.snapshot()


_STAGE_LABEL = {
    "vo": "Rendering audio", "masters": "Rendering video", "rife": "Rendering video",
    "assemble": "Assembling video", "graphics": "Rendering graphics", "music": "Rendering music",
    "whisper": "Transcribing", "srt": "Subtitles", "burn": "Burning subtitles",
}


async def _render_label(job: dict) -> str:
    """Friendly label for a running render job — its current stage if we can read it."""
    try:
        st = await pipeline_mod.status(job["id"])
        cur = None
        for e in (st.get("last_events") or []):
            if e.get("kind") == "stage.started":
                cur = e.get("name")
            elif e.get("kind") == "stage.done" and e.get("name") == cur:
                cur = None
        if cur:
            return _STAGE_LABEL.get(cur, f"Rendering ({cur})")
    except Exception:
        pass
    return f"Rendering {job.get('slug', '')}"


@app.get("/api/activity")
async def get_activity():
    """What the box is processing right now, for the topbar job indicator. Aggregates
    the render server's jobs, HyperFrames jobs, and the synchronous-job activity slot.
    Poll ~every 2s. Returns {state: idle|running|error, label}."""
    # 1) render-server job (the heavy, multi-minute work)
    try:
        jobs = (await pipeline_mod.jobs_list()).get("jobs", [])
    except Exception:
        jobs = []
    running = next((j for j in jobs if j.get("state") == "running"), None)
    if running:
        return {"state": "running", "label": await _render_label(running)}
    recent = max((j for j in jobs if j.get("finished_at")), key=lambda j: j["finished_at"], default=None)
    if recent and recent.get("state") == "error" and (time.time() - recent["finished_at"]) < 8:
        return {"state": "error", "label": f"Render failed: {recent.get('slug', '')}"}
    # 2) HyperFrames (title/graphics) jobs
    for job in list(hf_mod.JOBS.values()):
        if getattr(job, "state", None) == "running":
            return {"state": "running", "label": f"Rendering graphics: {job.key}"}
    # 3) synchronous studio jobs (agen sfx/music, shot-gen)
    s = activity_mod.get()
    if s["state"] != "idle":
        return s
    return {"state": "idle", "label": ""}


# ---------- Episodes ----------

@app.get("/api/episodes")
def list_episodes(show: str | None = None):
    """Episodes for one show (default: the-macu-report). Pass ?show=<id> to scope."""
    return {"episodes": [e.__dict__ for e in ep_mod.list_episodes(show)]}


@app.get("/api/episodes/{slug}/manifest")
def get_manifest(slug: str):
    try:
        return manifest_mod.load(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.put("/api/episodes/{slug}/manifest")
async def put_manifest(slug: str, body: dict = Body(...)):
    try:
        return manifest_mod.save(slug, body)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/script")
def get_script(slug: str):
    try:
        return script_mod.read(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.put("/api/episodes/{slug}/script")
async def put_script(slug: str, request: Request):
    body = (await request.body()).decode("utf-8")
    try:
        return script_mod.write(slug, body)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/script/versions")
def get_script_versions(slug: str):
    """Version history of script.md (git sync commits + live working copy)."""
    return {"versions": scriptdiff_mod.versions(slug)}


@app.get("/api/episodes/{slug}/script/diff")
def get_script_diff(slug: str, base: str, target: str):
    """Line-level diff between two script versions (base=older, target=newer)."""
    return scriptdiff_mod.diff(slug, base, target)


@app.post("/api/episodes/{slug}/manifest/from-script")
async def post_manifest_from_script(slug: str, body: dict = Body(default={})):
    """Regenerate manifest.cues from script.md, merging into the existing manifest.

    Default is a dry run returning {summary, cues}. With {"apply": true} it writes
    the merged manifest (after a timestamped manifest.json.bak)."""
    try:
        if bool(body.get("apply")):
            return genman_mod.apply(slug)
        prev = genman_mod.preview(slug)
        return {"summary": prev["summary"], "cues": prev["cues"]}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/cues")
def get_cues(slug: str):
    try:
        return {"cues": manifest_mod.derive_cues(slug)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/shots")
def get_shots(slug: str):
    try:
        return {"shots": manifest_mod.derive_shots(slug)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/titles")
def get_titles(slug: str):
    try:
        return {"titles": manifest_mod.derive_titles(slug)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/episodes/{slug}/pipeline")
def get_pipeline_status(slug: str):
    return {"stages": manifest_mod.episode_pipeline_status(slug)}


@app.get("/api/episodes/{slug}/pipeline/active")
async def get_pipeline_active(slug: str):
    """The currently-running render job id for this episode (or null) — lets the
    Assembly tab re-attach to an in-progress render after a reload / from another
    tab and rebuild its log tail by streaming the job's events."""
    try:
        jobs = (await pipeline_mod.jobs_list()).get("jobs", [])
    except Exception:
        jobs = []
    running = next((j for j in jobs if j.get("slug") == slug and j.get("state") == "running"), None)
    return {"job_id": running["id"] if running else None}


@app.get("/api/episodes/{slug}/final")
def get_final_info(slug: str):
    return manifest_mod.final_info(slug)


# Masters video backend selector — `comfyui.workflow` chooses how character shots
# render: zeroscope text-to-video (default) or WAN image-to-video (seeded from
# stills/<key>.png; b-roll stays t2v). See stage_2_masters._masters_backend.
_MASTERS_BACKENDS = {"zeroscope": "will-smith-modelscope-t2v", "wan_i2v": "wan21_i2v"}


@app.post("/api/episodes/{slug}/masters-backend")
def post_masters_backend(slug: str, body: dict = Body(...)):
    backend = (body.get("backend") or "").strip()
    if backend not in _MASTERS_BACKENDS:
        raise HTTPException(400, f"backend must be one of {sorted(_MASTERS_BACKENDS)}")
    try:
        m = manifest_mod.load(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown episode {slug}")
    m.setdefault("comfyui", {})["workflow"] = _MASTERS_BACKENDS[backend]
    manifest_mod.save(slug, m)
    return {"ok": True, "slug": slug, "backend": backend,
            "workflow": _MASTERS_BACKENDS[backend]}


@app.get("/api/episodes/{slug}/srt")
def get_srt(slug: str):
    return srt_mod.read(slug)


@app.put("/api/episodes/{slug}/srt")
async def put_srt(slug: str, body: dict = Body(...)):
    try:
        return srt_mod.write(slug, body.get("entries") or [])
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# ---------- Media streaming ----------

@app.get("/api/episodes/{slug}/cue/{cue_id}/audio")
def get_cue_audio(slug: str, cue_id: str, request: Request):
    try:
        cue_id = shows_mod.safe_segment(cue_id, "cue_id")
    except ValueError:
        raise HTTPException(400, "bad cue_id")
    p = ep_mod.episode_dir(slug) / "vo" / f"{cue_id}.wav"
    return media_mod.stream_file(request, p, content_type="audio/wav")


@app.get("/api/episodes/{slug}/shot/{key}/preview")
def get_shot_preview(slug: str, key: str, request: Request):
    try:
        key = shows_mod.safe_segment(key, "shot key")
    except ValueError:
        raise HTTPException(400, "bad shot key")
    ep = ep_mod.episode_dir(slug)
    # Cloud (Higgsfield) shots are per-shot-id mp4 clips, not webp masters.
    hf_clip = ep / "clips" / f"hf_{key}.mp4"
    if hf_clip.exists():
        return media_mod.stream_file(request, hf_clip, content_type="video/mp4")
    candidates = [
        ep / "clips" / f"{key}_master.zs.webp",
        ep / "clips" / f"broll_{key}.zs.webp",
    ]
    if key == "safe":
        candidates.insert(0, ep / "clips" / "safe_master.zs.webp")
    if key == "empty_room":
        candidates.insert(0, ep / "clips" / "c09_s1.zs.webp")
    for p in candidates:
        if p.exists():
            return media_mod.stream_file(request, p, content_type="image/webp")
    raise HTTPException(404, f"no preview for shot {key}")


@app.get("/api/episodes/{slug}/title/{key}/preview")
def get_title_preview(slug: str, key: str, request: Request):
    try:
        key = shows_mod.safe_segment(key, "title key")
    except ValueError:
        raise HTTPException(400, "bad key")
    p = ep_mod.episode_dir(slug) / "titles" / f"{key}.mp4"
    if not p.exists():
        p = SHARES / "assets" / "titles" / f"{key}.mp4"  # shared fallback (stage-4 resolution)
    return media_mod.stream_file(request, p, content_type="video/mp4")


@app.get("/api/episodes/{slug}/final/video")
def get_final_video(slug: str, request: Request):
    # For a localized variant the dub is final/<slug>.<lang>.mp4 (no bare <slug>.mp4).
    p = ep_mod.final_video_path(ep_mod.episode_dir(slug), slug)
    return media_mod.stream_file(request, p, content_type="video/mp4")


@app.get("/api/episodes/{slug}/final/thumb")
def get_final_thumb(slug: str, request: Request):
    p = ep_mod.final_thumb_path(ep_mod.episode_dir(slug), slug)
    return media_mod.stream_file(request, p, content_type="image/jpeg")


# ---------- Pipeline ----------

@app.post("/api/episodes/{slug}/pipeline/run")
async def post_run(slug: str, body: dict = Body(default={})):
    try:
        return await pipeline_mod.submit(slug,
                                          from_stage=body.get("from_stage"),
                                          only=body.get("only"))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"upstream render: {e}")


@app.post("/api/episodes/{slug}/cue/{cue_id}/regen")
async def post_cue_regen(slug: str, cue_id: str):
    return await regen_mod.regen_cue(slug, cue_id)


@app.post("/api/episodes/{slug}/shot/{key}/regen")
async def post_shot_regen(slug: str, key: str):
    return await regen_mod.regen_shot(slug, key)


@app.post("/api/episodes/{slug}/title/{key}/regen")
async def post_title_regen(slug: str, key: str):
    """Queue a HyperFrames render for title_assets[key]. Returns {job_id}."""
    try:
        job_id = await hf_mod.submit(slug, key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return {"job_id": job_id, "queued": True,
            "events_url": f"/api/hf/jobs/{job_id}/stream",
            "status_url": f"/api/hf/jobs/{job_id}"}


@app.get("/api/hf/jobs/{job_id}")
def get_hf_job(job_id: str):
    s = hf_mod.status(job_id)
    if not s:
        raise HTTPException(404, "hyperframes job not found")
    return s


@app.get("/api/hf/jobs/{job_id}/stream")
async def get_hf_job_stream(job_id: str, since: int = 0):
    return StreamingResponse(
        hf_mod.stream(job_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/events/stream")
async def get_events_stream(since: int = 0):
    """Global server-event SSE for the toast stack — every events.emit() from any
    source (HyperFrames jobs, agen/LLM activity, mutating MCP calls). One
    subscription per browser tab; only events after connect are sent."""
    return StreamingResponse(
        events_mod.stream(since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/api/episodes/{slug}/sfx/fetch")
async def post_sfx_fetch(slug: str, body: dict = Body(...)):
    """Run freesound_fetch.py for `query` and pin the result to manifest.sfx[]."""
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "query required")
    cue_id = body.get("cue_id")
    at = body.get("at") or "start"
    if at not in ("start", "end"):
        raise HTTPException(400, "at must be 'start' or 'end'")
    duration_max = float(body.get("duration_max") or 4.0)
    basename = body.get("basename") or None
    gain_db = float(body.get("gain_db") if body.get("gain_db") is not None else -6.0)
    fade_s = float(body.get("fade_s") if body.get("fade_s") is not None else 0.5)
    license_mode = body.get("license") or "cc0"
    return await sfx_mod.fetch_and_pin(
        slug, query, cue_id=cue_id, at=at,
        duration_max=duration_max, basename=basename,
        gain_db=gain_db, fade_s=fade_s, license_mode=license_mode,
    )


@app.delete("/api/episodes/{slug}/sfx")
async def del_sfx(slug: str, file: str):
    return sfx_mod.remove(slug, file)


@app.put("/api/episodes/{slug}/sfx")
async def put_sfx(slug: str, body: dict = Body(...)):
    """Replace manifest.sfx[] wholesale — the single mutation for the Audio-page
    timeline (add-from-library / reorder / move / delay-recompute)."""
    sfx = body.get("sfx")
    if not isinstance(sfx, list):
        raise HTTPException(400, "sfx must be a list")
    m = manifest_mod.load(slug)
    m["sfx"] = sfx
    manifest_mod.save(slug, m)
    return {"ok": True, "count": len(sfx)}


@app.put("/api/episodes/{slug}/overlays")
async def put_overlays(slug: str, body: dict = Body(...)):
    """Replace manifest.overlays[] wholesale — the single mutation for the dope sheet
    (drag-to-place) and the timeline's GRAPHICS track (drag/resize/edit/delete spanning
    title-card placements)."""
    overlays = body.get("overlays")
    if not isinstance(overlays, list):
        raise HTTPException(400, "overlays must be a list")
    m = manifest_mod.load(slug)
    m["overlays"] = overlays
    manifest_mod.save(slug, m)
    return {"ok": True, "count": len(overlays)}


# ---------- Cross-episode asset corpus (drawer "all episodes" toggle) ----------

@app.get("/api/corpus/shot-alternates")
def get_shot_alternates(slug: str | None = None):
    """Archived (non-live) shot generations — one row per version. `slug` scopes to a
    single episode; omit it for the whole corpus. Backs the drawer's 'alternates' toggle.
    Declared before /api/corpus/{kind} so the static path wins the match."""
    return {"alternates": corpus_mod.shot_alternates(slug)}


@app.get("/api/corpus/{kind}")
def get_corpus(kind: str):
    """All shots / titles / cues across every episode (each row tagged with its `slug`).
    Backs the asset drawer's 'all episodes' toggle so a shot from another episode can be
    pulled into the one being edited."""
    if kind == "shots":
        return {"shots": corpus_mod.shots()}
    if kind == "titles":
        return {"titles": corpus_mod.titles()}
    if kind == "cues":
        return {"cues": corpus_mod.cues()}
    raise HTTPException(400, "kind must be shots|titles|cues")


@app.post("/api/episodes/{slug}/import-shot-version")
async def post_import_shot_version(slug: str, body: dict = Body(...)):
    """Pull a specific archived generation of a shot into this episode (copies that take's
    frame over as the master + pins its seed; archives the current live take first)."""
    from_slug, key, kind, v = body.get("from_slug"), body.get("key"), body.get("kind"), body.get("v")
    if not (from_slug and key and kind in ("character", "broll") and v is not None):
        raise HTTPException(400, "from_slug, key, kind(character|broll), v required")
    try:
        return corpus_mod.import_shot_version(slug, from_slug, key, kind, int(v))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/episodes/{slug}/import-shot")
async def post_import_shot(slug: str, body: dict = Body(...)):
    """Copy a shot definition (core+seed) from another episode's manifest into this one,
    so a cross-episode shot dropped on the timeline renders here from the same seed."""
    from_slug, key, kind = body.get("from_slug"), body.get("key"), body.get("kind")
    if not (from_slug and key and kind in ("character", "broll")):
        raise HTTPException(400, "from_slug, key, kind(character|broll) required")
    try:
        return corpus_mod.import_shot(slug, from_slug, key, kind)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/episodes/{slug}/import-title")
async def post_import_title(slug: str, body: dict = Body(...)):
    """Copy a title-card definition from another episode's manifest into this one."""
    from_slug, key = body.get("from_slug"), body.get("key")
    if not (from_slug and key):
        raise HTTPException(400, "from_slug, key required")
    try:
        return corpus_mod.import_title(slug, from_slug, key)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.put("/api/episodes/{slug}/cue-shots")
async def put_cue_shots(slug: str, body: dict = Body(...)):
    """Set cue.shots[] for the named cues — the single mutation for the timeline SHOTS
    track (drag a shot onto a cue, move between cues, reorder, drag-out to remove). Only
    the cues present in the body are touched; everything else in the manifest is left
    alone. Mirrors put_overlays/put_sfx. Shots keep the ManifestShot shape
    ({id,kind,who?,asset?,seed?}); save() re-validates."""
    cues = body.get("cues")
    if not isinstance(cues, dict):
        raise HTTPException(400, "cues must be an object of {cueId: [shot,...]}")
    m = manifest_mod.load(slug)
    by_id = {c.get("id"): c for c in (m.get("cues") or [])}
    n = 0
    for cid, shots in cues.items():
        c = by_id.get(cid)
        if c is not None and isinstance(shots, list):
            c["shots"] = shots
            n += 1
    manifest_mod.save(slug, m)
    return {"ok": True, "count": n}


@app.put("/api/episodes/{slug}/music/beds")
async def put_music_beds(slug: str, body: dict = Body(...)):
    """Replace manifest.music.beds[] wholesale — the single mutation for the Video
    timeline's MUSIC track (drag-to-place / drag-resize cue-spanning beds). Leaves
    music.clips[] (the file pool) and other music settings untouched."""
    beds = body.get("beds")
    if not isinstance(beds, list):
        raise HTTPException(400, "beds must be a list")
    m = manifest_mod.load(slug)
    music = m.get("music")
    if not isinstance(music, dict):
        music = {}
    music["beds"] = beds
    m["music"] = music
    manifest_mod.save(slug, m)
    return {"ok": True, "count": len(beds)}


@app.put("/api/episodes/{slug}/speaker-voice")
async def put_speaker_voice(slug: str, body: dict = Body(...)):
    """Assign or clear one speaker's voice in manifest.voice.speaker_map.
    Body: {speaker, engine, profile_id?, voice_name?}. engine='omnivoice' sets
    the mapping (preserving any existing speed/seed/etc. for that speaker);
    engine in (piper/default/empty) CLEARS it so the speaker falls back to the
    default HAL voice. The render's per-cue VO hash covers engine+profile, so
    only that speaker's cues re-render."""
    speaker = (body.get("speaker") or "").strip()
    if not speaker:
        raise HTTPException(400, "speaker required")
    engine = (body.get("engine") or "").strip().lower()
    m = manifest_mod.load(slug)
    voice = m.get("voice") if isinstance(m.get("voice"), dict) else {}
    smap = voice.get("speaker_map") if isinstance(voice.get("speaker_map"), dict) else {}
    if engine == "omnivoice":
        pid = (body.get("profile_id") or "").strip()
        if not pid:
            raise HTTPException(400, "profile_id required for omnivoice")
        entry = dict(smap.get(speaker) or {})  # keep speed/seed/guidance/instruct
        entry["engine"] = "omnivoice"
        entry["profile_id"] = pid
        if body.get("voice_name"):
            entry["voice_name"] = body["voice_name"]
        smap[speaker] = entry
        mapped = True
    else:
        smap.pop(speaker, None)  # fall back to default (HAL)
        mapped = False
    voice["speaker_map"] = smap
    m["voice"] = voice
    manifest_mod.save(slug, m)
    # Propagate to the show defaults so every FUTURE episode of this show inherits
    # the cast's voice (create_episode deep-copies episode_defaults). Best-effort.
    propagated = False
    try:
        show_id = shows_mod.show_of(slug)
        cfg = ({"engine": "omnivoice", "profile_id": entry["profile_id"],
                **({"voice_name": entry["voice_name"]} if entry.get("voice_name") else {})}
               if mapped else None)
        propagated = shows_mod.set_default_speaker_voice(show_id, speaker, cfg)
    except Exception:
        pass
    return {"ok": True, "speaker": speaker, "mapped": mapped, "propagated": propagated}


@app.post("/api/shutdown")
async def post_shutdown():
    """Free the GPU, then stop the Studio server. Stops the VRAM-holding containers
    (ComfyUI / OmniVoice / Ollama) and then SIGTERMs this process for a graceful
    uvicorn exit. The 200 is returned BEFORE shutdown (a 0.4s timer) so the UI can
    show its 'shutting down' modal. A clean exit (code 0) won't trip the systemd
    unit's Restart=on-failure, so the service stays down until restarted."""
    import os
    import signal
    import subprocess
    import threading

    def _go():
        for c in ("comfyui", "omnivoice", "ollama"):
            try:
                subprocess.run(["docker", "stop", "-t", "10", c],
                               capture_output=True, text=True, timeout=30)
            except Exception:
                pass
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Timer(0.4, _go).start()
    return {"ok": True, "message": "freeing GPU and shutting down"}


# ---------- LLM shot-list generation (Ollama on-demand) ----------

@app.post("/api/episodes/{slug}/shots/generate")
def post_shots_generate(slug: str, body: dict = Body(default={})):
    """Dry run: ask the local LLM to propose the shot list (reuse vs mint + per-cue
    shots). Body {only_missing:true} plans ONLY cues without shots (gap-fill, the safe
    default) so apply won't clobber already-tuned cues. 409 if the GPU is busy (a render
    is active). Sync def → runs in the threadpool so the long model call doesn't block."""
    only_missing = bool(body.get("only_missing"))
    busy, free = agen_mod.gpu_busy()
    if busy and engines_mod.route("textgen") == "ollama_local":
        # Only Ollama competes for VRAM; the claude_cli engine runs off-GPU.
        raise HTTPException(409, f"GPU busy ({free} MiB free) — a render is active; try again when idle")
    activity_mod.set_running("Filling missing shots" if only_missing else "Generating shot list", ttl=180)
    try:
        out = shotgen_mod.generate(slug, only_missing=only_missing)
        activity_mod.clear()
        return out
    except FileNotFoundError as e:
        activity_mod.clear()
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        activity_mod.set_error("Shot-gen failed")
        raise HTTPException(500, f"shot-gen failed: {e}")


@app.post("/api/episodes/{slug}/shots/apply")
async def post_shots_apply(slug: str, body: dict = Body(...)):
    """Merge an approved proposal (from /shots/generate, possibly edited) into the
    manifest — write new character/broll defs and set each planned cue's shots[]."""
    proposal = body.get("proposal")
    if not isinstance(proposal, dict):
        raise HTTPException(400, "proposal object required")
    try:
        out = shotgen_mod.apply(slug, proposal)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    # New character defs from the shot plan → Cast stubs (best-effort).
    try:
        from . import characters as chars_mod
        show, _ = shows_mod.resolve_episode(slug)
        out["cast_created"] = chars_mod.ensure_stubs(show, manifest_mod.load(slug))
    except Exception:
        pass
    return out


# ---------- LLM sound-effect-list generation (Ollama on-demand) ----------

@app.post("/api/episodes/{slug}/sfx/generate")
def post_sfx_generate(slug: str):
    """Dry run: ask the local LLM to read the script as a radio play and propose SFX
    placements (favoring the existing kit, flagging any that need acquiring). 409 if the
    GPU is busy (a render is active). Sync def → threadpool so the model call doesn't
    block the event loop."""
    busy, free = agen_mod.gpu_busy()
    if busy and engines_mod.route("textgen") == "ollama_local":
        # Only Ollama competes for VRAM; the claude_cli engine runs off-GPU.
        raise HTTPException(409, f"GPU busy ({free} MiB free) — a render is active; try again when idle")
    activity_mod.set_running("Generating SFX list", ttl=180)
    try:
        out = sfxgen_mod.generate(slug)
        activity_mod.clear()
        return out
    except FileNotFoundError as e:
        activity_mod.clear()
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        activity_mod.set_error("SFX-gen failed")
        raise HTTPException(500, f"sfx-gen failed: {e}")


@app.post("/api/episodes/{slug}/sfx/apply")
async def post_sfx_apply(slug: str, body: dict = Body(...)):
    """Merge an approved SFX proposal (possibly edited) into manifest.sfx[] in the same
    list shape the Audio-page drag-drop uses, so the effects land in the timeline."""
    proposal = body.get("proposal")
    if not isinstance(proposal, dict):
        raise HTTPException(400, "proposal object required")
    try:
        return sfxgen_mod.apply(slug, proposal)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# ---------- LLM card-text generation (Ollama on-demand) ----------

@app.get("/api/card-types")
def get_card_types():
    """Supported card types for the Studio card-text generator dropdown."""
    return {"card_types": cardgen_mod.card_types()}


@app.post("/api/episodes/{slug}/card-text/generate")
def post_card_text_generate(slug: str, body: dict = Body(default={})):
    """Dry run: ask the local LLM to write the five HyperFrames fields for a card type
    (deadpan/funny, lifting a punchline from the script). 409 if the GPU is busy. Sync
    def → threadpool so the long model call doesn't block the loop."""
    card_type = (body.get("card_type") or "").strip()
    composition = (body.get("composition") or "").strip() or None
    if not card_type:
        raise HTTPException(400, "card_type required")
    busy, free = agen_mod.gpu_busy()
    if busy and engines_mod.route("textgen") == "ollama_local":
        # Only Ollama competes for VRAM; the claude_cli engine runs off-GPU.
        raise HTTPException(409, f"GPU busy ({free} MiB free) — a render is active; try again when idle")
    activity_mod.set_running(f"Writing {card_type} card text", ttl=180)
    try:
        out = cardgen_mod.generate(slug, card_type, composition=composition)
        activity_mod.clear()
        return out
    except ValueError as e:
        activity_mod.clear()
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        activity_mod.clear()
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        activity_mod.set_error("Card-text gen failed")
        raise HTTPException(500, f"card-text gen failed: {e}")


@app.post("/api/episodes/{slug}/card-text/apply")
def post_card_text_apply(slug: str, body: dict = Body(...)):
    """Merge approved (possibly edited) card fields into the manifest. For youtube_thumb
    this writes manifest.youtube_thumb; otherwise title_assets[key]. The existing
    Graphics render routes then pick it up unchanged."""
    card_type = (body.get("card_type") or "").strip()
    key = (body.get("key") or "").strip()
    fields = body.get("fields")
    composition = (body.get("composition") or "").strip() or None
    if not card_type:
        raise HTTPException(400, "card_type required")
    if not isinstance(fields, dict):
        raise HTTPException(400, "fields object required")
    try:
        return cardgen_mod.apply(slug, card_type, key, fields, composition=composition)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/emergency-stop")
def post_emergency_stop():
    """Kill the active render (run.py tree), interrupt + clear the ComfyUI queue, free its
    VRAM, and stop the on-demand GPU containers. Best-effort; returns a per-step report."""
    report = emergency_mod.stop_all()
    try:
        activity_mod.clear()
    except Exception:
        pass
    return {"ok": True, "report": report}


# ---------- LLM composition generation (Ollama on-demand) ----------

@app.post("/api/episodes/{slug}/composition/generate")
def post_composition_generate(slug: str, body: dict = Body(...)):
    """Ask the local model to write a NEW HyperFrames composition (animated card HTML) from
    a brief, save it as the template named `key`, and return its placeholder field set. 409
    if the GPU is busy (a render is active). Sync def → threadpool for the long model call."""
    key = (body.get("key") or "").strip()
    brief = (body.get("brief") or "").strip()
    busy, free = agen_mod.gpu_busy()
    if busy and engines_mod.route("textgen") == "ollama_local":
        # Only Ollama competes for VRAM; the claude_cli engine runs off-GPU.
        raise HTTPException(409, f"GPU busy ({free} MiB free) — a render is active; try again when idle")
    activity_mod.set_running(f"Generating composition {key}", ttl=240)
    try:
        out = compgen_mod.generate(slug, key, brief)
        activity_mod.clear()
        return out
    except ValueError as e:
        activity_mod.clear()
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        activity_mod.set_error("Composition gen failed")
        raise HTTPException(500, f"composition-gen failed: {e}")


# ---------- Asset library (assets/sfx, assets/music) ----------

@app.get("/api/assets/{kind}")
def get_assets(kind: str):
    if kind not in assets_mod.KINDS:
        raise HTTPException(404, f"unknown asset kind: {kind}")
    return {"assets": assets_mod.list_assets(kind)}


@app.get("/api/assets/{kind}/{file}/audio")
def get_asset_audio(kind: str, file: str, request: Request):
    p = assets_mod.asset_path(kind, file)
    if not p:
        raise HTTPException(404, "asset not found")
    ctype = "audio/mpeg" if p.suffix.lower() == ".mp3" else "audio/wav"
    return media_mod.stream_file(request, p, content_type=ctype)


@app.post("/api/episodes/{slug}/music/add-bed")
async def post_music_add_bed(slug: str, body: dict = Body(...)):
    """Add a library music file to manifest.music.clips[] (a bed)."""
    file = (body.get("file") or "").strip()
    if not file:
        raise HTTPException(400, "file required")
    m = manifest_mod.load(slug)
    music = m.get("music")
    if not isinstance(music, dict):
        music = {}
    clips = music.get("clips")
    if not isinstance(clips, list):
        clips = []
    added = file not in clips
    if added:
        clips.append(file)
    music["clips"] = clips
    music.setdefault("source_dir", str(assets_mod.KINDS["music"]))
    m["music"] = music
    manifest_mod.save(slug, m)
    return {"ok": True, "added": added, "clips": clips}


# ---------- agen (local music/SFX generation) ----------

@app.get("/api/agen/status")
def get_agen_status():
    busy, free = agen_mod.gpu_busy()
    return {"busy": busy, "gpu_free_mib": free, "min_free_mib": agen_mod.MIN_FREE_MIB}


@app.post("/api/episodes/{slug}/sfx/gen")
async def post_sfx_gen(slug: str, body: dict = Body(...)):
    """Generate an SFX one-shot with agen (AudioGen), normalize to kit, pin to manifest.sfx[]."""
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt required")
    at = body.get("at") or "start"
    if at not in ("start", "end"):
        raise HTTPException(400, "at must be 'start' or 'end'")
    activity_mod.set_running("Rendering SFX", ttl=120)
    res = await agen_mod.gen_sfx_and_pin(
        slug, prompt, cue_id=body.get("cue_id"), at=at,
        duration=float(body.get("duration") or 3.0),
        seed=body.get("seed"), basename=body.get("basename") or None,
        gain_db=float(body.get("gain_db") if body.get("gain_db") is not None else -6.0),
        fade_s=float(body.get("fade_s") if body.get("fade_s") is not None else 0.5),
    )
    activity_mod.set_error("SFX gen busy") if res.get("busy") else activity_mod.clear()
    if res.get("busy"):
        raise HTTPException(409, res.get("hint") or "GPU busy")
    return res


@app.post("/api/episodes/{slug}/music/gen")
async def post_music_gen(slug: str, body: dict = Body(...)):
    """Generate a music bed with agen (MusicGen/Riffusion) and add it to manifest.music.clips[]."""
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt required")
    activity_mod.set_running("Rendering music", ttl=180)
    res = await agen_mod.gen_music(
        slug, prompt, engine=body.get("engine") or "music",
        duration=float(body.get("duration") or 20.0),
        seed=body.get("seed"), basename=body.get("basename") or None,
        add_to_clips=bool(body.get("add_to_clips", True)),
    )
    activity_mod.set_error("Music gen busy") if res.get("busy") else activity_mod.clear()
    if res.get("busy"):
        raise HTTPException(409, res.get("hint") or "GPU busy")
    return res


@app.get("/api/jobs")
async def get_jobs():
    return await pipeline_mod.jobs_list()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    return await pipeline_mod.status(job_id)


@app.get("/api/jobs/{job_id}/stream")
async def get_job_stream(job_id: str, since: int = 0):
    return StreamingResponse(
        pipeline_mod.stream(job_id, since=since),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------- Chat (ss-chat-channel → always-on Max session) ----------

@app.post("/api/episodes/{slug}/chat")
async def post_chat(slug: str, body: dict = Body(...)):
    msg = (body.get("message") or "").strip()
    if not msg:
        raise HTTPException(400, "empty message")
    session_id = body.get("session_id") or None
    try:
        result = await chat_mod.send(slug, msg, session_id=session_id)
    except TimeoutError as e:
        raise HTTPException(504, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return result


@app.post("/api/chat/reply")
async def post_chat_reply(request: Request, body: dict = Body(...)):
    """Callback hit by ss-chat-channel when Max calls ss_chat_reply. Token-gated
    by the same SS_CHAT_WEBHOOK_TOKEN the channel signs outbound replies with."""
    presented = (request.headers.get("x-webhook-token") or "").strip()
    if not CHAT_WEBHOOK_TOKEN or presented != CHAT_WEBHOOK_TOKEN:
        raise HTTPException(403, "forbidden")
    request_id = body.get("request_id")
    text = body.get("text")
    if not request_id or not isinstance(text, str):
        raise HTTPException(400, "request_id and text required")
    delivered = chat_mod.deliver(str(request_id), text)
    return {"ok": delivered, "request_id": request_id}


# ---------- Feature routers (versioning, graphics, writers' room, youtube, docs, git-sync) ----------

app.include_router(routes_assets.router)
app.include_router(routes_graphics.router)
app.include_router(routes_writers.router)
app.include_router(routes_youtube.router)
app.include_router(routes_docs.router)
app.include_router(routes_gitsync.router)
app.include_router(routes_shows.router)
app.include_router(routes_voices.router)
app.include_router(routes_version.router)
app.include_router(routes_diag.router)
app.include_router(routes_localize.router)
app.include_router(routes_publish.router)
app.include_router(routes_higgsfield.router)
app.include_router(routes_engines.router)
app.include_router(routes_characters.router)
app.include_router(routes_sync.router)


# ---------- MCP server (Streamable HTTP at /mcp) ----------
# Exposes the API above as MCP tools so agents (Claude Desktop/Code via
# `mcp-remote http://<host>:8774/mcp --allow-http`) can drive Studio. Same
# trust model as the rest of the app: no auth, loopback bind by default.
app.mount("/mcp", mcp_server.attach(app))


class _McpSlash:
    """Pure-ASGI rewrite of /mcp -> /mcp/ . Clients POST to the bare path, but a
    Starlette Mount only matches its subtree — without this the request falls
    through to the SPA static mount and 405s."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


app.add_middleware(_McpSlash)


# ---------- HyperFrames template preview (read-only static serve of the template dirs) ----------
# Lets the New/Edit title-card modal show a live iframe of a composition's layout
# (placeholders render as literal ‹TOKENS›, so you can see where each field lands).
_HF_TEMPLATES = SHARES / "assets" / "hyperframes" / "templates"
if _HF_TEMPLATES.exists():
    app.mount("/api/hf/template-assets", StaticFiles(directory=str(_HF_TEMPLATES)), name="hf-templates")


# ---------- SPA static mount (last, after API routes) ----------

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
else:
    @app.get("/")
    def _no_spa():
        return JSONResponse(
            {"warning": "frontend not built — run `cd studio/frontend && npm run build`",
             "dist": str(FRONTEND_DIST)},
            status_code=200,
        )
