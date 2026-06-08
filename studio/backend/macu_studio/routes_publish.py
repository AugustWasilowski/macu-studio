"""Publish a show's text bundle to its macu-web (mayorawesome.com) git repo."""
from __future__ import annotations

from fastapi import APIRouter, Body

from . import publish as publish_mod

router = APIRouter()


@router.post("/api/shows/{show}/publish")
def post_publish(show: str, body: dict = Body(default={})):
    return publish_mod.publish(show, (body or {}).get("message"))
