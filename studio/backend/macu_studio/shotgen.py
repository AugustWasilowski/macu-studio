"""LLM-assisted shot-list generation.

Reads an episode's script + cues, the MACU character bible, and a couple of example
manifests, and asks the local LLM (Ollama / Qwen2.5-7B) to propose, per cue, which
character/b-roll shots to use — REUSING existing recurring-character keys where it can
(ron_cheer, walter_deadpan, …) and minting new keys with fresh cores otherwise.

Seeds are assigned PROGRAMMATICALLY (not by the LLM): a reused/known character keeps
its canonical seed; a new variant of a known character family (ron_*, walter_*) inherits
that family's seed; a genuinely new character gets a random seed. The full image prompt
is still `core + style.suffix` at render time, so cores here are character-core only.

`generate()` is a dry run returning a proposal; `apply()` merges an (approved) proposal
into the manifest.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from . import config
from . import llm
from . import manifest as manifest_mod
from . import prompts
from .episodes import episode_dir

EXAMPLE_SLUGS = ["ep-009", "ep-011"]


def _bible_path(show: str | None) -> Path | None:
    """Per-show character bible: docs/shows/<show>/*Character_Prompt_Bible.md.
    Returns None when the show has none yet (e.g. a brand-new show) — `_read`
    then yields an empty bible, which is fine for look-dev-less shows."""
    d = config.REPO_ROOT / "docs" / "shows" / (show or "the-macu-report")
    hits = sorted(d.glob("*Character_Prompt_Bible.md"))
    return hits[0] if hits else None

# Ollama structured-output schema. Lists (not maps) for robust schema support.
SCHEMA = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "core": {"type": "string"}},
                "required": ["key", "core"],
            },
        },
        "broll": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "prompt": {"type": "string"}},
                "required": ["key", "prompt"],
            },
        },
        "cues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cue_id": {"type": "string"},
                    "shots": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["character", "broll"]},
                                "key": {"type": "string"},
                            },
                            "required": ["kind", "key"],
                        },
                    },
                },
                "required": ["cue_id", "shots"],
            },
        },
    },
    "required": ["characters", "broll", "cues"],
}

SYSTEM = """You are the shot director for THE MACU REPORT, a black-and-white 1970s-broadcast
faux-newscast. For each cue (a spoken line) you decide which visual shots play over it.

Rules:
- A shot is either a CHARACTER (a person, by key) or BROLL (an environment/object, by key).
- PREFER REUSING the existing character/broll keys you are given. Recurring anchors Ron and
  Walter already have many pose/mood VARIANT keys (ron_cheer, ron_bet, walter_deadpan,
  walter_pained, …). Pick the existing variant whose mood best fits the line.
- Only MINT A NEW key when no existing key fits (a new character, or a needed new pose/broll).
  New character keys follow the family convention `<base>_<mood>` (e.g. ron_furious) so they
  inherit the family's look; give a short prompt CORE (nouns + 2-3 adjectives, the 1970s-anchor
  framing) — do NOT include the black-and-white/grain style words (the pipeline appends those).
- Most cues are a single shot of the speaking character. Use 1-2 shots per cue; add a broll or
  title-relevant character shot only when the line clearly calls for it.
- Do NOT invent cue ids — only use the cue ids you are given. Do NOT emit seeds.
Return ONLY JSON matching the schema."""


def ensure_prompt_seeded() -> None:
    """Materialize the editable prompt file from the default (no-op if it exists)."""
    prompts.load_or_seed(prompts.SHOTGEN_FILE, SYSTEM)


def _read(p: Path) -> str:
    try:
        return p.read_text()
    except Exception:
        return ""


def _examples(exclude: str = "") -> list[dict]:
    out = []
    for s in EXAMPLE_SLUGS:
        if s == exclude:
            continue  # don't show an episode its own answer
        try:
            m = manifest_mod.load(s)
        except Exception:
            continue
        chars = {k: (v.get("core") if isinstance(v, dict) else str(v)) for k, v in (m.get("characters") or {}).items()}
        broll = {k: (v.get("prompt") if isinstance(v, dict) else str(v)) for k, v in (m.get("broll") or {}).items()}
        cue_shots = [
            {"cue_id": c.get("id"), "speaker": c.get("speaker"),
             "shots": [{"kind": sh.get("kind"), "key": sh.get("who") or sh.get("asset")}
                       for sh in (c.get("shots") or []) if sh.get("kind") in ("character", "broll")]}
            for c in (m.get("cues") or [])
        ]
        out.append({"slug": s, "characters": chars, "broll": broll, "cue_shots": cue_shots[:14]})
    return out


def _seed_assigner(existing_chars: dict) -> Any:
    seed_map = {k: (v.get("seed") if isinstance(v, dict) else None) for k, v in existing_chars.items()}

    def seed_for(key: str) -> int:
        if seed_map.get(key) is not None:
            return seed_map[key]
        base = key.split("_")[0]
        for k, s in seed_map.items():
            if s is not None and k.split("_")[0] == base:
                return s
        return random.randint(10000, 99999)

    return seed_for


def _default_char_key(speaker: str, m: dict, existing_chars: dict) -> str | None:
    """Fallback character key for a cue the LLM left unplanned: the key this speaker is
    already shown with most often, else any existing key in the speaker's name family
    (e.g. 'CRATER CARL' -> a carl_* key). None if the speaker has no character family —
    the cue then stays unplanned (e.g. intercom-only speakers with no on-camera key)."""
    counts: dict[str, int] = {}
    for c in (m.get("cues") or []):
        if c.get("speaker") == speaker:
            for s in (c.get("shots") or []):
                if s.get("kind") == "character" and s.get("who"):
                    counts[s["who"]] = counts.get(s["who"], 0) + 1
    if counts:
        return max(counts, key=counts.get)
    toks = [t for t in re.split(r"[^a-z0-9]+", (speaker or "").lower()) if t]
    for tok in reversed(toks):  # last token first: 'CRATER CARL' -> carl
        for k in existing_chars:
            if k.split("_")[0] == tok:
                return k
    return None


def _empty_proposal() -> dict:
    return {"characters": {}, "broll": {}, "cues": [],
            "summary": {"new_characters": [], "reused_characters": [],
                        "new_broll": [], "reused_broll": [], "cues_planned": 0}}


def generate(slug: str, only_missing: bool = False) -> dict:
    """Dry run: ask the LLM, return a {characters, broll, cues, summary} proposal. No writes.

    only_missing=True plans ONLY the cues that have no shots yet (gap-fill), leaving the
    already-planned cues untouched — the safe default for an in-progress episode. On a
    fresh episode every cue is empty, so it still plans them all. only_missing=False
    re-plans every cue (apply then overwrites existing shots)."""
    m = manifest_mod.load(slug)
    cues = m.get("cues") or []
    existing_chars = m.get("characters") or {}
    existing_broll = m.get("broll") or {}

    if only_missing:
        target_ids = [c.get("id") for c in cues if not c.get("shots")]
        if not target_ids:
            return _empty_proposal()  # nothing to fill — every cue already has shots
    else:
        target_ids = [c.get("id") for c in cues]

    # The cues already carry each spoken line (vo) — that's the structured input the
    # model needs. Do NOT also send the full script.md (it blows past the context
    # window and the cues stop being visible). Keep a trimmed bible for new-character
    # look/family guidance. In gap-fill mode every cue is still sent (with its current
    # shot status) for continuity context, but only `cues_to_plan` should be returned.
    payload = {
        "cues": [{"id": c.get("id"), "speaker": c.get("speaker"),
                  "vo": (c.get("vo") or "")[:200], "segment": c.get("segment"),
                  "already_has_shots": bool(c.get("shots"))} for c in cues],
        "cues_to_plan": target_ids,
        "existing_characters": {k: (v.get("core") if isinstance(v, dict) else str(v)) for k, v in existing_chars.items()},
        "existing_broll": list(existing_broll.keys()),
        "bible": _read(_bible_path(m.get("show")))[:5000],
        "examples": _examples(exclude=slug),
    }
    instr = (
        "Plan the shots ONLY for the cue ids listed in `cues_to_plan`. Every other cue "
        "already has shots — use them as context for visual continuity, but do NOT "
        "re-plan them.\n\n"
        if only_missing else
        "Plan the shots for this episode.\n\n")
    messages = [
        {"role": "system", "content": prompts.load_or_seed(prompts.SHOTGEN_FILE, SYSTEM)},
        {"role": "user", "content": instr + json.dumps(payload)},
    ]

    llm.start()
    try:
        try:
            raw = llm.chat_json(messages, SCHEMA)
        except Exception:
            raw = llm.chat_json(messages + [{"role": "user", "content": "Return ONLY valid JSON matching the schema."}], SCHEMA)
    finally:
        llm.stop()

    return _proposal(raw, m, target_ids=set(target_ids))


def _proposal(raw: dict, m: dict, target_ids: set | None = None) -> dict:
    existing_chars = m.get("characters") or {}
    existing_broll = m.get("broll") or {}
    all_cue_ids = {c.get("id") for c in (m.get("cues") or [])}
    # Cues we're allowed to (re)plan. In gap-fill mode this is just the shot-less cues,
    # so the proposal — and therefore apply() — never touches already-planned cues.
    keep_ids = set(target_ids) if target_ids is not None else all_cue_ids
    seed_for = _seed_assigner(existing_chars)

    char_cores = {c["key"]: c.get("core", "") for c in (raw.get("characters") or []) if c.get("key")}
    broll_prompts = {b["key"]: b.get("prompt", "") for b in (raw.get("broll") or []) if b.get("key")}

    used_char: set[str] = set()
    used_broll: set[str] = set()
    per_cue = []
    for cu in (raw.get("cues") or []):
        cid = cu.get("cue_id")
        if cid not in keep_ids:
            continue  # drop hallucinated ids + (in gap-fill) cues we must not re-plan
        shots = []
        for i, sh in enumerate(cu.get("shots") or [], 1):
            kind, key = sh.get("kind"), sh.get("key")
            if kind not in ("character", "broll") or not key:
                continue
            shot = {"id": f"{cid}_s{i}", "kind": kind, "who": key}
            if kind == "character":
                shot["seed"] = seed_for(key)
                used_char.add(key)
            else:
                used_broll.add(key)
            shots.append(shot)
        if shots:
            per_cue.append({"cue_id": cid, "shots": shots})

    # Coverage backstop: the local 7B model often omits cues on long episodes, leaving
    # them shot-less — which later divides-by-zero in stage 4. Give every uncovered cue
    # a single default shot of its speaker's character (a reused, already-defined key),
    # so the proposal is always complete. The operator can refine the mood per cue after.
    covered = {pc["cue_id"] for pc in per_cue}
    cue_speaker = {c.get("id"): c.get("speaker") for c in (m.get("cues") or [])}
    for cid in keep_ids:
        if cid in covered:
            continue
        key = _default_char_key(cue_speaker.get(cid), m, existing_chars)
        if not key:
            continue  # no character family for this speaker — leave it to the operator
        per_cue.append({"cue_id": cid,
                        "shots": [{"id": f"{cid}_s1", "kind": "character",
                                   "who": key, "seed": seed_for(key)}]})
        used_char.add(key)

    def char_core(key: str) -> str:
        if key in existing_chars:
            v = existing_chars[key]
            return v.get("core") if isinstance(v, dict) else str(v)
        return char_cores.get(key, "")

    def broll_prompt(key: str) -> str:
        if key in existing_broll:
            v = existing_broll[key]
            return v.get("prompt") if isinstance(v, dict) else str(v)
        return broll_prompts.get(key, "")

    characters = {k: {"reuse": k in existing_chars, "seed": seed_for(k), "core": char_core(k)} for k in sorted(used_char)}
    broll = {k: {"reuse": k in existing_broll, "prompt": broll_prompt(k)} for k in sorted(used_broll)}

    return {
        "characters": characters,
        "broll": broll,
        "cues": per_cue,
        "summary": {
            "new_characters": [k for k, v in characters.items() if not v["reuse"]],
            "reused_characters": [k for k, v in characters.items() if v["reuse"]],
            "new_broll": [k for k, v in broll.items() if not v["reuse"]],
            "reused_broll": [k for k, v in broll.items() if v["reuse"]],
            "cues_planned": len(per_cue),
        },
    }


def apply(slug: str, proposal: dict) -> dict:
    """Merge an approved proposal into the manifest: write new character/broll defs and
    set each planned cue's shots[]. Reused keys are left as-is (or seeded into place if
    somehow missing). One validated save."""
    m = manifest_mod.load(slug)
    chars = m.setdefault("characters", {})
    broll = m.setdefault("broll", {})

    for key, v in (proposal.get("characters") or {}).items():
        if not v.get("reuse") or key not in chars:
            chars[key] = {"seed": v.get("seed"), "core": v.get("core", "")}
    for key, v in (proposal.get("broll") or {}).items():
        if not v.get("reuse") or key not in broll:
            broll[key] = v.get("prompt", "")

    cue_by_id = {c.get("id"): c for c in (m.get("cues") or [])}
    applied = 0
    for pc in (proposal.get("cues") or []):
        c = cue_by_id.get(pc.get("cue_id"))
        if c is not None and isinstance(pc.get("shots"), list):
            c["shots"] = pc["shots"]
            applied += 1

    manifest_mod.save(slug, m)
    return {"ok": True, "applied_cues": applied,
            "new_characters": len([1 for v in (proposal.get("characters") or {}).values() if not v.get("reuse")]),
            "new_broll": len([1 for v in (proposal.get("broll") or {}).values() if not v.get("reuse")])}
