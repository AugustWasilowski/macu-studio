"""Editable Ollama prompts, surfaced on the Docs page.

The shot-list and card-text generators (shotgen.py / cardgen.py) used to carry
their LLM system prompts as hardcoded Python strings. This module externalizes
them into plain markdown files under <repo>/docs/ — the same dir the Docs page
(routes_docs.py / docs.py) lists and edits — so they can be viewed and tuned
from the Studio UI without a code change or rebuild.

Each prompt is read FRESH on every generation (load_or_seed), so an edit saved
on the Docs page takes effect on the next "Generate" with no restart. If a file
is missing it is seeded from the in-code default (the caller passes it in), so
the defaults remain the single source of truth and the files always exist for
the Docs list.

Files:
  PROMPT_shot-list.md    shotgen SYSTEM prompt (whole file == the prompt)
  PROMPT_card-text.md    cardgen SYSTEM prompt (whole file == the prompt)
  PROMPT_card-briefs.md  per-card-type briefs, one `## <card_type>` section each
"""
from __future__ import annotations

import re

from . import docs

SHOTGEN_FILE = "PROMPT_shot-list.md"
SFXGEN_FILE = "PROMPT_sfx-list.md"
CARDGEN_FILE = "PROMPT_card-text.md"
CARD_BRIEFS_FILE = "PROMPT_card-briefs.md"
COMPOSITION_FILE = "PROMPT_composition.md"

_BRIEFS_PREAMBLE = (
    "<!-- Per-card-type briefs for the show card-text generator.\n"
    "     Each `## <card_type>` section below is the brief handed to the LLM on\n"
    "     top of the card-text system prompt (PROMPT_card-text.md). Edit the\n"
    "     prose under each heading; keep the `## ` headings exactly as named.\n"
    "     Text before the first heading (this note) is ignored. A missing\n"
    "     section falls back to the in-code default. -->\n"
)

_SECTION_RE = re.compile(r"^##[ \t]+(\S+)[ \t]*$", re.MULTILINE)


def _read(name: str) -> str | None:
    # PROMPT_* / pipeline prompts are shared across all shows → docs/_common.
    try:
        return docs.read(name, scope="common")
    except FileNotFoundError:
        return None


def load_or_seed(name: str, default_text: str) -> str:
    """Return the live text of prompt file `name`, seeding it from `default_text`
    (atomic write into docs/_common) the first time if it doesn't exist yet."""
    text = _read(name)
    if text is None:
        docs.write(name, default_text if default_text.endswith("\n") else default_text + "\n", scope="common")
        return default_text.strip()
    return text.strip()


def _serialize_briefs(briefs: dict[str, str]) -> str:
    out = [_BRIEFS_PREAMBLE]
    for key, body in briefs.items():
        out.append(f"## {key}\n\n{body.strip()}\n")
    return "\n".join(out) + "\n"


def _parse_briefs(text: str) -> dict[str, str]:
    """Split a briefs doc into {card_type: brief} by its `## <card_type>` headings.
    Text before the first heading is ignored (it's the explanatory preamble)."""
    out: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        key = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            out[key] = body
    return out


def load_or_seed_briefs(defaults: dict[str, str]) -> dict[str, str]:
    """Return the live per-card-type briefs, seeding the file from `defaults` the
    first time. Any card type missing from the file falls back to its default, so
    the generator never ends up without a brief."""
    text = _read(CARD_BRIEFS_FILE)
    if text is None:
        docs.write(CARD_BRIEFS_FILE, _serialize_briefs(defaults), scope="common")
        return dict(defaults)
    parsed = _parse_briefs(text)
    return {key: parsed.get(key) or defaults[key] for key in defaults}
