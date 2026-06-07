"""Localize routes — translate subtitles + dub an already-rendered episode into other
languages. Each requested language is enqueued as a dub job on the render queue
(run.py --dub), so progress streams over the existing /api/episodes/{slug}/pipeline SSE
(per job_id). Artifacts land at final/<slug>.<lang>.{srt,mp4}.
"""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from . import agen as agen_mod
from . import episodes as ep_mod
from . import pipeline as pipeline_mod

router = APIRouter()

ENGINES = [
    {"id": "qwen",
     "caveat": "Deadpan-aware, keeps character names; all languages. A bit slower (local LLM)."},
    {"id": "argos",
     "caveat": "Fast & literal (local NMT); flatter phrasing, does NOT preserve character names; major languages only."},
]

_LANG_RE = re.compile(r"^[a-zA-Z][a-zA-Z-]{1,8}$")


def _final_dir(slug: str):
    return ep_mod.episode_dir(slug) / "final"


def _rendered(slug: str) -> bool:
    """A dub needs a completed English render: the picture + the aligned SRT."""
    ep = ep_mod.episode_dir(slug)
    final = ep / "final" / f"{slug}.mp4"
    srt = ep / "final" / f"{slug}.srt"
    pic = ep / ".work" / f"{slug}_music_nosubs.mp4"
    pic2 = ep / ".work" / f"{slug}_nosubs.mp4"
    return final.exists() and srt.exists() and (pic.exists() or pic2.exists())


@router.get("/api/episodes/{slug}/localize")
def get_localize(slug: str):
    """State for the Localize modal: whether the English render exists, the engine
    options, and which languages already have artifacts on disk."""
    fdir = _final_dir(slug)
    langs = []
    if fdir.exists():
        seen = set()
        for f in fdir.iterdir():
            m = re.match(rf"^{re.escape(slug)}\.([a-zA-Z][a-zA-Z-]{{1,8}})\.(srt|mp4)$", f.name)
            # skip archived finals like <slug>.20260101-000000.mp4
            if not m or re.match(r"^\d", m.group(1)):
                continue
            seen.add(m.group(1))
        for code in sorted(seen):
            srt = fdir / f"{slug}.{code}.srt"
            mp4 = fdir / f"{slug}.{code}.mp4"
            langs.append({
                "code": code,
                "has_srt": srt.exists(),
                "has_mp4": mp4.exists(),
                "mtime": max((p.stat().st_mtime for p in (srt, mp4) if p.exists()), default=None),
            })
    return {"rendered": _rendered(slug), "engines": ENGINES, "languages": langs}


@router.post("/api/episodes/{slug}/localize")
async def post_localize(slug: str, body: dict = Body(...)):
    languages = body.get("languages") or []
    engine = body.get("engine") or "qwen"
    subs_only = bool(body.get("subs_only"))
    if engine not in ("qwen", "argos"):
        raise HTTPException(400, "engine must be 'qwen' or 'argos'")
    if not isinstance(languages, list) or not languages:
        raise HTTPException(400, "languages must be a non-empty list")
    langs = [str(c) for c in languages if _LANG_RE.match(str(c))]
    if not langs:
        raise HTTPException(400, "no valid language codes")
    if not _rendered(slug):
        raise HTTPException(409, "render the episode in English first (need the picture + subtitles)")
    # A render in flight would contend on the GPU; the queue serializes anyway, but
    # fail fast like the other gen routes so the user isn't left wondering.
    busy, free = agen_mod.gpu_busy()
    if busy:
        raise HTTPException(409, f"GPU busy ({free} MiB free) — a render is active; localize when idle")

    jobs = []
    for lang in langs:
        data = await pipeline_mod.submit(slug, dub={"lang": lang, "engine": engine, "subs_only": subs_only})
        jobs.append({"lang": lang, "job_id": data.get("job_id"),
                     "events_url": data.get("events_url")})
    return {"ok": True, "jobs": jobs}


def _serve(slug: str, lang: str, ext: str, media_type: str):
    if not _LANG_RE.match(lang):
        raise HTTPException(400, "invalid language")
    path = _final_dir(slug) / f"{slug}.{lang}.{ext}"
    if not path.exists():
        raise HTTPException(404, f"no {ext} for {slug}.{lang}")
    return FileResponse(str(path), media_type=media_type, filename=path.name)


@router.get("/api/episodes/{slug}/localize/{lang}/video")
def get_localize_video(slug: str, lang: str):
    return _serve(slug, lang, "mp4", "video/mp4")


@router.get("/api/episodes/{slug}/localize/{lang}/srt")
def get_localize_srt(slug: str, lang: str):
    return _serve(slug, lang, "srt", "application/x-subrip")
