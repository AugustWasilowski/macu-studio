"""ComfyUI workflow-graph registry.

Graph JSONs ship in the repo at pipeline/workflows/*.json: {meta, graph} where
meta.inputs maps a friendly param name to its [node, "inputs", field] path and
meta.defaults supplies fallbacks. bind() deep-copies the graph and applies
params, so callers never mutate the registry copy.

Dropping a new JSON in (e.g. wan21_infinitetalk.json from the Leo dump) is all
it takes to register a workflow — engines.py keys availability off file
presence.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

WORKFLOWS_DIR = REPO_ROOT / "pipeline" / "workflows"

_cache: dict[str, dict] = {}


def list_workflows() -> list[dict]:
    out = []
    if WORKFLOWS_DIR.exists():
        for p in sorted(WORKFLOWS_DIR.glob("*.json")):
            try:
                meta = json.loads(p.read_text()).get("meta") or {}
                out.append({"id": meta.get("id") or p.stem, "title": meta.get("title"),
                            "capability": meta.get("capability"),
                            "description": meta.get("description")})
            except Exception:
                continue
    return out


def load(workflow_id: str) -> dict:
    if workflow_id not in _cache:
        p = WORKFLOWS_DIR / f"{workflow_id}.json"
        if not p.exists():
            raise FileNotFoundError(f"unknown workflow '{workflow_id}' (no {p})")
        _cache[workflow_id] = json.loads(p.read_text())
    return _cache[workflow_id]


def bind(workflow_id: str, **params: Any) -> tuple[dict, dict]:
    """(graph, applied_params): deep-copied graph with meta.defaults + params
    applied along meta.inputs paths. seed=None → random 32-bit."""
    wf = load(workflow_id)
    meta = wf["meta"]
    graph = copy.deepcopy(wf["graph"])
    applied = dict(meta.get("defaults") or {})
    applied.update({k: v for k, v in params.items() if v is not None})
    if applied.get("seed") is None:
        applied["seed"] = random.randint(0, 2**32 - 1)
    for name, path in (meta.get("inputs") or {}).items():
        if name not in applied:
            continue
        node, key, field = path
        graph[str(node)][key][field] = applied[name]
    return graph, applied
