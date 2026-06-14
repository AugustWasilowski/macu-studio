"""CoWork job board — the shared in-process store behind the SSA-133 workflow.

The CoWork↔Studio loop: a browser-capable agent (CoWork) generates ep assets in
the Higgsfield WEB app (free under the unlimited plan), while Studio/Leo harvest
the results via the API (free) and place them into the episode. This module is the
hand-off queue between the two halves.

Ownership (SSA-133 split, confirmed task 149/SSA-137):
- THIS module (store + create/list/update/claim) and its REST CRUD: Leo.
- The ``cowork_*`` MCP tools that import this module and call it directly,
  token auth, and **placement-on-done** (importing a finished job's result media
  into the episode via the SSA-132 import-generation path): Max. ``update_job``
  here is pure store mutation — it does NOT place anything. An optional
  ``set_done_hook`` seam (below) lets Max wire placement once so it fires whether
  a job is completed via the MCP tool or the raw REST PATCH.

Persistence: in-process dict mirrored to an atomic JSON file so a long-lived
browser worklist survives a Studio restart (the browser work it tracks does too).
Guarded by a re-entrant lock; REST handlers run in FastAPI's threadpool and the
MCP tools call in-process, so all mutations serialize through it.

No auth here, same as the rest of Studio — bind loopback / let Max's token gate
front it before any LAN/CoWork exposure. Do NOT expose the REST publicly unguarded.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# ---- schema --------------------------------------------------------------------

# A job is one unit of browser generation CoWork should perform (or has). Shape:
#   id              str    "j-" + 8 hex; assigned by create_job
#   episode         str    episode slug, e.g. "ep-022"
#   kind            str    KINDS — what to generate
#   target          str    where the result belongs, e.g. "character:ron",
#                          "broll:evidence_table", "shot:c01_s1", "soul:macu_ron".
#                          Free-form "<type>:<id>"; the placement layer (Max) parses it.
#   prompt          str    the generation prompt (style suffix already folded in)
#   model           str    requested web-app model, e.g. "nano_banana",
#                          "hailuo_2_3", "soul_v2" (free-form; advisory)
#   params          dict   extra knobs: seed, duration_s, input_still, negative,
#                          aspect_ratio, soul_id … (free-form; placement reads it)
#   status          str    STATUSES; lifecycle pending→claimed→in_progress→done|failed|skipped
#   claimed_by      str?   who is working it (e.g. "cowork"); None when pending
#   result_gen_ids  [str]  Higgsfield generation ids CoWork produced (harvest input)
#   result          dict   freeform structured result (e.g. {"soul_id": "..."} )
#   note            str    freeform human/agent note
#   error           str?   failure reason when status == "failed"
#   created_at      str    ISO-8601 UTC
#   updated_at      str    ISO-8601 UTC

KINDS = ("still", "video", "soul")
STATUSES = ("pending", "claimed", "in_progress", "done", "failed", "skipped")
ACTIVE = ("claimed", "in_progress")
TERMINAL = ("done", "failed", "skipped")

_STORE_PATH = Path(
    os.environ.get(
        "MACU_COWORK_JOBS",
        str(Path.home() / ".config" / "macu-studio" / "cowork_jobs.json"),
    )
)

_LOCK = threading.RLock()
_JOBS: dict[str, dict] = {}
_LOADED = False

# Sentinel so update_job can distinguish "don't touch claimed_by" from "set it to
# None" (un-claim). Plain default of None can't express that difference.
_UNSET = object()

# Optional placement-on-done seam (Max wires this). Called with the job dict AFTER
# a transition into "done". Best-effort: exceptions are swallowed so a placement
# failure never corrupts the store (the job stays "done"; the hook can re-run).
_DONE_HOOK: Optional[Callable[[dict], Any]] = None


def set_done_hook(fn: Optional[Callable[[dict], Any]]) -> None:
    """Register (or clear with None) the on-done callback. Inert by default."""
    global _DONE_HOOK
    _DONE_HOOK = fn


# ---- io ------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    with _LOCK:
        if _LOADED:
            return
        if _STORE_PATH.exists():
            try:
                data = json.loads(_STORE_PATH.read_text())
                if isinstance(data, dict):
                    jobs = data.get("jobs", data)
                    if isinstance(jobs, dict):
                        _JOBS.update({k: v for k, v in jobs.items() if isinstance(v, dict)})
            except Exception:
                pass  # corrupt store → start empty rather than crash the backend
        _LOADED = True


def _save() -> None:
    """Atomic mirror to disk (call inside _LOCK)."""
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cowork_jobs.", suffix=".json.tmp",
                               dir=_STORE_PATH.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"version": 1, "jobs": _JOBS}, f, indent=2)
        os.replace(tmp, _STORE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---- helpers -------------------------------------------------------------------

def _new_id() -> str:
    for _ in range(8):
        jid = "j-" + uuid.uuid4().hex[:8]
        if jid not in _JOBS:
            return jid
    return "j-" + uuid.uuid4().hex  # pathological collision streak: full uuid


def _make_job(episode: str, kind: str, target: str, *, prompt: str = "",
              model: str = "", params: Optional[dict] = None, note: str = "") -> dict:
    if not episode:
        raise ValueError("episode is required")
    if kind not in KINDS:
        raise ValueError(f"unknown kind '{kind}' (allowed: {', '.join(KINDS)})")
    if not target:
        raise ValueError("target is required")
    ts = _now()
    return {
        "id": _new_id(),
        "episode": episode,
        "kind": kind,
        "target": target,
        "prompt": prompt or "",
        "model": model or "",
        "params": dict(params or {}),
        "status": "pending",
        "claimed_by": None,
        "result_gen_ids": [],
        "result": {},
        "note": note or "",
        "error": None,
        "created_at": ts,
        "updated_at": ts,
    }


# ---- public API (Max's cowork_* MCP tools import + call these directly) ---------

def create_job(episode: str, kind: str, target: str, *, prompt: str = "",
               model: str = "", params: Optional[dict] = None,
               note: str = "") -> dict:
    """Create one pending job. Returns the stored job dict. Raises ValueError on
    bad kind / missing episode|target."""
    _load()
    with _LOCK:
        job = _make_job(episode, kind, target, prompt=prompt, model=model,
                        params=params, note=note)
        _JOBS[job["id"]] = job
        _save()
        return dict(job)


def bulk_create(episode: str, jobs: list[dict]) -> list[dict]:
    """Seed a whole episode worklist in one call. Each item: {kind, target,
    prompt?, model?, params?, note?} (episode may be omitted → uses the arg).
    All-or-nothing: validates every item before committing any."""
    _load()
    with _LOCK:
        built = [
            _make_job(it.get("episode") or episode, it.get("kind"), it.get("target"),
                      prompt=it.get("prompt", ""), model=it.get("model", ""),
                      params=it.get("params"), note=it.get("note", ""))
            for it in jobs
        ]
        for job in built:
            _JOBS[job["id"]] = job
        _save()
        return [dict(j) for j in built]


def get_job(job_id: str) -> Optional[dict]:
    _load()
    with _LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else None


def list_jobs(*, episode: Optional[str] = None, status: Optional[str] = None,
              kind: Optional[str] = None) -> list[dict]:
    """All jobs matching the (optional) filters, oldest first."""
    _load()
    with _LOCK:
        out = []
        for j in _JOBS.values():
            if episode and j.get("episode") != episode:
                continue
            if status and j.get("status") != status:
                continue
            if kind and j.get("kind") != kind:
                continue
            out.append(dict(j))
    out.sort(key=lambda j: j.get("created_at") or "")
    return out


def update_job(job_id: str, *, status: Optional[str] = None,
               claimed_by: Any = _UNSET,
               result_gen_ids: Optional[list[str]] = None,
               result: Optional[dict] = None, note: Optional[str] = None,
               error: Optional[str] = None,
               params: Optional[dict] = None) -> dict:
    """Patch a job. Only provided fields change. ``params``/``result`` shallow-MERGE
    into the existing dict (pass {} to no-op, not to clear). ``claimed_by`` is
    skipped unless explicitly passed (so you can null it: claimed_by=None).
    Fires the optional done-hook on a fresh transition into "done".
    Raises KeyError if the job is unknown, ValueError on a bad status.

    PURE STORE MUTATION — no placement/harvest happens here (that's Max's layer)."""
    _load()
    if status is not None and status not in STATUSES:
        raise ValueError(f"unknown status '{status}' (allowed: {', '.join(STATUSES)})")
    with _LOCK:
        j = _JOBS.get(job_id)
        if j is None:
            raise KeyError(job_id)
        was_done = j.get("status") == "done"
        if status is not None:
            j["status"] = status
        if claimed_by is not _UNSET:
            j["claimed_by"] = claimed_by
        if result_gen_ids is not None:
            j["result_gen_ids"] = list(result_gen_ids)
        if result:
            j["result"] = {**(j.get("result") or {}), **result}
        if note is not None:
            j["note"] = note
        if error is not None:
            j["error"] = error
        if params:
            j["params"] = {**(j.get("params") or {}), **params}
        j["updated_at"] = _now()
        _JOBS[job_id] = j
        _save()
        snapshot = dict(j)
    if _DONE_HOOK and not was_done and snapshot.get("status") == "done":
        try:
            _DONE_HOOK(snapshot)
        except Exception:
            pass  # placement is best-effort; the job stays done, hook can re-run
    return snapshot


def claim_next(*, episode: Optional[str] = None,
               kinds: Optional[list[str]] = None,
               by: str = "cowork") -> Optional[dict]:
    """Atomically claim the oldest pending job (optionally filtered by episode /
    kinds) → flips it to "claimed"/claimed_by=by and returns it. None if the
    queue is empty. Lets CoWork pull work without racing itself."""
    _load()
    with _LOCK:
        for j in sorted(_JOBS.values(), key=lambda x: x.get("created_at") or ""):
            if j.get("status") != "pending":
                continue
            if episode and j.get("episode") != episode:
                continue
            if kinds and j.get("kind") not in kinds:
                continue
            j["status"] = "claimed"
            j["claimed_by"] = by
            j["updated_at"] = _now()
            _save()
            return dict(j)
    return None


def delete_job(job_id: str) -> bool:
    _load()
    with _LOCK:
        if job_id in _JOBS:
            del _JOBS[job_id]
            _save()
            return True
        return False


def clear(*, episode: Optional[str] = None) -> int:
    """Delete all jobs (or just one episode's). Returns the count removed."""
    _load()
    with _LOCK:
        ids = [k for k, v in _JOBS.items()
               if episode is None or v.get("episode") == episode]
        for k in ids:
            del _JOBS[k]
        if ids:
            _save()
        return len(ids)


def stats(*, episode: Optional[str] = None) -> dict:
    """Counts by status (+ total) for the queue UI / progress reporting."""
    _load()
    counts = {s: 0 for s in STATUSES}
    total = 0
    with _LOCK:
        for j in _JOBS.values():
            if episode and j.get("episode") != episode:
                continue
            counts[j.get("status", "pending")] = counts.get(j.get("status", "pending"), 0) + 1
            total += 1
    counts["total"] = total
    return counts
