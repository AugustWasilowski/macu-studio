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

import json
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import activity as activity_mod
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
 7. generate_card_text(slug, card_type) [optional] -> title cards / YouTube thumb
 8. run_pipeline(slug)              -> queues the render; poll render_status(job_id)
 9. git_sync(slug)                  -> commit the episode's text files
10. set_episode_meta / set_episode_youtube / set_episode_published, then
    publish_show(show)              -> push to the connected macu-web site

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
  job_id immediately; renders take many minutes. Poll render_status(job_id).
- generate_* tools run a local LLM on the GPU and return 409 if a render is
  active — check studio_status first.
- All generate_* tools are DRY RUNS by default. Nothing is written until you call
  them with apply=true (or call the matching apply step). Review proposals with
  the user before applying when in doubt.
- write_manifest replaces the whole manifest: read_manifest first, modify, write
  back. Prefer the purpose-built tools (set_episode_meta, set_speaker_voice...)
  over hand-editing manifest JSON.
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
    out["manifest_summary"] = {
        "title": man.get("title"), "show": man.get("show"),
        "cues": len(man.get("cues") or []),
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
    takes many minutes. Poll render_status(job_id=...) for progress."""
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
    """Render progress. With job_id: that job's state + recent stage events. With
    slug: that episode's per-stage cache status + its active job id. With neither:
    the whole render-job queue."""
    if job_id:
        return await _api("GET", f"/api/jobs/{job_id}")
    if slug:
        stages = await _api("GET", f"/api/episodes/{slug}/pipeline")
        active = await _api("GET", f"/api/episodes/{slug}/pipeline/active")
        return {"slug": slug, "stages": stages,
                "active_render_job": (active or {}).get("job_id")}
    return await _api("GET", "/api/jobs")


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
    'lipsync' (cloud, audio-driven by the cue's VO; must be the cue's ONLY
    shot). Optional fields apply to cloud kinds: model (default from the
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
