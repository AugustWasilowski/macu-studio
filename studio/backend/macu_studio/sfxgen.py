"""LLM-assisted sound-effect-list generation.

Mirror of shotgen.py, for AUDIO. Reads an episode's cues (each carries its spoken
line) and the SFX library we already have, and asks the local LLM (Ollama /
Qwen2.5-7B) to read the script as a RADIO PLAY and propose where sound effects
should land — strongly FAVORING sounds already in the kit, but free to request a
NEW sound (with a short acquire query) when nothing fits.

`generate()` is a dry run returning a proposal; `apply()` merges the (approved,
possibly edited) proposal into manifest.sfx[] in the SAME list shape the Audio-page
drag-and-drop produces, and re-staggers per-gap delays exactly like the frontend's
useSfx.normalize() — so generated effects appear in the timeline identically to
hand-dropped ones. Stage 5 (stage_5_music.py) skips any file that isn't on disk
yet (the acquire-needed ones) with a warning, so an applied proposal never breaks
a render.
"""
from __future__ import annotations

import json
import re

from . import llm
from . import manifest as manifest_mod
from . import assets as assets_mod
from . import prompts

# Default linear placement gain (matches the Audio-page drag-drop default of 0.4).
_DEFAULT_GAIN = 0.4
# Fallback duration (s) for delay staggering when a file's length is unknown
# (an acquire-needed sound not on disk yet) — same fallback the frontend uses.
_FALLBACK_DUR = 0.5

SCHEMA = {
    "type": "object",
    "properties": {
        "sfx": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cue": {"type": "string"},
                    "at": {"type": "string", "enum": ["start", "end"]},
                    "file": {"type": "string"},
                    "query": {"type": "string"},
                    "gain": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["cue", "at", "reason"],
            },
        },
    },
    "required": ["sfx"],
}

SYSTEM = """You are the sound-effects designer for the show, a black-and-white
1970s-broadcast faux-newscast. Treat the script as a RADIO PLAY: read each spoken line
(a cue) and find the moments where a sound effect would land — an action named or
implied (a door, an impact, machinery, a bell, a crowd, footsteps, a switch, weather),
a bit of scene-setting ambience, or a dry comedic punctuation.

Rules:
- For each opportunity attach ONE sound to a cue, anchored at the START or END of that
  cue (`at`) — `start` for a sound that opens the line, `end` for a button/reaction after it.
- FAVOR THE SOUNDS WE ALREADY HAVE. You are given the current SFX library (filenames +
  notes). If an existing file fits, put its EXACT `file` name and leave `query` empty.
  Reusing what we already have is strongly preferred.
- Only when NOTHING in the library fits, request a NEW sound: leave `file` empty and give
  a short, concrete `query` of 2-5 words we can use to acquire it (e.g. "diesel engine
  idle", "metal door slam", "single church bell"). We can acquire or generate new sounds
  at will, so don't force a bad match — but don't ask for a new sound when a close one exists.
- Be TASTEFUL and SPARSE. This is deadpan news, not a cartoon: most lines need NO effect.
  Place effects only where the script clearly calls for one — a handful per episode is
  normal. Do not put an effect on every cue.
- `gain` is a 0-1 linear level (0.3-0.5 is typical; lower for background ambience).
- Use ONLY the cue ids you are given. Do NOT invent cue ids. Give one short `reason` per
  effect naming the script moment it serves.
Return ONLY JSON matching the schema."""


def ensure_prompt_seeded() -> None:
    """Materialize the editable prompt file from the default (no-op if it exists)."""
    prompts.load_or_seed(prompts.SFXGEN_FILE, SYSTEM)


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (s or "").strip().lower())
    return s.strip("_")[:32] or "sfx"


def _existing_entries(m: dict) -> list[dict]:
    """Current SFX placements as a flat list, tolerating both the list form (Audio-page
    drag-drop / fetch) and the older dict form ({enabled, cues:[...]})."""
    sfx = m.get("sfx")
    if isinstance(sfx, list):
        return [e for e in sfx if isinstance(e, dict)]
    if isinstance(sfx, dict):
        return [e for e in (sfx.get("cues") or []) if isinstance(e, dict)]
    return []


def generate(slug: str) -> dict:
    """Dry run: ask the LLM to propose SFX placements. No writes."""
    m = manifest_mod.load(slug)
    cues = m.get("cues") or []
    lib = assets_mod.list_assets("sfx")
    placed = _existing_entries(m)

    payload = {
        "cues": [{"id": c.get("id"), "speaker": c.get("speaker"),
                  "vo": (c.get("vo") or "")[:200], "segment": c.get("segment")} for c in cues],
        "available_sfx": [{"file": a["file"], "duration_s": a.get("duration_s"),
                           "notes": a.get("notes")} for a in lib],
        "already_placed": [{"cue": e.get("cue"), "at": e.get("at"), "file": e.get("file")}
                           for e in placed],
        "production_notes": (m.get("notes") or "")[:1500],
    }
    messages = [
        {"role": "system", "content": prompts.load_or_seed(prompts.SFXGEN_FILE, SYSTEM)},
        {"role": "user", "content": (
            "Read this episode as a radio play and find the sound-effect opportunities. "
            "Prefer the sounds already in `available_sfx`; request a new one only when "
            "nothing fits. Don't duplicate anything in `already_placed`.\n\n"
            + json.dumps(payload)
        )},
    ]

    llm.start()
    try:
        try:
            raw = llm.chat_json(messages, SCHEMA)
        except Exception:
            raw = llm.chat_json(
                messages + [{"role": "user", "content": "Return ONLY valid JSON matching the schema."}],
                SCHEMA)
    finally:
        llm.stop()

    return _proposal(raw, m, lib)


def _proposal(raw: dict, m: dict, lib: list[dict]) -> dict:
    valid_cue_ids = {c.get("id") for c in (m.get("cues") or [])}
    lib_dur = {a["file"]: a.get("duration_s") for a in lib}
    lib_files = set(lib_dur)
    already = {(e.get("cue"), e.get("at"), e.get("file")) for e in _existing_entries(m)}

    entries: list[dict] = []
    seen: set[tuple] = set()
    for s in (raw.get("sfx") or []):
        cue = s.get("cue")
        if cue not in valid_cue_ids:
            continue  # drop hallucinated cue ids
        at = s.get("at") if s.get("at") in ("start", "end") else "start"
        file = (s.get("file") or "").strip()
        query = (s.get("query") or "").strip()
        try:
            gain = float(s.get("gain"))
        except (TypeError, ValueError):
            gain = _DEFAULT_GAIN
        gain = max(0.05, min(1.0, gain))
        reason = (s.get("reason") or "").strip()

        reuse = bool(file) and file in lib_files
        if reuse:
            need = False
            dur = lib_dur.get(file)
        else:
            need = True
            # No usable library file → an acquire suggestion. Derive a query/basename.
            if not query:
                query = re.sub(r"\.wav$", "", file).replace("_", " ").strip() or "sound effect"
            if not file or file not in lib_files:
                file = _slugify(file if file else query) + ".wav"
            dur = None

        key = (cue, at, file)
        if key in seen or key in already:
            continue
        seen.add(key)
        entries.append({
            "cue": cue, "at": at, "file": file, "gain": gain,
            "reuse": reuse, "need": need, "query": query if need else "",
            "reason": reason, "duration_s": dur,
        })

    return {
        "sfx": entries,
        "summary": {
            "opportunities": len(entries),
            "reused": sorted({e["file"] for e in entries if e["reuse"]}),
            "acquire": [{"file": e["file"], "query": e["query"]} for e in entries if e["need"]],
        },
    }


def _normalize(entries: list[dict], cue_ids: list[str], dur_of: dict) -> list[dict]:
    """Re-stagger per-gap delays, mirroring the frontend useSfx.normalize(): entries are
    bucketed by the gap they sit in (at='start' → after the PREVIOUS cue; at='end' → after
    their own cue), then ordered by [pre-roll, cue1, cue2, …]. Within a gap, entries WITHOUT
    an explicit delay are seeded with the running cumulative source duration; entries that
    already carry a delay (user-nudged) are preserved."""
    idx_of = {cid: i for i, cid in enumerate(cue_ids)}

    def after_cue(e: dict):
        if e.get("at") == "start":
            i = idx_of.get(e.get("cue"), -1)
            return cue_ids[i - 1] if i > 0 else None
        return e.get("cue")

    buckets: dict = {}
    for e in entries:
        buckets.setdefault(after_cue(e), []).append(e)

    out: list[dict] = []
    for key in [None, *cue_ids]:
        grp = buckets.pop(key, None)
        if not grp:
            continue
        cum = 0.0
        for e in grp:
            delay = e["delay"] if e.get("delay") is not None else round(cum, 2)
            out.append({**e, "delay": delay})
            cum += dur_of.get(e.get("file")) or _FALLBACK_DUR
    for grp in buckets.values():  # any orphan gap keys
        out.extend(grp)
    return out


def apply(slug: str, proposal: dict) -> dict:
    """Merge an approved proposal into manifest.sfx[] in the Audio-page list shape and
    re-stagger delays so the effects appear in the timeline like hand-dropped ones."""
    m = manifest_mod.load(slug)
    cue_ids = [c.get("id") for c in (m.get("cues") or [])]
    lib = assets_mod.list_assets("sfx")
    dur_of = {a["file"]: a.get("duration_s") for a in lib}

    base = _existing_entries(m)
    existing_keys = {(e.get("cue"), e.get("at"), e.get("file")) for e in base}

    merged = list(base)
    placed = reused = 0
    acquire: list[dict] = []
    for e in (proposal.get("sfx") or []):
        cue, at, file = e.get("cue"), e.get("at"), e.get("file")
        if not (cue and file):
            continue
        if at not in ("start", "end"):
            at = "start"
        if (cue, at, file) in existing_keys:
            continue
        need = bool(e.get("need"))
        entry = {
            "file": file, "cue": cue, "at": at,
            "gain": float(e.get("gain") or _DEFAULT_GAIN), "fade": 0,
            "source": "acquire" if need else "library",
        }
        if need:
            q = (e.get("query") or "").strip()
            if q:
                entry["query"] = q
            acquire.append({"file": file, "query": entry.get("query", "")})
        merged.append(entry)
        existing_keys.add((cue, at, file))
        placed += 1
        reused += 0 if need else 1

    m["sfx"] = _normalize(merged, cue_ids, dur_of)
    manifest_mod.save(slug, m)
    return {"ok": True, "placed": placed, "reused": reused,
            "acquire": acquire, "total": len(m["sfx"])}
