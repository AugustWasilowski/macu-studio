"""Docs/canon editor routes (Feature G).

GET    /api/docs          → list *.md under <repo>/docs
GET    /api/docs/{name}   → {name, text}
PUT    /api/docs/{name}   → write {text}; returns {ok: True}
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from . import docs

router = APIRouter()


@router.get("/api/docs")
def get_docs():
    return {"docs": docs.list_docs()}


@router.get("/api/docs/{name}")
def get_doc(name: str):
    try:
        return {"name": name, "text": docs.read(name)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.put("/api/docs/{name}")
def put_doc(name: str, body: dict = Body(...)):
    text = body.get("text")
    if not isinstance(text, str):
        raise HTTPException(400, "text required")
    try:
        docs.write(name, text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
