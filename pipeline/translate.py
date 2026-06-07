#!/usr/bin/env python3
"""Translate MACU cue / subtitle text into a target language for the Localize feature.

Two engines, both LOCAL, chosen at runtime:
  - "qwen": Ollama qwen2.5:7b with a deadpan + glossary + length-budget prompt. Creative,
    length-aware (helps the dub fit each cue's on-screen time), may paraphrase. All 48 locales.
  - "argos": OmniVoice's bundled Argos NMT via POST /dub/translate (provider="argos"). Literal,
    fast, pure-CPU, flatter phrasing, no length control. Covers the major languages only — a
    locale with no Argos package falls back to the English source (reported, never blank).
    (OmniVoice's NLLB-200 engine ships broken — `AutoTokenizer` import fails — so we use Argos.)

Public API:
    translate(items, target_lang, engine, glossary) -> {id: translated_text}
where `items` = [{"id": str, "text": str}, ...] (cue ids for VO; subtitle indices for SRT),
`target_lang` is a BCP-47-ish locale code (es, pt-BR, zh-Hans, ...), `engine` in {qwen, argos},
and `glossary` = [{"source","target","note"?}, ...] (proper nouns; target==source = keep verbatim).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from lib import OMNIVOICE_URL  # noqa: E402
import llm_ollama  # noqa: E402

# Locale code -> the language NAME OmniVoice /generate expects for its `language` field.
# (k2-fsa/OmniVoice is 600+ languages; it accepts plain English names. "Auto" = detect.)
LOCALE_TO_OMNIVOICE = {
    "es": "Spanish", "hi": "Hindi", "uk": "Ukrainian", "fr": "French", "it": "Italian",
    "pt-BR": "Portuguese", "ro": "Romanian", "ca": "Catalan", "de": "German", "nl": "Dutch",
    "pl": "Polish", "cs": "Czech", "el": "Greek", "sv": "Swedish", "da": "Danish",
    "nb": "Norwegian", "fi": "Finnish", "hu": "Hungarian", "tr": "Turkish",
    "zh-Hans": "Chinese", "zh-Hant": "Chinese", "ja": "Japanese", "ko": "Korean",
    "vi": "Vietnamese", "th": "Thai", "id": "Indonesian", "ms": "Malay", "fil": "Filipino",
    "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "mr": "Marathi", "gu": "Gujarati",
    "ur": "Urdu", "pa": "Punjabi", "ml": "Malayalam", "kn": "Kannada", "ar": "Arabic",
    "he": "Hebrew", "fa": "Persian", "sw": "Swahili", "am": "Amharic", "yo": "Yoruba",
    "ha": "Hausa", "zu": "Zulu", "ig": "Igbo", "af": "Afrikaans", "so": "Somali",
}

# Locale code -> Argos short code for OmniVoice /dub/translate (provider="argos").
# Argos uses ISO-639-1-ish codes and only ships a subset of pairs from English; a locale
# absent here (or with no Argos package at runtime) falls back to the English source.
LOCALE_TO_ARGOS = {
    "es": "es", "hi": "hi", "uk": "uk", "fr": "fr", "it": "it", "pt-BR": "pt", "ro": "ro",
    "ca": "ca", "de": "de", "nl": "nl", "pl": "pl", "cs": "cs", "el": "el", "sv": "sv",
    "da": "da", "fi": "fi", "hu": "hu", "tr": "tr", "zh-Hans": "zh", "ja": "ja", "ko": "ko",
    "vi": "vi", "th": "th", "id": "id", "ar": "ar", "he": "he", "fa": "fa",
}


def omnivoice_language(locale: str) -> str:
    return LOCALE_TO_OMNIVOICE.get(locale, "Auto")


def lang_name(locale: str) -> str:
    return LOCALE_TO_OMNIVOICE.get(locale, locale)


# ---------------------------------------------------------------------------
# qwen path
# ---------------------------------------------------------------------------

def _qwen_chunks(items, size=20):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _qwen_glossary_text(glossary):
    if not glossary:
        return "(none)"
    lines = []
    for g in glossary:
        s, t = g.get("source", ""), g.get("target", "")
        if not s:
            continue
        if t and t != s:
            lines.append(f'  "{s}" -> "{t}"' + (f"  ({g['note']})" if g.get("note") else ""))
        else:
            lines.append(f'  "{s}" -> keep verbatim, do NOT translate')
    return "\n".join(lines) if lines else "(none)"


def _translate_qwen(items, target_lang, glossary):
    name = lang_name(target_lang)
    gtext = _qwen_glossary_text(glossary)
    out: dict[str, str] = {}
    for chunk in _qwen_chunks(items):
        payload = {it["id"]: it["text"] for it in chunk}
        schema = {
            "type": "object",
            "properties": {it["id"]: {"type": "string"} for it in chunk},
            "required": [it["id"] for it in chunk],
        }
        system = (
            f"You translate lines of a deadpan, post-apocalyptic faux-newscast into {name}. "
            "Preserve the DRY, UNDERSTATED, deadpan register — never punch up or explain a joke. "
            "Keep each translation TERSE and within roughly ±15% of the source's character length "
            "so it fits the same on-screen time. Translate naturally, not word-for-word.\n"
            "Glossary (use these exact targets for proper nouns; 'keep verbatim' means copy the "
            f"English unchanged):\n{gtext}\n"
            "Return a JSON object mapping each input id to its translated string. Translate the "
            "VALUES only; keep the ids unchanged. Output nothing but the JSON."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        res = llm_ollama.chat_json(messages, schema, temperature=0.3)
        for it in chunk:
            v = res.get(it["id"])
            out[it["id"]] = v if isinstance(v, str) and v.strip() else it["text"]
    return out


# ---------------------------------------------------------------------------
# argos path (OmniVoice /dub/translate, provider="argos")
# ---------------------------------------------------------------------------

def argos_supports(locale: str) -> bool:
    return locale in LOCALE_TO_ARGOS


def _translate_argos(items, target_lang, glossary):
    code = LOCALE_TO_ARGOS.get(target_lang)
    if not code:
        # No Argos package for this locale → English fallback for every item.
        return {it["id"]: it["text"] for it in items}
    segments = [{"id": it["id"], "text": it["text"]} for it in items]
    gloss = [{"source": g.get("source", ""), "target": g.get("target", ""),
              "note": g.get("note", "")} for g in (glossary or []) if g.get("source")]
    body = {"segments": segments, "target_lang": code, "source_lang": "en",
            "provider": "argos", "glossary": gloss}
    req = urllib.request.Request(
        OMNIVOICE_URL + "/dub/translate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=600).read())
    out: dict[str, str] = {}
    for s in (resp.get("translated") or []) if isinstance(resp, dict) else []:
        if isinstance(s, dict) and s.get("id") is not None and not s.get("error"):
            txt = s.get("text")
            if isinstance(txt, str) and txt.strip():
                out[s["id"]] = txt
    # Any item the engine couldn't translate falls back to English (never blank).
    for it in items:
        out.setdefault(it["id"], it["text"])
    return out


def translate(items, target_lang, engine, glossary=None):
    """Translate items -> {id: text}. engine in {"qwen","argos"}. Never raises on a
    single bad line — missing translations fall back to the English source."""
    items = [it for it in items if (it.get("text") or "").strip()]
    if not items:
        return {}
    if engine == "qwen":
        return _translate_qwen(items, target_lang, glossary)
    if engine == "argos":
        return _translate_argos(items, target_lang, glossary)
    raise ValueError(f"unknown engine {engine!r} (expected 'qwen' or 'argos')")


if __name__ == "__main__":
    # Smoke test: python3 translate.py <locale> <qwen|nllb>
    loc = sys.argv[1] if len(sys.argv) > 1 else "es"
    eng = sys.argv[2] if len(sys.argv) > 2 else "qwen"
    demo = [
        {"id": "c01", "text": "Welcome to the MACU Report. The world has ended; the broadcast has not."},
        {"id": "c02", "text": "Ron, what's the weather looking like out at Lake Mirabel?"},
        {"id": "c03", "text": "Cloudy, with a chance of the Product."},
    ]
    gl = [{"source": "MACU Report", "target": "MACU Report"},
          {"source": "Ron", "target": "Ron"},
          {"source": "Lake Mirabel", "target": "Lake Mirabel"},
          {"source": "the Product", "target": "the Product"}]
    if eng == "qwen":
        llm_ollama.start()
    try:
        res = translate(demo, loc, eng, gl)
    finally:
        if eng == "qwen":
            llm_ollama.stop()
    print(json.dumps(res, ensure_ascii=False, indent=2))
