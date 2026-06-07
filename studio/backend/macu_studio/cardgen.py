"""LLM-assisted HyperFrames card-text generation.

The HyperFrames title/thumbnail compositions are all driven by the SAME five string
fields (the only interface between the manifest and the rendered card):

    kicker        small all-caps mono line above the title (a label / tease)
    title_line_1  big Anton wordmark, line 1
    title_line_2  big Anton wordmark, line 2
    sub           small mono tagline under the title
    idtag         tiny corner stamp, almost always "EP <N> • MACU"

This module asks the on-demand local LLM (Ollama / Qwen2.5-7B, see llm.py) to WRITE
those five fields for a given card TYPE, in the MACU house voice: black-and-white
1970s-broadcast, post-apocalyptic, bone-dry deadpan that's funny precisely because it
plays it straight. Where it can, it lifts an actual punchline/phrase from the episode
script rather than inventing one.

`generate(slug, card_type)` is a dry run returning a proposed {composition, fields,
...} — no writes. `apply(slug, card_type, key, fields, composition)` merges an
(approved, possibly hand-edited) fields dict into the manifest so the existing
hyperframes.py render path picks it up unchanged.
"""
from __future__ import annotations

import json
import re

from pathlib import Path

from . import config
from . import llm
from . import manifest as manifest_mod
from . import prompts
from . import script as script_mod


def _bible_path(show: str | None) -> Path | None:
    """Per-show character bible: docs/shows/<show>/*Character_Prompt_Bible.md.
    None when the show has none yet — `_read_text` then yields an empty excerpt."""
    d = config.REPO_ROOT / "docs" / "shows" / (show or "the-macu-report")
    hits = sorted(d.glob("*Character_Prompt_Bible.md"))
    return hits[0] if hits else None

# Five-field schema — every MACU card composition consumes exactly these. Strings so
# Ollama's structured-output (`format`) stays on the well-supported flat-object path.
FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "kicker": {"type": "string"},
        "title_line_1": {"type": "string"},
        "title_line_2": {"type": "string"},
        "sub": {"type": "string"},
        "idtag": {"type": "string"},
    },
    "required": ["kicker", "title_line_1", "title_line_2", "sub", "idtag"],
}

# Per-type: which HyperFrames composition the card renders through, and the specific
# brief handed to the model on top of the shared house-voice system prompt. Keep these
# field-length notes honest — the Anton wordmark (title lines) is ~150px; long lines
# overflow the 1024px card, so the title lines must be SHORT.
CARD_TYPES: dict[str, dict] = {
    "macu_title": {
        "composition": "intro",
        "brief": (
            "The RECURRING franchise title card that opens the broadcast. The wordmark "
            "is the show itself, so title_line_1='THE MACU' and title_line_2='REPORT' "
            "(do not change these). kicker is tonight's bulletin tease — a short, "
            "deadpan all-caps topic line drawn from what this episode is actually about. "
            "sub is a single dry station-ID tagline (e.g. 'FROM THE LAST TRANSMITTER.'). "
            "Funny via flat understatement, never a joke with a setup."
        ),
    },
    "fresh_title": {
        "composition": "intro",
        "brief": (
            "A FRESH per-episode segment title card (same layout as the franchise intro, "
            "different words). title_line_1 + title_line_2 are the SEGMENT/EPISODE title "
            "broken across two short lines (each <= ~16 chars, all-caps, no punctuation) — "
            "punchy and a little ominous. kicker is a short topic tease above it. sub is a "
            "one-line deadpan logline, ideally lifting a phrase or beat straight from the "
            "script. Think a grim TV chyron written by someone too tired to be scared."
        ),
    },
    "weather": {
        "composition": "weather",
        "brief": (
            "The WEATHER segment card — a post-apocalyptic forecast delivered like routine "
            "local news. kicker is a short all-caps segment label naming the weather beat. "
            "title_line_1 + title_line_2 are the forecast headline in two short blunt lines: "
            "name a specific grim condition tied to THIS episode's setting (look for outside / "
            "sky / temperature / hazard beats in the script), never generic, never cute. sub "
            "is a one-line deadpan advisory that treats catastrophe as a mild inconvenience. "
            "Comedy comes from the flat delivery, not from the words being silly."
        ),
    },
    "youtube_thumb": {
        "composition": "youtube_thumb",
        "brief": (
            "The YOUTUBE THUMBNAIL — read at a glance on a phone, so MAXIMUM punch and "
            "MINIMUM words. title_line_1 + title_line_2 are the hook in two VERY short, "
            "VERY loud all-caps lines (<= ~12 chars each) — the single most absurd or "
            "quotable idea in the episode, ideally a verbatim punchline from the script. "
            "kicker is a tiny over-line label. sub is one short barbed teaser. idtag stays "
            "the EP stamp. Bait the click without lying about the episode."
        ),
    },
}

SYSTEM = """You are the on-air graphics writer for THE MACU REPORT, a black-and-white
1970s-broadcast faux-newscast set after a vague apocalypse. You write the TEXT that goes
on title cards, weather cards, and thumbnails.

House voice:
- Bone-dry DEADPAN. Report the end of the world in the flat cadence of a local anchor
  reading a school-closing list. The humor is in the understatement — never tell a joke
  with a setup and punchline, never use exclamation marks (except a thumbnail may use ONE),
  never wink at the audience.
- When the episode script contains a quotable line, a recurring bit, or a vivid phrase,
  LIFT IT. A real punchline from the script beats anything you invent.
- All card text is ALL-CAPS in the final render — write it in all-caps.
- The big title lines render in a huge font: keep each title line SHORT or it overflows.
- Stay in-world: 1970s broadcast diction, post-collapse setting, no modern slang, no emoji.
- Any example wording shown in a brief illustrates TONE ONLY. NEVER copy an example
  verbatim — write fresh words drawn from THIS episode's script every time.

You will be told the card TYPE and its specific brief, plus the episode's script and notes.
Return ONLY the five fields as JSON matching the schema."""


def _default_briefs() -> dict[str, str]:
    return {k: v["brief"] for k, v in CARD_TYPES.items()}


def _brief(card_type: str) -> str:
    """The live (possibly Docs-edited) brief for `card_type`, else the in-code default."""
    return prompts.load_or_seed_briefs(_default_briefs()).get(card_type) \
        or CARD_TYPES[card_type]["brief"]


def ensure_prompt_seeded() -> None:
    """Materialize the editable system-prompt + briefs files (no-op if they exist)."""
    prompts.load_or_seed(prompts.CARDGEN_FILE, SYSTEM)
    prompts.load_or_seed_briefs(_default_briefs())


def _read_text(p) -> str:
    try:
        return p.read_text()
    except Exception:
        return ""


def _episode_number(slug: str) -> str:
    m = re.search(r"(\d+)", slug or "")
    return str(int(m.group(1))) if m else ""


def _default_idtag(slug: str) -> str:
    n = _episode_number(slug)
    return f"EP {n} • MACU" if n else "MACU"


def card_types() -> list[str]:
    """Names of supported card types (for the Studio UI dropdown)."""
    return list(CARD_TYPES.keys())


def generate(slug: str, card_type: str, composition: str | None = None,
             temperature: float = 0.7) -> dict:
    """Dry run: ask the LLM to write the five card fields for `card_type`. No writes.

    Returns {card_type, composition, fields, idtag_default}. The caller (Studio) shows
    the fields for edit, then POSTs them to apply(). A slightly warm temperature is the
    default here — this is comedy writing, not the deterministic shot planner."""
    spec = CARD_TYPES.get(card_type)
    if spec is None:
        raise ValueError(f"unknown card_type {card_type!r}; one of {list(CARD_TYPES)}")
    comp = composition or spec["composition"]
    brief = _brief(card_type)

    m = manifest_mod.load(slug)
    sc = script_mod.read(slug)
    notes = (m.get("notes") or "")
    # Segment/topic hints from the cues help the model aim the kicker/title.
    segments = []
    for c in (m.get("cues") or []):
        seg = c.get("segment")
        if seg and seg not in segments:
            segments.append(seg)

    payload = {
        "card_type": card_type,
        "brief": brief,
        "episode_slug": slug,
        "episode_number": _episode_number(slug),
        "episode_title": m.get("title") or "",
        "segments": segments[:20],
        "production_notes": notes[:1500],
        "script": (sc.get("text") or "")[:9000],
        "bible_excerpt": _read_text(_bible_path(m.get("show")))[:2500],
    }
    messages = [
        {"role": "system", "content": prompts.load_or_seed(prompts.CARDGEN_FILE, SYSTEM)},
        {"role": "user", "content": (
            f"Write the card text for a `{card_type}` card.\n\n"
            f"BRIEF: {brief}\n\n"
            "Use the episode context below. Prefer lifting a real punchline from the "
            "script over inventing one.\n\n" + json.dumps(payload)
        )},
    ]

    llm.start()
    try:
        try:
            raw = llm.chat_json(messages, FIELD_SCHEMA, temperature=temperature)
        except Exception:
            raw = llm.chat_json(
                messages + [{"role": "user", "content": "Return ONLY valid JSON with the five fields."}],
                FIELD_SCHEMA, temperature=temperature)
    finally:
        llm.stop()

    fields = _clean_fields(raw, slug, card_type)
    return {
        "card_type": card_type,
        "composition": comp,
        "fields": fields,
        "idtag_default": _default_idtag(slug),
        "warnings": _length_warnings(fields, card_type),
    }


# Soft length budgets (chars). The big Anton wordmark overflows the 1024px card past
# ~22 chars; thumbnails need to read on a phone so they're tighter. These only WARN —
# the operator reviews + trims before apply; we never auto-truncate (it kills the joke).
_TITLE_MAX = {"youtube_thumb": 14}
_SUB_MAX = {"youtube_thumb": 40}


def _length_warnings(fields: dict, card_type: str) -> list[str]:
    out = []
    tmax = _TITLE_MAX.get(card_type, 22)
    smax = _SUB_MAX.get(card_type, 48)
    for ln in ("title_line_1", "title_line_2"):
        v = fields.get(ln, "")
        if len(v) > tmax:
            out.append(f"{ln} is {len(v)} chars (> {tmax}) — will overflow the wordmark; trim it")
    if len(fields.get("sub", "")) > smax:
        out.append(f"sub is {len(fields['sub'])} chars (> {smax}) — consider shortening")
    return out


def _clean_fields(raw: dict, slug: str, card_type: str) -> dict:
    """Normalize the model output to the five string fields, upper-case the on-air text,
    pin the franchise title + idtag where they're fixed, and trim runaway whitespace."""
    def s(key: str) -> str:
        return re.sub(r"\s+", " ", str(raw.get(key) or "")).strip()

    fields = {
        "kicker": s("kicker").upper(),
        "title_line_1": s("title_line_1").upper(),
        "title_line_2": s("title_line_2").upper(),
        "sub": s("sub").upper(),
        "idtag": s("idtag") or _default_idtag(slug),
    }
    # The franchise title card's wordmark is fixed branding — never let the model drift it.
    if card_type == "macu_title":
        fields["title_line_1"] = "THE MACU"
        fields["title_line_2"] = "REPORT"
    # idtag is a stamp, not a sentence — keep the model from over-writing it.
    if len(fields["idtag"]) > 24 or "MACU" not in fields["idtag"].upper():
        fields["idtag"] = _default_idtag(slug)
    return fields


def apply(slug: str, card_type: str, key: str, fields: dict,
          composition: str | None = None) -> dict:
    """Merge approved card fields into the manifest so hyperframes.py renders them.

    - youtube_thumb writes manifest.youtube_thumb = {composition, fields} (the shape
      hyperframes.submit_thumb / routes_graphics already consume).
    - every other type writes title_assets[key] = {source:'hyperframes', composition,
      fields}, the object form hyperframes._run requires for regen.
    One validated save. Returns the manifest entry that was written."""
    if not isinstance(fields, dict) or not fields:
        raise ValueError("fields object required")
    spec = CARD_TYPES.get(card_type)
    comp = composition or (spec["composition"] if spec else None)
    if not comp:
        raise ValueError(f"unknown card_type {card_type!r} and no composition given")

    # Only keep the five known field keys; coerce to str.
    clean = {k: str(fields.get(k, "")) for k in
             ("kicker", "title_line_1", "title_line_2", "sub", "idtag") if k in fields}

    m = manifest_mod.load(slug)
    if card_type == "youtube_thumb":
        m["youtube_thumb"] = {"composition": comp, "fields": clean}
        entry = m["youtube_thumb"]
    else:
        if not key:
            raise ValueError("key required for a title-card type")
        ta = m.setdefault("title_assets", {})
        ta[key] = {"source": "hyperframes", "composition": comp, "fields": clean}
        entry = ta[key]
    manifest_mod.save(slug, m)
    return {"ok": True, "card_type": card_type, "key": key if card_type != "youtube_thumb" else None,
            "entry": entry}
