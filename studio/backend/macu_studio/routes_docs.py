"""Docs/canon editor routes (Feature G) — show-aware.

GET    /api/docs?show=<id>                 → list _common + show docs (each tagged scope)
GET    /api/docs/{name}?show=<id>&scope=…  → {name, scope, text}
PUT    /api/docs/{name}?show=<id>          → write {text, scope}; returns {ok, scope}

`scope` is "common" (shared pipeline docs) or "show" (per-show canon). On GET it
may be omitted to auto-resolve (show dir first, then _common). On PUT the client
passes the scope it got from the listing so the write lands in the right dir.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from . import docs

router = APIRouter()


@router.get("/api/docs")
def get_docs(show: str | None = None):
    try:
        return {"docs": docs.list_docs(show)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/docs/{name}")
def get_doc(name: str, show: str | None = None, scope: str | None = None):
    try:
        text = docs.read(name, show=show, scope=scope)
        return {"name": name, "scope": scope, "text": text}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.put("/api/docs/{name}")
def put_doc(name: str, show: str | None = None, body: dict = Body(...)):
    text = body.get("text")
    if not isinstance(text, str):
        raise HTTPException(400, "text required")
    scope = body.get("scope") or "show"
    try:
        summ = docs.write(name, text, show=show, scope=scope)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "scope": summ["scope"]}
