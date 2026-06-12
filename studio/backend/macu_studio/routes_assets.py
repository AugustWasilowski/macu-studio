"""Asset versioning + shot-creation routes.

Versioning (Feature B): browse [current + history] for cues/shots/ythumb and
promote an archived version back over the canonical file. Shot creation
(Feature D): add a character or b-roll key to the manifest from the Video page,
optionally attaching a shot to an existing cue.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from . import manifest as manifest_mod
from . import media
from . import regen
from . import versions

router = APIRouter()

_CTYPE = {"cue": "audio/wav", "shot": "image/webp", "ythumb": "image/png"}


@router.get("/api/episodes/{slug}/versions/{kind}/{key}")
def version_summary(slug: str, kind: str, key: str):
    if kind not in versions.KINDS:
        raise HTTPException(404, f"unknown kind: {kind}")
    return versions.summary(slug, kind, key)


@router.get("/api/episodes/{slug}/versions/{kind}/{key}/{v}/media")
def version_media(slug: str, kind: str, key: str, v: int, request: Request):
    if kind not in versions.KINDS:
        raise HTTPException(404, f"unknown kind: {kind}")
    f = versions.version_file(slug, kind, key, int(v))
    if f is None or not f.exists():
        raise HTTPException(404, f"version {v} not found for {kind}:{key}")
    return media.stream_file(request, f, content_type=_CTYPE[kind])


@router.post("/api/episodes/{slug}/versions/{kind}/{key}/promote")
def version_promote(slug: str, kind: str, key: str, body: dict = Body(...)):
    if kind not in versions.KINDS:
        raise HTTPException(404, f"unknown kind: {kind}")
    v = body.get("v")
    if v is None:
        raise HTTPException(400, "missing 'v'")
    target_meta = versions.version_meta(slug, kind, key, int(v))
    try:
        r = versions.promote(slug, kind, key, int(v))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    if kind == "cue":
        regen._drop_cue_from_vo_cache(slug, key)
    elif kind == "shot":
        # Restore the seed this version was rendered with so the manifest (and
        # the seed shown on the page) tracks the promoted master.
        seed = target_meta.get("seed")
        if seed is not None:
            m = manifest_mod.load(slug)
            chars = m.get("characters") or {}
            broll = m.get("broll") or {}
            if isinstance(chars.get(key), dict):
                chars[key]["seed"] = seed
                manifest_mod.save(slug, m)
            elif isinstance(broll.get(key), dict):
                broll[key]["seed"] = seed
                manifest_mod.save(slug, m)
    return r


# --- Feature D: add a shot (character / b-roll) from the Video page ----------
@router.post("/api/episodes/{slug}/shots/add")
def add_shot(slug: str, body: dict = Body(...)):
    key = (body.get("key") or "").strip()
    kind = body.get("kind")
    prompt = body.get("prompt") or ""
    seed = body.get("seed")
    attach_to_cue = body.get("attach_to_cue")
    if kind not in ("character", "broll", "higgsfield", "lipsync"):
        raise HTTPException(400, "kind must be character | broll | higgsfield | lipsync")

    m = manifest_mod.load(slug)

    # Cloud kinds are per-cue shots (each is a unique billed generation), not
    # reusable masters — they require a cue and mint their own shot id.
    if kind in ("higgsfield", "lipsync"):
        if not attach_to_cue:
            raise HTTPException(400, f"a {kind} shot must be attached to a cue")
        cue = next((c for c in (m.get("cues") or []) if c.get("id") == attach_to_cue), None)
        if cue is None:
            raise HTTPException(404, f"cue not found: {attach_to_cue}")
        shots = cue.setdefault("shots", [])
        shot: dict = {"id": f"{attach_to_cue}_s{len(shots) + 1}", "kind": kind}
        for field in ("model", "source_still", "who"):
            v = (body.get(field) or "").strip() if isinstance(body.get(field), str) else body.get(field)
            if v:
                shot[field] = v
        if prompt:
            shot["prompt"] = prompt
        if kind == "higgsfield" and body.get("duration"):
            shot["duration"] = int(body["duration"])
        if kind == "lipsync":
            # solo-per-cue invariant (validate() enforces it; replace explicitly
            # so the user's intent — "this cue becomes a lipsync shot" — wins)
            shot["id"] = f"{attach_to_cue}_s1"
            cue["shots"] = [shot]
        else:
            shots.append(shot)
        manifest_mod.save(slug, m)
        return {"ok": True, "key": shot["id"]}

    if not key:
        raise HTTPException(400, "missing 'key'")
    if kind == "character":
        m.setdefault("characters", {})[key] = {"seed": seed, "core": prompt}
    else:
        m.setdefault("broll", {})[key] = prompt

    if attach_to_cue:
        cue = next((c for c in (m.get("cues") or []) if c.get("id") == attach_to_cue), None)
        if cue is None:
            raise HTTPException(404, f"cue not found: {attach_to_cue}")
        shots = cue.setdefault("shots", [])
        shot = {"id": f"{attach_to_cue}_s{len(shots) + 1}", "kind": kind, "who": key}
        if kind == "character":
            shot["seed"] = seed
        shots.append(shot)

    manifest_mod.save(slug, m)
    return {"ok": True, "key": key}
