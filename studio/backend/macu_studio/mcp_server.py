"""MCP server for MACU Studio — exposes the Studio REST API as MCP tools.

Mounted into the FastAPI app at ``/mcp`` (Streamable HTTP). Any MCP client —
Claude Desktop via ``npx mcp-remote http://<host>:8774/mcp --allow-http``,
Claude Code via ``claude mcp add --transport http studio http://<host>:8774/mcp``,
or anything else that speaks Streamable HTTP — can drive the full episode
pipeline: write scripts, build manifests, generate shot/SFX/card proposals,
kick renders, and publish to macu-web.

Design notes:
- Tools call the existing REST routes **in-process** via httpx's ASGITransport,
  so there is exactly one implementation of every behavior (the routes) and the
  MCP layer can never drift from the UI.
- Tool descriptions and error payloads are written to hand-hold smaller models
  (sonnet/haiku): every error carries a ``hint`` with the next thing to try, and
  ``studio_overview`` returns a step-by-step workflow cheat-sheet.
- No auth, same as the rest of Studio — the server binds loopback by default;
  see config.HOST. Do NOT expose :8774 (or /mcp) to untrusted networks.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import activity as activity_mod
from . import cowork_jobs
from . import events as events_mod

WORKFLOW_GUIDE = """\
MACU Studio drives an end-to-end AI video pipeline (scripts -> voices -> video ->
subtitles -> YouTube/web publish). Episodes live under a SHOW; each episode has a
script.md (the writing surface) and a manifest.json (the render plan).

TYPICAL WORKFLOW — new episode, start to published:
 1. list_shows                      -> pick a show id (or create_show)
 2. create_episode(show, slug, title)
 3. write_script(slug, text)        -> script.md (format below)
 4. manifest_from_script(slug)      -> preview cue generation; rerun with apply=true
 5. generate_shots(slug)            -> LLM shot-list proposal; review, then rerun
                                       with apply=true (or pass the edited proposal)
 6. generate_sfx(slug) [optional]   -> same dry-run/apply pattern
 7. generate_card_text(slug, card_type) [optional] -> title cards / YouTube thumb;
    render_title_cards(slug) renders just the cards (no video-masters stage)
 8. run_pipeline(slug)              -> queues the render; then await_render(slug,
                                       job_id) blocks to a milestone (don't
                                       blind-poll render_status in a loop)
 9. git_sync(slug)                  -> commit the episode's text files
10. set_episode_meta / set_episode_youtube / set_episode_published, then
    publish_show(show)              -> push to the connected macu-web site

CHARACTERS (show-level cast, feeds Higgsfield i2v/lipsync shots):
 - list_characters / upsert_character(show, key, still_prompt=...) build the roster.
 - generate_character_takes makes reference stills (engine comfy_zimage = local +
   free; higgsfield = credits; remote_render = a remote GPU box; empty = the
   routed default). Poll character_take_status; set_default_take picks the keeper.
   Each take carries `url`/`thumb_url` (+ local `path`) — pull these to PREVIEW takes
   in chat for the user to choose, no screenshot needed.
 - PREFERRED curated path for library characters: generate_character_takes ->
   set_default_take -> use_character_in_episode(slug, take=...). This reuses one
   vetted still across episodes; prefer it over generate_character_still / a per-
   episode still_prompt (those mint a fresh one-off still each time).
 - Cast stubs are auto-seeded when manifest_from_script / apply_shots run — new
   speakers appear in list_characters with empty prompts to fill in.
 - use_character_in_episode copies the still into an episode (pre-stamped, free).
   It returns `invalidates` when replacing a still would re-bill paid cloud
   shots — STOP and confirm with the user before passing overwrite_still=true.
 - engines_status / set_engine_route control which service runs each capability.
 - MASTERS BACKEND: set_masters_backend(slug, 'zeroscope'|'wan_i2v'). zeroscope =
   text-to-video (default). wan_i2v = character shots animate from a seed still
   (generate_stills renders those z-image stills first); b-roll stays zeroscope.
   WAN needs the --with-talking-head pack on the render box.

VOICES & CASTING (OmniVoice TTS — consumer-lifecycle, started on demand):
 - list_voices shows the cloned roster; set_speaker_voice casts a SPEAKER to one.
 - ALWAYS validate_cast(slug) before a VO render — it flags speakers cast to a
   voice that won't resolve (status 'missing' → would render a generic fallback),
   catching it in ~1s instead of after a multi-minute render.
 - Voices are portable by voice_name but cast by a machine-specific profile_id;
   import_voices(zip_path?, show=...) (re)clones reference clips into the LOCAL
   OmniVoice and rebinds manifests by name. VO render also self-heals by name and
   FAILS LOUD (never a silent fallback) if a cue's voice resolves by neither.
 - start_voice_engine brings OmniVoice up; preview_vo(slug, cue_id) auditions one
   line in seconds. render_title_cards(slug) renders title cards without masters.

SCRIPT FORMAT (script.md):
  ## SEGMENT HEADER                 -> starts a segment
  **SPEAKER:** dialogue...          -> one voice cue (may wrap multiple lines)
  » Ron core → b-roll: ruins → MACU title card
                                    -> optional shot line for the cue above:
                                       "X core" = character shot, "b-roll: X" =
                                       b-roll, "... card"/"... bumper" = title card.
                                       Cues without a » line get one character
                                       shot of their speaker automatically.

THINGS TO KNOW:
- Everything render/GPU-related is queued and asynchronous: run_pipeline returns a
  job_id immediately; renders take many minutes. Don't blind-poll — call
  await_render(slug, job_id, until='masters'|'final'|<stage>) to BLOCK until a
  checkpoint, then act. render_status(job_id) is the one-shot snapshot.
- generate_* tools run a local LLM on the GPU and return 409 if a render is
  active — check studio_status first.
- All generate_* tools are DRY RUNS by default. Nothing is written until you call
  them with apply=true (or call the matching apply step). Review proposals with
  the user before applying when in doubt.
- write_manifest replaces the whole manifest: read_manifest first, modify, write
  back. Prefer the purpose-built tools (set_episode_meta, set_speaker_voice...)
  over hand-editing manifest JSON.
- CLOUD SHOTS: kind 'higgsfield' (cloud t2v/i2v) bills the user's Higgsfield
  account per generation. kind 'lipsync' (still + cue VO -> talking head; must
  be the FIRST shot in its cue, max one per cue — b-roll/character cutaways may
  follow it over the continuing VO) follows the lipsync engine route (engines_status):
  higgsfield = billed chunk+chain; local_wan / remote_render = free (local or
  remote GPU, no chunking). ALWAYS call estimate_episode_cost and surface the
  total to the user BEFORE run_pipeline / generate_cloud_shot on an episode
  with cloud shots — it prices by the current routing. Cached shots are free;
  crop/trim edits never re-bill. higgsfield_status shows connection/plan/
  credits (connecting is a Settings-UI action, not an MCP one).

COWORK JOB-BOARD (free-web -> local-harvest, the $0 loop): Higgsfield's unlimited
tiers are WEB-APP ONLY (the API always bills). A browser-capable CoWork agent works
a job queue here: cowork_jobs_create queues "generate this" jobs; CoWork claims them
(cowork_job_claim), generates them FREE in the Higgsfield web app, then reports the
result generation id (cowork_job_complete / cowork_job_update status=done,
result_gen_ids=[...]) and Studio auto-harvests the result into the episode target
(still -> stills/<key>.png, video -> clips/hf_<shot>.mp4). cowork_recent_generations
finds the id of a just-made web gen. cowork_jobs_list watches the queue (also the
"CoWork" UI tab). The browser-side how-to is the cowork-harvest + higgsfield-web-
free-gen skills. result_gen_ids are Higgsfield GENERATION ids, not URLs.
"""

mcp = FastMCP(
    "macu-studio",
    instructions=WORKFLOW_GUIDE,
    stateless_http=True,
    json_response=True,
    # Studio is reached by LAN IP / hostname, not just localhost — the SDK's
    # DNS-rebinding Host check would 421 those. Same trust model as the rest of
    # the (unauthenticated) app: protection comes from the loopback-default bind.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
# We mount the sub-app at /mcp ourselves (main.py), so the sub-app serves at its root.
mcp.settings.streamable_http_path = "/"

# The FastAPI app we call back into; set by attach() at import-from-main time.
_app = None

# Long-poll-ish budget: generate_* tools hold the connection while Ollama loads +
# infers (can be minutes); media/manifest calls are quick.
_TIMEOUT = httpx.Timeout(connect=5.0, read=600.0, write=30.0, pool=10.0)


def attach(app) -> Any:
    """Wire the FastAPI app in and return the Streamable-HTTP ASGI sub-app."""
    global _app
    _app = app
    return mcp.streamable_http_app()


def session_manager():
    return mcp.session_manager


_HINTS = {
    404: "Unknown slug/key? Call list_episodes (or list_shows) to see what exists.",
    409: "The GPU is busy (a render or generation is active). Check studio_status and retry when idle.",
    400: "The request body was rejected — re-read this tool's description for the expected fields.",
    502: "An upstream service (render server / macu-web / Ollama) is unreachable. studio_status shows render-server health.",
}


def _mcp_label(path: str) -> str:
    """Human line for the event feed: '/api/episodes/awb-001/git-sync' → 'awb-001 git-sync'."""
    p = path.split("?")[0].strip("/")
    if p.startswith("api/"):
        p = p[4:]
    if p.startswith("episodes/"):
        p = p[len("episodes/"):]
    return p.replace("/", " ")


async def _api(method: str, path: str, *, body: dict | None = None,
               text: str | None = None, params: dict | None = None) -> Any:
    """Call a Studio REST route in-process. Returns parsed JSON, or an
    {error, status, detail, hint} envelope on failure — never raises, so even a
    confused client gets something actionable back."""
    if _app is None:
        return {"error": True, "detail": "MCP server not attached to the Studio app (startup bug)"}
    # Surface mutating MCP calls in the topbar + toast stack: the box should
    # never look IDLE while an agent is driving it (reads stay silent).
    mutating = method in ("POST", "PUT", "DELETE", "PATCH")
    label = f"MCP: {_mcp_label(path)}" if mutating else ""
    if mutating:
        events_mod.emit("mcp", label, level="running")
        activity_mod.set_running(label, ttl=4.0, quiet=True)
    transport = httpx.ASGITransport(app=_app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://studio",
                                     timeout=_TIMEOUT) as client:
            r = await client.request(method, path, json=body, content=text, params=params)
    except Exception as e:  # noqa: BLE001 — surface, don't crash the session
        if mutating:
            events_mod.emit("mcp", f"{label} failed: {type(e).__name__}", level="error")
        return {"error": True, "detail": f"{type(e).__name__}: {e}",
                "hint": "Internal call failed — is the episode dir readable? studio_status may help."}
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except Exception:  # noqa: BLE001
            detail = r.text[:500]
        out = {"error": True, "status": r.status_code, "detail": detail}
        if r.status_code in _HINTS:
            out["hint"] = _HINTS[r.status_code]
        if mutating:
            events_mod.emit("mcp", f"{label} failed ({r.status_code})", level="error")
        return out
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"ok": True, "raw": r.text[:2000]}


def _is_err(res: Any) -> bool:
    return isinstance(res, dict) and res.get("error") is True


# --------------------------------------------------------------------------- #
# Orientation / status
# --------------------------------------------------------------------------- #

@mcp.tool()
async def studio_overview() -> dict:
    """START HERE. What this MACU Studio instance contains (shows, episode counts,
    macu-web connection) plus the step-by-step workflow guide for producing an
    episode. Call this first if you're unsure what to do."""
    shows = await _api("GET", "/api/shows")
    out: dict[str, Any] = {"workflow_guide": WORKFLOW_GUIDE}
    if _is_err(shows):
        return {**shows, **out}
    listing = []
    for s in shows.get("shows", []):
        sid = s.get("id")
        eps = await _api("GET", "/api/episodes", params={"show": sid})
        slugs = [e.get("slug") for e in eps.get("episodes", [])] if not _is_err(eps) else []
        listing.append({"id": sid, "name": s.get("name"), "episodes": slugs})
    out["shows"] = listing
    out["default_show"] = shows.get("default")
    web = await _api("GET", "/api/macu-web/status")
    out["macu_web"] = web if not _is_err(web) else {"connected": False}
    return out


@mcp.tool()
async def studio_status() -> dict:
    """Live status: server health, CPU/GPU utilization, what's currently rendering
    or generating, and the render-job queue. Check this before run_pipeline or any
    generate_* call (they 409 when the GPU is busy)."""
    health = await _api("GET", "/api/health")
    sysstat = await _api("GET", "/api/sysstat")
    activity = await _api("GET", "/api/activity")
    agen = await _api("GET", "/api/agen/status")
    jobs = await _api("GET", "/api/jobs")
    return {"health": health, "sysstat": sysstat, "activity": activity,
            "gpu": agen, "render_jobs": jobs}


# --------------------------------------------------------------------------- #
# Shows / episodes
# --------------------------------------------------------------------------- #

@mcp.tool()
async def list_shows() -> dict:
    """All shows registered in this Studio, plus the default show id."""
    return await _api("GET", "/api/shows")


@mcp.tool()
async def create_show(id: str, name: str) -> dict:
    """Register a new show. `id` is a lowercase-kebab identifier (e.g.
    'as-the-world-burns'); `name` is the display title. Episodes are then created
    under it with create_episode."""
    return await _api("POST", "/api/shows", body={"id": id, "name": name})


@mcp.tool()
async def list_episodes(show: str = "") -> dict:
    """Episodes of one show (default show when omitted). Each row has slug, title,
    and render state. Use the slug for every other episode tool."""
    params = {"show": show} if show else None
    return await _api("GET", "/api/episodes", params=params)


@mcp.tool()
async def create_episode(show: str, slug: str, title: str = "") -> dict:
    """Create a new episode under `show`. `slug` is the episode's id-on-disk
    (lowercase-kebab, e.g. 'awb-002'). Seeds the dir + a starter manifest from the
    show's defaults. Next step: write_script(slug, ...)."""
    return await _api("POST", f"/api/shows/{show}/episodes",
                      body={"slug": slug, "title": title})


@mcp.tool()
async def get_episode(slug: str) -> dict:
    """One episode at a glance: pipeline stage status (which render stages are
    cached/stale), final-video info, whether a script exists, and the manifest's
    cue/shot/title counts. Cheaper than read_manifest for orientation."""
    stages = await _api("GET", f"/api/episodes/{slug}/pipeline")
    final = await _api("GET", f"/api/episodes/{slug}/final")
    script = await _api("GET", f"/api/episodes/{slug}/script")
    man = await _api("GET", f"/api/episodes/{slug}/manifest")
    out: dict[str, Any] = {"slug": slug, "stages": stages, "final": final}
    if not _is_err(script):
        out["script"] = {"exists": script.get("exists"),
                         "chars": len(script.get("text") or "")}
    if _is_err(man):
        return {**man, **out}
    _wf = (man.get("comfyui") or {}).get("workflow")
    out["manifest_summary"] = {
        "title": man.get("title"), "show": man.get("show"),
        "cues": len(man.get("cues") or []),
        "masters_backend": "wan_i2v" if _wf == "wan21_i2v" else "zeroscope",
        "characters": sorted((man.get("characters") or {}).keys()),
        "title_assets": sorted((man.get("title_assets") or {}).keys()),
        "sfx": len(man.get("sfx") or []),
        "music_clips": len((man.get("music") or {}).get("clips") or []),
        "youtube_video_id": (man.get("youtube") or {}).get("video_id"),
        "published": bool(man.get("published")),
    }
    active = await _api("GET", f"/api/episodes/{slug}/pipeline/active")
    out["active_render_job"] = (active or {}).get("job_id")
    return out


# --------------------------------------------------------------------------- #
# Script / manifest
# --------------------------------------------------------------------------- #

@mcp.tool()
async def read_script(slug: str) -> dict:
    """The episode's script.md — the human-editable writing surface the manifest's
    cues are generated from."""
    return await _api("GET", f"/api/episodes/{slug}/script")


@mcp.tool()
async def write_script(slug: str, text: str) -> dict:
    """Replace script.md wholesale (atomic write). Format: '## SEGMENT' headers,
    '**SPEAKER:** dialogue' cue lines, optional '» shot → shot' lines per cue (see
    studio_overview's guide). After writing, run manifest_from_script to turn the
    script into render cues. Consider git_sync(slug, message='<slug> vN') after
    each meaningful revision so versions stay reviewable."""
    return await _api("PUT", f"/api/episodes/{slug}/script", text=text)


@mcp.tool()
async def read_manifest(slug: str) -> dict:
    """The full manifest.json — the episode's render plan (cues, characters, shots,
    music, sfx, voice map, title assets...). Large; prefer get_episode for a
    summary."""
    return await _api("GET", f"/api/episodes/{slug}/manifest")


@mcp.tool()
async def write_manifest(slug: str, manifest_json: str) -> dict:
    """Replace the manifest wholesale. `manifest_json` is the FULL manifest as a
    JSON string — read_manifest first, modify, pass the whole thing back. The save
    re-validates and snapshots a .bak. Prefer purpose-built tools (set_episode_meta,
    set_speaker_voice, generate_* with apply) over hand-editing where possible."""
    try:
        m = json.loads(manifest_json)
    except json.JSONDecodeError as e:
        return {"error": True, "detail": f"manifest_json is not valid JSON: {e}",
                "hint": "Pass the complete manifest object serialized as a JSON string."}
    if not isinstance(m, dict):
        return {"error": True, "detail": "manifest_json must encode a JSON object"}
    return await _api("PUT", f"/api/episodes/{slug}/manifest", body=m)


@mcp.tool()
async def manifest_from_script(slug: str, apply: bool = False) -> dict:
    """Regenerate manifest.cues from script.md (merging — voices/shots/music etc.
    are preserved). DRY RUN by default: returns {summary, cues} for review. Call
    again with apply=true to write (a timestamped manifest backup is taken)."""
    return await _api("POST", f"/api/episodes/{slug}/manifest/from-script",
                      body={"apply": bool(apply)})


# --------------------------------------------------------------------------- #
# LLM generation (local Ollama — dry-run by default, one-call apply for agents)
# --------------------------------------------------------------------------- #

@mcp.tool()
async def generate_shots(slug: str, only_missing: bool = True, apply: bool = False) -> dict:
    """Ask the local LLM to plan the episode's shot list (reuse existing characters/
    b-roll vs mint new ones, per-cue shots). only_missing=true (the safe default)
    plans ONLY cues that have no shots yet, so tuned cues are never clobbered.
    DRY RUN unless apply=true, which writes the proposal straight into the
    manifest. Takes a minute+ (model load); 409 if the GPU is busy."""
    prop = await _api("POST", f"/api/episodes/{slug}/shots/generate",
                      body={"only_missing": bool(only_missing)})
    if _is_err(prop) or not apply:
        return prop
    applied = await _api("POST", f"/api/episodes/{slug}/shots/apply",
                         body={"proposal": prop})
    return {"proposal": prop, "applied": applied}


@mcp.tool()
async def apply_shots(slug: str, proposal_json: str) -> dict:
    """Apply an (optionally hand-edited) shot proposal from generate_shots. Pass
    the proposal object back as a JSON string. Use this instead of
    generate_shots(apply=true) when you've reviewed/edited the proposal."""
    try:
        prop = json.loads(proposal_json)
    except json.JSONDecodeError as e:
        return {"error": True, "detail": f"proposal_json is not valid JSON: {e}"}
    return await _api("POST", f"/api/episodes/{slug}/shots/apply",
                      body={"proposal": prop})


@mcp.tool()
async def generate_sfx(slug: str, apply: bool = False) -> dict:
    """Ask the local LLM to read the script as a radio play and propose sound-effect
    placements (favoring the existing SFX kit, flagging ones to acquire). DRY RUN
    unless apply=true. Takes a minute+; 409 if the GPU is busy."""
    prop = await _api("POST", f"/api/episodes/{slug}/sfx/generate")
    if _is_err(prop) or not apply:
        return prop
    applied = await _api("POST", f"/api/episodes/{slug}/sfx/apply",
                         body={"proposal": prop})
    return {"proposal": prop, "applied": applied}


@mcp.tool()
async def generate_card_text(slug: str, card_type: str, key: str = "",
                             apply: bool = False) -> dict:
    """Ask the local LLM to write title-card text fields (deadpan, lifting a real
    punchline from the script). card_type is one of GET /api/card-types — commonly
    'cold_open', 'segment_bumper', 'sponsor', 'youtube_thumb'. DRY RUN unless
    apply=true; when applying, `key` names the title_assets entry to write
    (ignored for youtube_thumb). Returns length warnings — headline fields
    overflow the card past ~22 chars, so trim before applying."""
    types = await _api("GET", "/api/card-types")
    valid = (types or {}).get("card_types") or []
    if valid and card_type not in valid:
        return {"error": True, "detail": f"unknown card_type '{card_type}'",
                "hint": f"Valid card types: {', '.join(valid)}"}
    prop = await _api("POST", f"/api/episodes/{slug}/card-text/generate",
                      body={"card_type": card_type})
    if _is_err(prop) or not apply:
        return prop
    applied = await _api("POST", f"/api/episodes/{slug}/card-text/apply",
                         body={"card_type": card_type, "key": key,
                               "fields": prop.get("fields") or {}})
    return {"proposal": prop, "applied": applied}


@mcp.tool()
async def render_title_cards(slug: str, key: str = "", only_missing: bool = False,
                             wait: bool = True) -> dict:
    """Render the episode's TITLE CARDS on their own — the HyperFrames-composited
    intro / bumper / lower-third cards — WITHOUT running the expensive video-masters
    stage they're normally rendered alongside. `key` renders a single title_assets
    entry; omit it to render every HyperFrames-rendered title. only_missing=true
    skips titles already rendered. Title-card TEXT is authored separately with
    generate_card_text — this just (re)renders the picture. Renders run one at a
    time and are quick; with wait=true (default) this blocks until they finish and
    returns each card's final state, with wait=false it returns the queued job ids
    immediately (poll get_episode to watch titles flip to 'rendered')."""
    body: dict[str, Any] = {}
    if key:
        body["key"] = key
    if only_missing:
        body["only_missing"] = True
    res = await _api("POST", f"/api/episodes/{slug}/titles/render", body=body)
    if _is_err(res):
        return res
    queued = res.get("queued") or []
    if not queued:
        return {"slug": slug, "rendered": [], "queued": [],
                "skipped": res.get("skipped") or [],
                "note": "no HyperFrames-rendered title cards"
                        + (" were missing" if only_missing else " to render")}
    if not wait:
        res["hint"] = "Renders queued. Poll each status_url, or call get_episode(slug) to watch titles flip to 'rendered'."
        return res
    # Serialized HF worker, fast renders — poll to completion with a safety cap.
    import asyncio
    rendered, failed, pending = [], [], []
    deadline = time.monotonic() + 25.0 * max(1, len(queued)) + 30.0
    remaining = {j["job_id"]: j["key"] for j in queued}
    while remaining and time.monotonic() < deadline:
        await asyncio.sleep(1.5)
        for jid in list(remaining):
            st = await _api("GET", f"/api/hf/jobs/{jid}")
            state = (st or {}).get("state")
            if state == "done":
                rendered.append(remaining.pop(jid))
            elif state == "error":
                tail = "; ".join(str(e) for e in (st.get("last_events") or [])[-3:])
                failed.append({"key": remaining.pop(jid), "detail": tail[:300]})
    pending = list(remaining.values())
    out = {"slug": slug, "rendered": sorted(rendered),
           "failed": failed, "skipped": res.get("skipped") or []}
    if pending:
        out["still_rendering"] = pending
        out["hint"] = "Some renders were still going past the wait window; call get_episode(slug) to confirm they finished."
    return out


@mcp.tool()
async def generate_stills(slug: str, only_missing: bool = True, who: str = "") -> dict:
    """Render the seed reference STILLS for an episode — the discrete 'stills before
    video' step. Each still (z-image / the routed stills engine) is what the WAN i2v
    masters backend animates, so shots stay on-model; runs independently of the video
    stage. Renders a still per character; under the wan_i2v backend it ALSO renders one
    per b-roll key (b-roll then animates from its still — no zeroscope). only_missing
    skips stills already fresh; `who` limits to one key. A character needs a still_prompt
    (set via upsert_character); b-roll uses its own scene prompt. Returns {rendered,
    skipped, failed, characters_seen, broll_seen}. Pair with set_masters_backend(slug,
    'wan_i2v')."""
    body: dict[str, Any] = {"only_missing": only_missing}
    if who:
        body["who"] = who
    return await _api("POST", f"/api/episodes/{slug}/stills/render", body=body)


@mcp.tool()
async def set_masters_backend(slug: str, backend: str) -> dict:
    """Choose how this episode renders its video masters: 'zeroscope' (text-to-video,
    the default — no seed still) or 'wan_i2v' (WAN image-to-video; BOTH character and
    b-roll shots animate from their stills/<key>.png — no zeroscope anywhere, so a
    clean WAN+z-image install renders the whole episode). Writes comfyui.workflow. For
    wan_i2v, run generate_stills first (it renders stills for every character AND b-roll
    key) and note the WAN render needs the --with-talking-head pack on the render box."""
    return await _api("POST", f"/api/episodes/{slug}/masters-backend",
                      body={"backend": backend})


# --------------------------------------------------------------------------- #
# Render pipeline
# --------------------------------------------------------------------------- #

@mcp.tool()
async def run_pipeline(slug: str, from_stage: int = 0, only: int = 0) -> dict:
    """Queue a full episode render (VO → video masters → interpolation → assembly →
    graphics → music → transcription → subtitles → burn). Stages are cached: an
    unchanged stage is skipped, so re-running after a small edit is cheap.
    from_stage=N re-runs from stage N; only=N runs just that stage; leave both 0
    for the normal cached full run. Returns immediately with a job_id — the render
    takes many minutes. Then await_render(slug, job_id=...) to BLOCK until a
    milestone (e.g. until='final'); render_status(job_id) is a one-shot snapshot."""
    body: dict[str, Any] = {}
    if from_stage and from_stage > 1:
        body["from_stage"] = int(from_stage)
    if only:
        body["only"] = int(only)
    res = await _api("POST", f"/api/episodes/{slug}/pipeline/run", body=body)
    if not _is_err(res):
        res.setdefault("hint", "Render queued. Poll render_status(job_id) every minute or two; a full episode typically takes 10-40 min.")
    return res


@mcp.tool()
async def render_status(job_id: str = "", slug: str = "") -> dict:
    """Render progress, ONE-SHOT (returns immediately). With job_id: that job's
    state + recent stage events. With slug: that episode's per-stage cache status +
    its active job id. With neither: the whole render-job queue. To WAIT for a
    stage instead of polling this in a loop, use await_render(slug, job_id)."""
    if job_id:
        return await _api("GET", f"/api/jobs/{job_id}")
    if slug:
        stages = await _api("GET", f"/api/episodes/{slug}/pipeline")
        active = await _api("GET", f"/api/episodes/{slug}/pipeline/active")
        return {"slug": slug, "stages": stages,
                "active_render_job": (active or {}).get("job_id")}
    return await _api("GET", "/api/jobs")


# Stage number for each `until=` alias await_render accepts (matches the 8-stage
# order in manifest.episode_pipeline_status: vo, masters, rife, assemble, music,
# whisper, srt, burn).
_AWAIT_STAGES = {"vo": 1, "masters": 2, "rife": 3, "assemble": 4, "music": 5,
                 "whisper": 6, "srt": 7, "subs": 7, "burn": 8, "final": 8}
_AWAIT_JOB_TERMINAL = {"done", "error", "abandoned", "cancelled", "failed"}


@mcp.tool()
async def await_render(slug: str, job_id: str = "", until: str = "final",
                       timeout_s: int = 600, interval_s: int = 15) -> dict:
    """BLOCK until a render reaches a milestone, then return — so you can *await* a
    checkpoint instead of looping on render_status and burning context between
    polls. Resolves the moment the target stage flips to done/error, OR the whole
    job terminates, OR timeout_s elapses. After run_pipeline, prefer this over
    manual polling.

    `until` is a stage number 1-8 or an alias: vo(1), masters(2), rife(3),
    assemble(4), music(5), whisper(6), srt/subs(7), burn/final(8). Pass job_id
    (from run_pipeline) so a crash/cancel wakes you too; omit it to await purely on
    on-disk stage status.

    Returns {reached, reason, stage, stage_status, stage_note, job_state, stages}.
    reason is 'stage:done'/'stage:error', 'job:<state>', or 'timeout'. On 'timeout'
    the render is still going — just call await_render again to keep waiting (it's
    idempotent, re-reads live state each call). Note the masters stage reads 'idle'
    until shot 1's file lands even though ComfyUI is already crunching."""
    try:
        target = _AWAIT_STAGES.get(until.strip().lower()) or int(until)
    except (ValueError, TypeError):
        return {"error": True,
                "detail": f"until must be a stage 1-8 or one of {sorted(_AWAIT_STAGES)}"}
    if not 1 <= target <= 8:
        return {"error": True, "detail": "until stage must be 1..8"}
    interval = max(5, min(int(interval_s), 60))
    deadline = time.monotonic() + max(10, min(int(timeout_s), 1800))
    while True:
        stages = await _api("GET", f"/api/episodes/{slug}/pipeline")
        if _is_err(stages):
            return stages
        rows = stages.get("stages") if isinstance(stages, dict) else stages
        st = next((s for s in (rows or []) if s.get("n") == target), {})
        job_state = None
        if job_id:
            job = await _api("GET", f"/api/jobs/{job_id}")
            if not _is_err(job):
                inner = job.get("job") if isinstance(job.get("job"), dict) else job
                job_state = inner.get("state") if isinstance(inner, dict) else None
        snap = {"stage": target, "stage_status": st.get("status"),
                "stage_note": st.get("note"), "job_state": job_state, "stages": rows}
        if st.get("status") in ("done", "error"):
            return {"reached": True, "reason": f"stage:{st.get('status')}", **snap}
        if job_state in _AWAIT_JOB_TERMINAL:
            return {"reached": job_state == "done", "reason": f"job:{job_state}", **snap}
        if time.monotonic() >= deadline:
            return {"reached": False, "reason": "timeout", **snap}
        await asyncio.sleep(interval)


@mcp.tool()
async def regen_asset(slug: str, kind: str, key: str) -> dict:
    """Re-render ONE asset without touching the rest: kind='cue' regenerates a
    voice line (key=cue id, e.g. 'c07'), kind='shot' re-renders a video shot
    (key=shot key), kind='title' re-renders a title card (key=title_assets key;
    returns an async job_id). The next run_pipeline picks the new take up."""
    if kind == "cue":
        return await _api("POST", f"/api/episodes/{slug}/cue/{key}/regen")
    if kind == "shot":
        return await _api("POST", f"/api/episodes/{slug}/shot/{key}/regen")
    if kind == "title":
        return await _api("POST", f"/api/episodes/{slug}/title/{key}/regen")
    return {"error": True, "detail": f"unknown kind '{kind}'",
            "hint": "kind must be one of: cue, shot, title"}


@mcp.tool()
async def emergency_stop() -> dict:
    """Kill the active render, clear the GPU queue, and stop the on-demand GPU
    containers. Destructive to in-flight work — use only when a render is stuck or
    the user asks to stop everything."""
    return await _api("POST", "/api/emergency-stop")


# --------------------------------------------------------------------------- #
# Voices
# --------------------------------------------------------------------------- #

@mcp.tool()
async def list_voices() -> dict:
    """Cloned voice profiles available for casting (OmniVoice), with profile ids."""
    return await _api("GET", "/api/voices")


@mcp.tool()
async def set_speaker_voice(slug: str, speaker: str, profile_id: str = "",
                            voice_name: str = "") -> dict:
    """Cast a speaker: map a script SPEAKER name to a cloned voice profile (see
    list_voices). Empty profile_id CLEARS the mapping so the speaker falls back to
    the default robot/HAL voice. Also updates the show's defaults so future
    episodes inherit the casting. Only that speaker's cues re-render next run."""
    body: dict[str, Any] = {"speaker": speaker}
    if profile_id:
        body.update({"engine": "omnivoice", "profile_id": profile_id})
        if voice_name:
            body["voice_name"] = voice_name
    else:
        body["engine"] = "default"
    return await _api("PUT", f"/api/episodes/{slug}/speaker-voice", body=body)


@mcp.tool()
async def start_voice_engine() -> dict:
    """Start OmniVoice (the TTS engine) and wait until it answers, then return the
    live voice roster. OmniVoice is consumer-lifecycle — stopped when idle so it
    doesn't hog GPU — so 'running: false' in engines_status / list_voices is normal;
    call this to bring it up before importing voices or validating a cast. Starting
    cold can take up to ~3 min."""
    return await _api("POST", "/api/voices/start")


@mcp.tool()
async def import_voices(zip_path: str = "", names: str = "", show: str = "") -> dict:
    """Load cloned voices into the LOCAL OmniVoice so episodes cast to them render
    correctly. `zip_path` is a server-local voices export (.zip of reference clips);
    omit it to (re)clone reference clips already on disk. `names` is an optional
    comma-separated subset. `show` rebinds that show's speaker_map entries (matched
    by the portable voice_name) to the freshly minted profile_ids — pass it so
    existing manifests resolve. Clones run one at a time on the GPU (slow for many
    voices); starts OmniVoice if needed. Returns {imported:{name:profile_id},
    rebound:{name:n}, failed:[...]}. Render also self-heals by voice_name, so even
    without `show` an imported voice resolves at VO time."""
    body: dict[str, Any] = {}
    if zip_path:
        body["zip_path"] = zip_path
    if names:
        body["names"] = [n.strip() for n in names.split(",") if n.strip()]
    if show:
        body["show"] = show
    return await _api("POST", "/api/voices/import", body=body)


@mcp.tool()
async def validate_cast(slug: str) -> dict:
    """Cast doctor — BEFORE a render, check every speaker the script uses against
    the running OmniVoice roster. Flags speakers whose voice resolves by neither
    profile_id nor voice_name (status 'missing' → would render a fallback voice;
    fix the cast or import_voices), distinguishes ones that will self-heal by name
    ('self_heal'), and notes speakers on the default robot voice. Catches the
    silent-fallback bug in ~1s instead of after a multi-minute render. If OmniVoice
    is stopped, start_voice_engine first for a live check."""
    return await _api("GET", f"/api/episodes/{slug}/cast/validate")


@mcp.tool()
async def preview_vo(slug: str, cue_id: str, wait: bool = True) -> dict:
    """Audition ONE cue's voiceover — re-render just that cue (drops its cached wav
    + queues stage 1) so you can check a voice without rendering all of an episode's
    lines. With wait=true (default) it blocks until the VO job finishes (seconds)
    and returns the cue's audio URL + state; wait=false returns the job id. Pair with
    set_speaker_voice / import_voices to dial in a voice fast."""
    res = await _api("POST", f"/api/episodes/{slug}/cue/{cue_id}/regen")
    if _is_err(res):
        return res
    job_id = res.get("job_id") or res.get("id")
    audio_url = f"/api/episodes/{slug}/cue/{cue_id}/audio"
    if not wait or not job_id:
        return {"slug": slug, "cue_id": cue_id, "job_id": job_id,
                "audio_url": audio_url, "queued": True}
    deadline = time.monotonic() + 90.0
    state = "running"
    while time.monotonic() < deadline:
        await asyncio.sleep(1.5)
        job = await _api("GET", f"/api/jobs/{job_id}")
        state = (job or {}).get("state") or state
        if state in ("done", "error", "failed"):
            break
    return {"slug": slug, "cue_id": cue_id, "job_id": job_id, "state": state,
            "audio_url": audio_url,
            "hint": "Fetch audio_url to hear it, or get_episode to see VO status."}


# --------------------------------------------------------------------------- #
# Versioning / publish
# --------------------------------------------------------------------------- #

@mcp.tool()
async def git_sync(slug: str, message: str = "") -> dict:
    """Commit + push the episode's text files (script.md / manifest.json /
    youtube.txt) to the repo's episode_meta/ path. Pass a message like
    'awb-002 v3 (writers' room)' so each script revision is its own reviewable
    commit."""
    return await _api("POST", f"/api/episodes/{slug}/git-sync",
                      body={"message": message} if message else {})


@mcp.tool()
async def set_episode_meta(slug: str, title: str = "", notes: str = "",
                           season: int = 0, episode_num: int = 0) -> dict:
    """Patch episode metadata used by the public site: title, notes (the episode
    description/synopsis), season, episode_num. Only the fields you pass non-empty/
    non-zero are touched."""
    body: dict[str, Any] = {}
    if title:
        body["title"] = title
    if notes:
        body["notes"] = notes
    if season:
        body["season"] = season
    if episode_num:
        body["episode_num"] = episode_num
    if not body:
        return {"error": True, "detail": "nothing to set",
                "hint": "Pass at least one of title, notes, season, episode_num."}
    return await _api("POST", f"/api/episodes/{slug}/macu-web/meta", body=body)


@mcp.tool()
async def set_episode_youtube(slug: str, video_id: str) -> dict:
    """Record the episode's YouTube video id (bare id or full URL — it's parsed)
    in the manifest, driving the macu-web embed after the next publish_show. Pass
    an empty string to clear it."""
    return await _api("POST", f"/api/episodes/{slug}/macu-web/youtube",
                      body={"video_id": video_id})


@mcp.tool()
async def set_episode_published(slug: str, published: bool) -> dict:
    """Set the episode's published flag: true → shown on the public macu-web site
    after the next publish_show; false → pushed but hidden draft. This is per-
    episode; making a whole SHOW public is owner-only in the macu-web UI."""
    return await _api("POST", f"/api/episodes/{slug}/macu-web/published",
                      body={"published": bool(published)})


@mcp.tool()
async def publish_show(show: str, message: str = "", allow_new_public: list[str] | None = None) -> dict:
    """Push the show's episode bundle to the connected macu-web site (git push +
    reindex). Episodes appear publicly only if their published flag is set AND the
    show itself is public (an owner-only toggle on the site). Check
    studio_overview's macu_web.connected first — publishing needs a one-time
    connect token from the site's Manage page.

    Episodes the repo has never published whose manifest already says published:true
    are HELD BACK (they would seed PUBLIC on the site's first index). Pass their slugs
    in allow_new_public to ship them deliberately; check `skipped_new_episodes` and
    `warnings` in the response."""
    body: dict = {}
    if message:
        body["message"] = message
    if allow_new_public:
        body["allow_new_public"] = list(allow_new_public)
    return await _api("POST", f"/api/shows/{show}/publish", body=body)


# ---- Higgsfield (cloud video generation) ------------------------------------

@mcp.tool()
async def higgsfield_status() -> dict:
    """Higgsfield.ai connection state, subscription plan, and remaining credits.
    Cloud shots (kind 'higgsfield'/'lipsync') need this connected — the user
    connects once in Settings -> Higgsfield (OAuth; cannot be done over MCP)."""
    return await _api("GET", "/api/higgsfield/auth")


@mcp.tool()
async def higgsfield_models(refresh: bool = False) -> dict:
    """The Higgsfield model catalog (video + image + audio) with per-model
    parameters, durations, and aspect ratios. Disk-cached 24h; refresh=true
    forces a refetch. Video shots default to seedance_2_0; lipsync shots need a
    model whose medias accept an 'audio' role (seedance_2_0, wan2_7)."""
    return await _api("GET", "/api/higgsfield/models", params={"refresh": str(refresh).lower()})


@mcp.tool()
async def estimate_episode_cost(slug: str) -> dict:
    """Credit cost of rendering the episode's NON-CACHED Higgsfield shots, plus
    current balance and a tri-state `sufficient` verdict (null = some costs or
    the balance are unknown). Cached shots are free; crop/trim edits never
    re-bill. ALWAYS show this to the user before run_pipeline on an episode
    with cloud shots."""
    return await _api("GET", f"/api/episodes/{slug}/higgsfield/estimate")


@mcp.tool()
async def set_shot_provider(slug: str, cue_id: str, shot_id: str, kind: str,
                            model: str = "", prompt: str = "", who: str = "",
                            source_still: str = "", duration: int = 0) -> dict:
    """Convert (or create) one shot in a cue to a given provider kind:
    'character'/'broll' (local zeroscope), 'higgsfield' (cloud t2v/i2v), or
    'lipsync' (cloud, audio-driven by the cue's VO; must be the FIRST shot in
    its cue, max one per cue — cutaways may follow it). Optional fields apply to
    cloud kinds: model (default from the
    manifest's higgsfield block), prompt (default: who's core prompt +
    style_suffix), source_still (character key or episode-relative path ->
    image-to-video), duration (seconds, higgsfield kind only)."""
    mres = await _api("GET", f"/api/episodes/{slug}/manifest")
    if _is_err(mres):
        return mres
    m = mres.get("manifest") or mres
    cue = next((c for c in (m.get("cues") or []) if c.get("id") == cue_id), None)
    if cue is None:
        return {"error": True, "detail": f"unknown cue {cue_id}",
                "hint": "read_manifest and check cues[].id"}
    shots = cue.get("shots") or []
    shot = next((s for s in shots if s.get("id") == shot_id), None)
    if shot is None:
        shot = {"id": shot_id}
        shots.append(shot)
    shot["kind"] = kind
    for k, v in (("model", model), ("prompt", prompt), ("who", who),
                 ("source_still", source_still)):
        if v:
            shot[k] = v
    if duration:
        shot["duration"] = duration
    if kind == "lipsync":
        # the validator rejects siblings; make the intent explicit instead of 400ing
        cue["shots"] = [shot]
    else:
        cue["shots"] = shots
    return await _api("PUT", f"/api/episodes/{slug}/cue-shots",
                      body={"cues": {cue_id: cue["shots"]}})


@mcp.tool()
async def generate_cloud_shot(slug: str, shot_id: str) -> dict:
    """Force-regenerate ONE Higgsfield cloud shot (drops its cache + clip, queues
    stage 2 — only this clip re-bills; everything cached is skipped). This SPENDS
    CREDITS: call estimate_episode_cost first and confirm with the user. Returns
    the render job; poll render_status(job_id)."""
    return await _api("POST", f"/api/episodes/{slug}/shot/{shot_id}/higgsfield/regen")


@mcp.tool()
async def generate_character_still(slug: str, who: str) -> dict:
    """(Re)generate an EPISODE character's still via the routed stills engine
    (local Z-Image / Higgsfield / remote — see engines_status; uses
    characters[who].still_prompt; async). Prefer the show-level library
    (generate_character_takes + use_character_in_episode) for reusable cast —
    this regenerates one episode's still in place."""
    return await _api("POST", f"/api/episodes/{slug}/characters/{who}/still/regen")


# ---- Character library + engines ---------------------------------------------

@mcp.tool()
async def list_characters(show: str) -> dict:
    """The show's character library roster (key, name, tags, take count). The
    library is show-level — episodes pull characters in via
    use_character_in_episode."""
    return await _api("GET", f"/api/shows/{show}/characters")


@mcp.tool()
async def get_character(show: str, key: str) -> dict:
    """Full character record: prompts, takes, default take, and any running
    generation job. Each take carries `url` + `thumb_url` (fetchable image — absolute
    if MACU_STUDIO_PUBLIC_URL is set, else relative to this Studio's host) and `path`
    (local file) plus engine/model/seed provenance, so a headless client can pull the
    image to preview takes for selection. Top-level `default_take_url` too."""
    return await _api("GET", f"/api/shows/{show}/characters/{key}")


@mcp.tool()
async def upsert_character(show: str, key: str, name: str = "", core: str = "",
                           still_prompt: str = "", voice_hint: str = "",
                           seed: int = 0) -> dict:
    """Create or update a library character. core = the video prompt base;
    still_prompt = the reference-image prompt (used by generate_character_takes)."""
    fields = {k: v for k, v in (("name", name), ("core", core),
              ("still_prompt", still_prompt), ("voice_hint", voice_hint)) if v}
    if seed:
        fields["seed"] = seed
    r = await _api("POST", f"/api/shows/{show}/characters", body={"key": key, **fields})
    if isinstance(r, dict) and r.get("status") == 409:
        r = await _api("PUT", f"/api/shows/{show}/characters/{key}", body=fields)
    return r


@mcp.tool()
async def generate_character_takes(show: str, key: str, engine: str = "",
                                   count: int = 1, prompt: str = "",
                                   seed: int = 0) -> dict:
    """Generate 1-4 reference-still takes for a library character. engine:
    comfy_zimage (local, free) | higgsfield (SPENDS CREDITS) | remote_render;
    empty = the routed default (Settings → Engines). Async — poll
    character_take_status."""
    body: dict = {"count": count}
    if engine:
        body["engine"] = engine
    if prompt:
        body["prompt"] = prompt
    if seed:
        body["seed"] = seed
    return await _api("POST", f"/api/shows/{show}/characters/{key}/generate", body=body)


@mcp.tool()
async def character_take_status(show: str, key: str) -> dict:
    """Generation job state + the character's takes list (each take carries a
    fetchable `url`/`thumb_url` + local `path` — pull these to preview takes)."""
    return await _api("GET", f"/api/shows/{show}/characters/{key}/generate/status")


@mcp.tool()
async def set_default_take(show: str, key: str, take: str) -> dict:
    """Pick which take is the character's default reference still."""
    return await _api("POST", f"/api/shows/{show}/characters/{key}/takes/{take}/default")


@mcp.tool()
async def use_character_in_episode(show: str, key: str, slug: str, take: str = "",
                                   overwrite_still: bool = False) -> dict:
    """Copy a library take into an episode (stills/<key>.png + manifest entry +
    freshness stamp, so nothing re-bills). Returns needs_confirm when a
    different episode still exists (pass overwrite_still=true to replace) and
    `invalidates` listing cached PAID cloud shots the replacement would mark
    stale — surface that to the user before confirming."""
    body: dict = {"slug": slug, "overwrite_still": overwrite_still}
    if take:
        body["take"] = take
    return await _api("POST", f"/api/shows/{show}/characters/{key}/use", body=body)


@mcp.tool()
async def engines_status() -> dict:
    """Engine routing config (which service handles masters / stills / cloud
    video / lipsync) + live reachability probes."""
    cfg = await _api("GET", "/api/engines")
    probe = await _api("GET", "/api/engines/probe")
    return {"config": cfg, "probe": probe}


@mcp.tool()
async def set_engine_route(capability: str, engine: str) -> dict:
    """Route a capability (masters|stills|cloud_video|lipsync) to an engine.
    Allowed engines per capability come from engines_status capabilities."""
    return await _api("PUT", "/api/engines", body={"routing": {capability: engine}})


@mcp.tool()
async def studio_sync_plan(show: str) -> dict:
    """What a Studio↔Studio sync would do for this show: per-file push / pull /
    conflict lists (working text only — scripts, manifests, docs, character
    records — travelling through the show's macu-web repo, which both Studios
    must be connected to). Read-only."""
    return await _api("GET", f"/api/shows/{show}/sync/plan")


@mcp.tool()
async def studio_sync_apply(show: str, message: str = "") -> dict:
    """Execute the sync plan: pull remote-changed text into this Studio (locally
    overwritten files get timestamped .bak backups), push locally-changed text,
    conflicts resolve newest-wins. Show the user studio_sync_plan first when the
    direction of changes matters."""
    body = {"message": message} if message else {}
    return await _api("POST", f"/api/shows/{show}/sync/apply", body=body)


# --------------------------------------------------------------------------- #
# CoWork ↔ Studio job-board (SSA-133/137)
#
# The job store + REST CRUD are Leo's (cowork_jobs.py / routes_cowork.py); these
# are the cowork_* MCP tools CoWork drives, plus the placement-on-done seam.
# No per-tool auth — same trust model as the rest of Studio's MCP (the whole :8774
# surface is unauthenticated, including render/billing tools); the boundary is the
# LAN-only bind. Do NOT tunnel :8774/mcp publicly.
# --------------------------------------------------------------------------- #

async def _place_generation(job: dict) -> None:
    """Drop a finished job's harvested generation into its episode target, reusing
    the SSA-132 placement routes (so the same provenance stamping applies). Target
    is '<type>:<id>' — video/shot → the cloud clip; still/character|broll → the seed
    still. Soul jobs carry no media (the soul_id is server-side) so there's nothing
    to place."""
    gen_ids = job.get("result_gen_ids") or []
    if not gen_ids:
        return
    gid = gen_ids[0]
    episode = job.get("episode") or ""
    kind = job.get("kind")
    ttype, _, tid = (job.get("target") or "").partition(":")
    if not (episode and tid):
        return
    if kind == "video" or ttype == "shot":
        await _api("POST", f"/api/episodes/{episode}/shot/{tid}/import-generation", body={"gen_id": gid})
    elif kind == "still" or ttype in ("character", "broll"):
        await _api("POST", f"/api/episodes/{episode}/still/{tid}/import-generation", body={"gen_id": gid})


def _on_job_done(job: dict) -> None:
    """Done-hook (R2): fires once when a job transitions to "done", whether via the
    cowork_job_update tool OR a raw REST PATCH — one wiring covers both. Schedules
    the async placement onto the running server loop; best-effort by contract."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no event loop (e.g. a CLI mutation) — placement only runs in-server
    loop.create_task(_place_generation(job))


# Wire placement to the store seam at import (attach() runs before any job completes,
# so _api has the app by the time the hook fires).
cowork_jobs.set_done_hook(_on_job_done)


@mcp.tool()
async def cowork_jobs_list(status: str = "pending", episode: str = "",
                           kind: str = "") -> dict:
    """List browser-generation jobs from the CoWork job-board (oldest-first).
    status/episode/kind filter (status="" = all)."""
    jobs = cowork_jobs.list_jobs(episode=episode or None, status=status or None, kind=kind or None)
    return {"jobs": jobs, "count": len(jobs), "stats": cowork_jobs.stats(episode=episode or None)}


@mcp.tool()
async def cowork_job_claim(episode: str = "", kinds: list[str] | None = None,
                           by: str = "cowork") -> dict:
    """Atomically claim the oldest pending job (→ "claimed") so CoWork can work it
    without racing. Optionally filter by episode / kinds. Returns the job, or
    {job: null} if the queue is empty."""
    job = cowork_jobs.claim_next(episode=episode or None, kinds=kinds or None, by=by or "cowork")
    return {"job": job}


@mcp.tool()
async def cowork_job_update(id: str, status: str = "",
                            result_gen_ids: list[str] | None = None, note: str = "",
                            error: str = "", result_json: str = "") -> dict:
    """Report progress on a CoWork job. Set status (claimed|in_progress|done|failed|
    skipped) and, when done, the Higgsfield result_gen_ids you generated — Studio
    auto-harvests them into the job's episode target on the done transition. result_json
    is an optional JSON object merged into the job's freeform result (e.g. {"soul_id":..})."""
    result = None
    if result_json.strip():
        try:
            result = json.loads(result_json)
        except Exception as e:  # noqa: BLE001
            return {"error": True, "detail": f"result_json is not valid JSON: {e}"}
    try:
        job = cowork_jobs.update_job(
            id, status=status or None, result_gen_ids=result_gen_ids,
            result=result, note=note or None, error=error or None)
    except KeyError:
        return {"error": True, "detail": f"unknown job id {id}"}
    except ValueError as e:
        return {"error": True, "detail": str(e)}
    return {"job": job}


@mcp.tool()
async def cowork_jobs_create(episode: str, jobs_json: str) -> dict:
    """Queue browser-generation jobs for CoWork to execute. jobs_json is a JSON array
    of {kind: still|video|soul, target: "<type>:<id>", prompt?, model?, params?, note?}.
    All-or-nothing validation. Mostly Leo/August queue work this way; CoWork lists +
    claims + updates."""
    try:
        items = json.loads(jobs_json)
        if not isinstance(items, list):
            raise ValueError("jobs_json must be a JSON array")
    except Exception as e:  # noqa: BLE001
        return {"error": True, "detail": f"jobs_json invalid: {e}"}
    try:
        created = cowork_jobs.bulk_create(episode, items)
    except (ValueError, KeyError) as e:
        return {"error": True, "detail": str(e)}
    return {"created": created, "count": len(created)}


@mcp.tool()
async def cowork_job_complete(id: str, gen_ids: list[str], note: str = "") -> dict:
    """One-call completion for the CoWork harvest skill: mark a job done AND attach
    the Higgsfield generation id(s) you just made, in a single step. Studio then
    auto-harvests the result into the job's episode target. gen_ids are HIGGSFIELD
    GENERATION IDs (from the account history) — NOT media URLs; placement fetches
    each generation's rawUrl by id. Sugar over cowork_job_update(status="done", ...)."""
    if not gen_ids:
        return {"error": True, "detail": "gen_ids required — the Higgsfield generation id(s) "
                "you just made (see cowork_recent_generations)"}
    try:
        job = cowork_jobs.update_job(id, status="done", result_gen_ids=gen_ids,
                                     note=note or None)
    except KeyError:
        return {"error": True, "detail": f"unknown job id {id}"}
    return {"job": job, "harvesting": True}


@mcp.tool()
async def cowork_recent_generations(type: str = "", limit: int = 10) -> dict:
    """Find the generation you just made in the Higgsfield web app, so you can report
    its id back via cowork_job_complete. Returns the account's most-recent generations
    (newest first; web- AND API-made), trimmed to {id, type, model, prompt, thumb_url,
    created_at}. type=image|video narrows it. The `id` is what goes in gen_ids."""
    res = await _api("GET", "/api/higgsfield/generations",
                     params={"type": type, "size": max(1, min(50, limit))} if type
                     else {"size": max(1, min(50, limit))})
    if _is_err(res):
        return res
    out = []
    for g in (res.get("items") or [])[:limit]:
        r = g.get("results") or {}
        out.append({"id": g.get("id"), "type": g.get("type"), "model": g.get("model"),
                    "prompt": (g.get("params") or {}).get("prompt"),
                    "thumb_url": r.get("thumbnailUrl") or r.get("minUrl") or r.get("rawUrl"),
                    "created_at": g.get("createdAt")})
    return {"generations": out, "count": len(out)}
