"""Engine routing — which service handles each pipeline capability.

Capabilities → engines:
  masters      → comfy_local                       (zeroscope stage 2)
  stills       → comfy_zimage | higgsfield | remote_render
  cloud_video  → higgsfield
  lipsync      → higgsfield  (+ local_wan, listed but unavailable until the
                 wan21_infinitetalk workflow JSON ships — install-only round)

Config lives at ~/.config/macu-studio/engines.json (atomic writes). Env vars win
over the file and are surfaced to the UI as `overridden` so the Settings tab can
badge pinned fields:
  MACU_ENGINE_COMFY_URL   (falls back to MACU_COMFY_URL for pipeline parity)
  MACU_ENGINE_REMOTE_URL
  MACU_ZIMAGE_UNET
  MACU_ROUTE_MASTERS / _STILLS / _CLOUD_VIDEO / _LIPSYNC
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from .config import REPO_ROOT

_CFG_PATH = Path.home() / ".config" / "macu-studio" / "engines.json"

# The unet the public installer fetches (Comfy-Org repack ships bf16 + nvfp4
# only; nvfp4 is 4.5 GB and proven on a 2080 Ti). Override via the Engines tab
# or MACU_ZIMAGE_UNET, e.g. to z_image_turbo_bf16.safetensors.
DEFAULT_ZIMAGE_UNET = "z_image_turbo_nvfp4.safetensors"

DEFAULTS: dict = {
    "version": 1,
    "endpoints": {
        "comfy_local": {"url": "http://127.0.0.1:8188", "zimage_unet": ""},
        "remote_render": {"url": "", "enabled": False},
    },
    "routing": {
        "masters": "comfy_local",
        "stills": "comfy_zimage",
        "cloud_video": "higgsfield",
        "lipsync": "higgsfield",
    },
}

WAN_WORKFLOW = REPO_ROOT / "pipeline" / "workflows" / "wan21_infinitetalk.json"


def _capabilities(cfg: dict) -> list[dict]:
    """Capability → allowed engines, with availability + reason for the UI."""
    remote_on = bool(_remote_url_of(cfg))
    return [
        {"id": "masters", "engines": [
            {"id": "comfy_local", "available": True},
        ]},
        {"id": "stills", "engines": [
            {"id": "comfy_zimage", "available": True},
            {"id": "higgsfield", "available": True},
            {"id": "remote_render", "available": remote_on,
             "reason": None if remote_on else "set + enable the remote render URL"},
        ]},
        {"id": "cloud_video", "engines": [
            {"id": "higgsfield", "available": True},
        ]},
        {"id": "lipsync", "engines": [
            {"id": "higgsfield", "available": True},
            {"id": "local_wan", "available": False,
             "reason": "coming soon — install with --with-talking-head"
                       if not WAN_WORKFLOW.exists()
                       else "workflow installed — pipeline wiring lands in a future update"},
        ]},
    ]


_ALLOWED = {
    "masters": {"comfy_local"},
    "stills": {"comfy_zimage", "higgsfield", "remote_render"},
    "cloud_video": {"higgsfield"},
    "lipsync": {"higgsfield"},  # local_wan intentionally not settable yet
}


# ---- config io ------------------------------------------------------------------

def _load_file() -> dict:
    if _CFG_PATH.exists():
        try:
            return json.loads(_CFG_PATH.read_text())
        except Exception:
            return {}
    return {}


def _deep_merge(base: dict, over: dict) -> dict:
    out = json.loads(json.dumps(base))
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env_overrides() -> tuple[dict, list[str]]:
    """(patch, overridden-field-paths) from the environment."""
    patch: dict = {"endpoints": {"comfy_local": {}, "remote_render": {}}, "routing": {}}
    over: list[str] = []
    comfy = os.environ.get("MACU_ENGINE_COMFY_URL", "").strip() \
        or os.environ.get("MACU_COMFY_URL", "").strip()
    if comfy:
        patch["endpoints"]["comfy_local"]["url"] = comfy.rstrip("/")
        over.append("endpoints.comfy_local.url")
    unet = os.environ.get("MACU_ZIMAGE_UNET", "").strip()
    if unet:
        patch["endpoints"]["comfy_local"]["zimage_unet"] = unet
        over.append("endpoints.comfy_local.zimage_unet")
    remote = os.environ.get("MACU_ENGINE_REMOTE_URL", "").strip()
    if remote:
        patch["endpoints"]["remote_render"]["url"] = remote.rstrip("/")
        patch["endpoints"]["remote_render"]["enabled"] = True
        over.append("endpoints.remote_render.url")
    for cap in ("masters", "stills", "cloud_video", "lipsync"):
        v = os.environ.get(f"MACU_ROUTE_{cap.upper()}", "").strip()
        if v:
            patch["routing"][cap] = v
            over.append(f"routing.{cap}")
    return patch, over


def _effective() -> dict:
    """Effective config: defaults ← file ← env (no derived fields)."""
    env_patch, _ = _env_overrides()
    return _deep_merge(_deep_merge(DEFAULTS, _load_file()), env_patch)


def _remote_url_of(cfg: dict) -> str:
    ep = cfg["endpoints"]["remote_render"]
    return ep["url"].rstrip("/") if ep.get("enabled") and ep.get("url") else ""


def get_config() -> dict:
    """Effective config + overridden paths + capability matrix (for the UI)."""
    _, overridden = _env_overrides()
    cfg = _effective()
    cfg["overridden"] = overridden
    cfg["capabilities"] = _capabilities(cfg)
    return cfg


def save_config(body: dict) -> dict:
    """Persist endpoints+routing (validated). Env overrides still win at read time."""
    cur = _deep_merge(DEFAULTS, _load_file())
    nxt = _deep_merge(cur, {k: body[k] for k in ("endpoints", "routing") if k in body})
    for cap, eng in (nxt.get("routing") or {}).items():
        if cap not in _ALLOWED:
            raise ValueError(f"unknown capability: {cap}")
        if eng not in _ALLOWED[cap]:
            raise ValueError(f"engine '{eng}' is not valid for {cap} "
                             f"(allowed: {', '.join(sorted(_ALLOWED[cap]))})")
    for name in ("comfy_local", "remote_render"):
        url = ((nxt.get("endpoints") or {}).get(name) or {}).get("url", "")
        if url and not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"{name} URL must start with http:// or https://")
        if url:
            nxt["endpoints"][name]["url"] = url.rstrip("/")
    _CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".engines.", suffix=".json.tmp", dir=_CFG_PATH.parent)
    with os.fdopen(fd, "w") as f:
        json.dump(nxt, f, indent=2)
    os.replace(tmp, _CFG_PATH)
    return get_config()


# ---- accessors -------------------------------------------------------------------

def route(capability: str) -> str:
    return _effective()["routing"].get(capability, DEFAULTS["routing"].get(capability, ""))


def comfy_url() -> str:
    return _effective()["endpoints"]["comfy_local"]["url"].rstrip("/")


def remote_url() -> str:
    return _remote_url_of(_effective())


def zimage_unet() -> str:
    return _effective()["endpoints"]["comfy_local"].get("zimage_unet") or DEFAULT_ZIMAGE_UNET


# ---- probes ------------------------------------------------------------------------

async def _probe_http(url: str, timeout: float = 1.5) -> dict:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url)
        return {"ok": True, "latency_ms": int((time.monotonic() - t0) * 1000),
                "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e) or e.__class__.__name__}


async def probe() -> dict:
    """Parallel liveness probes for the Settings Engines tab."""
    from . import higgsfield as hf  # late import: avoid module-load cycles

    cfg = get_config()
    tasks: dict[str, Any] = {
        "comfy_local": _probe_http(cfg["endpoints"]["comfy_local"]["url"] + "/system_stats"),
    }
    r_url = remote_url()
    if r_url:
        tasks["remote_render"] = _probe_http(r_url + "/")
    results = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values())))
    if not r_url:
        results["remote_render"] = {"ok": False, "disabled": True}

    hf_res: dict = {"ok": False, "connected": False}
    try:
        if hf.status()["connected"]:
            hf_res = {"ok": True, "connected": True}
            try:
                bal = await hf.balance()
                hf_res["credits"] = bal.get("credits")
                hf_res["plan"] = bal.get("subscription_plan_type")
            except Exception as e:
                hf_res = {"ok": False, "connected": True, "error": str(e)}
    except Exception as e:
        hf_res = {"ok": False, "error": str(e)}
    results["higgsfield"] = hf_res
    return results
