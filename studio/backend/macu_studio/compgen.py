"""LLM-generated HyperFrames compositions (local Qwen via Ollama).

From a free-text brief, the local model writes a complete self-contained HyperFrames
`index.html` (a 1024x1024 animated MACU title/graphic card). We save it as a NEW
composition template under assets/hyperframes/templates/<name>/index.html, scan it for
`‹PLACEHOLDER›` tokens (the editable-text interface), and hand the name + placeholder
field set back to the Studio. The normal title-card flow (submit_new → render) then
renders it; the operator fills the placeholder fields in the Edit modal.

This is the deterministic-render bet for local: the system prompt (PROMPT_composition.md,
editable in Docs) pins the hard contract (paused GSAP timeline on window.__timelines,
no rng/time/raf, 1024², MACU style) and few-shots the real `intro` template, so a 7B can
produce structurally-valid cards. Quality scales with the examples/blocks we feed it.
"""
from __future__ import annotations

import re

from . import llm
from . import prompts
from . import hyperframes
from . import manifest as manifest_mod

# Full default — seeds docs/PROMPT_composition.md on first run; that file (editable in the
# Docs tab) then wins. Keep this and the doc in sync if you change the contract here.
SYSTEM = """You are the motion-graphics author for THE MACU REPORT — a black-and-white, 1970s-broadcast,
post-apocalyptic faux-newscast. From a short brief you write ONE self-contained HyperFrames
composition: a single `index.html` that renders a 1024×1024 animated title/graphic card.

Return ONLY the complete `index.html` — no markdown fences, no commentary, no explanation.

## Hard output contract (a render fails if any of these are wrong)
- The document is ONE self-contained HTML file, 1024×1024. External CDNs for fonts and GSAP
  are allowed (see the example); NO local asset files, NO <img src> to disk, NO network calls
  at runtime beyond the font/GSAP CDN in <head>.
- It MUST contain a root element:
  `<div id="root" data-composition-id="main" data-start="0" data-duration="<seconds>" data-width="1024" data-height="1024">`
  with a single `.clip` child carrying `data-start="0" data-duration="<seconds>" data-track-index="1"`.
- ALL animation is one GSAP timeline, created `paused:true`, and registered as
  `window.__timelines["main"] = tl;`. HyperFrames renders by SEEKING this timeline frame by
  frame — so it MUST be fully deterministic:
  - NO `requestAnimationFrame`, NO `setTimeout`/`setInterval`, NO `Date.now()`/`new Date()`,
    NO `Math.random()`. Every motion is a GSAP tween at an explicit time on the timeline.
  - A value that "changes" (a score going 2→1, a counter, a wheel landing) is animated with a
    GSAP tween on a JS object + an `onUpdate` that writes the DOM (e.g. round the number, set
    `textContent`, or set `rotation`). Pick fixed start/end values from the brief — never random.
- `data-duration` on `#root` and `.clip` MUST equal the timeline's total length. Keep it 4–8s
  unless the brief says otherwise.

## Editable text = placeholders
Any text the operator should be able to re-edit later MUST be a placeholder token of the form
`‹UPPER_SNAKE›` (e.g. `‹TITLE_LINE_1›`, `‹HOME_TEAM›`, `‹HOME_SCORE›`, `‹SUB›`). The pipeline
substitutes these before render. Use placeholders for names/scores/labels; hard-code only truly
fixed chrome (e.g. the show wordmark, a static "LIVE" tag). Numbers that animate: put the START
value in a placeholder and the END value in a second placeholder, and tween between them.

## MACU house style (mandatory — match the example's look)
- Pure black field (`#000`/`#0c0c10`), monochrome only. No color.
- Fonts: `Anton` (huge display/wordmarks) + `JetBrains Mono` (kickers, subs, stats, labels),
  loaded from Google Fonts in <head>.
- Always layer these four FX over the card (copy them from the example): an SVG `feTurbulence`
  grain at ~7% opacity, horizontal scanlines (`repeating-linear-gradient`, `mix-blend-mode:multiply`),
  an inset vignette (`box-shadow:inset …`), and a faint radial/concentric motif behind the content.
- The signature display-text fill is the striped clip: white `-webkit-text-stroke` + a
  `repeating-linear-gradient` background-clipped to the text.
- Tone is deadpan broadcast: dignified, slightly ominous, never cartoonish or neon.

## Motion guidance
- Stagger reveals (scale/opacity from), hold, then a subtle ambient move (slow rotation/drift).
- Eases: `power3.out` / `back.out(1.4)` for entrances; `none` for steady ambient motion.
- For a SCOREBOARD: lay out HOME vs AWAY with big Anton numbers; if a score changes, tween the
  number with an `onUpdate` that rounds to an integer; a brief flash/shake on the change sells it.
- For a WHEEL / carousel: a wrapper `rotation` tween that decelerates (`power4.out`) to a fixed
  final angle so it "lands" on a chosen wedge — angle chosen from the brief, never random.

## Worked example — study its structure, contract, and style, then write a NEW one
```html
<!doctype html><html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1024, height=1024"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:1024px;height:1024px;overflow:hidden;background:#000}
  #card{position:relative;width:1024px;height:1024px;background:#0c0c10;overflow:hidden;display:flex;align-items:center;justify-content:center}
  .stack{position:relative;text-align:center}
  .kicker{font-family:'JetBrains Mono',monospace;font-weight:500;letter-spacing:.4em;font-size:28px;color:#e8e8e8;opacity:.8;margin-bottom:26px}
  .macu-title{font-family:'Anton',sans-serif;line-height:.9;letter-spacing:.02em;-webkit-text-stroke:2px #f4f4f4;
    background-image:repeating-linear-gradient(to bottom,#f6f6f6 0 7px,transparent 7px 12px);
    -webkit-background-clip:text;background-clip:text;color:transparent;font-size:150px}
  .macu-title span{display:block}
  .sub{font-family:'JetBrains Mono',monospace;letter-spacing:.3em;font-size:24px;color:#cfcfcf;opacity:.72;margin-top:30px}
  .motif{position:absolute;left:50%;top:54%;width:1280px;height:1280px;transform:translate(-50%,-50%);border-radius:50%;
    background:repeating-radial-gradient(circle at center,rgba(216,216,216,.85) 0 2px,transparent 2px 54px);opacity:.15}
  .scrim{position:absolute;inset:0;background:radial-gradient(circle at 50% 46%,rgba(12,12,16,.86) 0 36%,rgba(12,12,16,.46) 70%,rgba(12,12,16,.05) 100%)}
  .scan{position:absolute;inset:0;mix-blend-mode:multiply;background:repeating-linear-gradient(to bottom,rgba(0,0,0,0) 0 3px,rgba(0,0,0,.28) 3px 5px)}
  .vig{position:absolute;inset:0;box-shadow:inset 0 0 200px 50px #000}
  .grain{position:absolute;inset:0;opacity:.07;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/></filter><rect width='220' height='220' filter='url(%23n)'/></svg>")}
  .idtag{position:absolute;bottom:22px;right:30px;font-family:'JetBrains Mono',monospace;font-size:22px;letter-spacing:.15em;color:#cfcfcf;opacity:.55}
  .card-layer{opacity:0}
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="6" data-width="1024" data-height="1024">
  <div id="card" class="clip" data-start="0" data-duration="6" data-track-index="1">
    <div class="card-layer">
      <div class="motif"></div><div class="scrim"></div>
      <div class="stack">
        <div class="kicker">‹KICKER›</div>
        <div class="macu-title"><span>‹TITLE_LINE_1›</span><span>‹TITLE_LINE_2›</span></div>
        <div class="sub">‹SUB›</div>
      </div>
    </div>
    <div class="grain"></div><div class="scan"></div><div class="vig"></div>
    <div class="idtag">‹IDTAG›</div>
  </div>
</div>
<script>
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.to(".card-layer",{opacity:1,duration:.35},0.2);
  tl.fromTo(".macu-title",{scale:1.12,opacity:0},{scale:1,opacity:1,duration:.5,ease:"back.out(1.4)"},0.3);
  tl.to(".motif",{rotation:8,duration:5,ease:"none"},0.4);
  window.__timelines["main"] = tl;
</script></body></html>
```

## Before you answer
- Re-check the contract: one `#root` (data-composition-id="main", correct duration), one `.clip`,
  one paused GSAP timeline on `window.__timelines["main"]`, no random/time/raf, placeholders for
  editable text, the four FX layers, 1024×1024.
- Output ONLY the final `index.html`."""

_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n|\n?```\s*$")
_PLACEHOLDER_RE = re.compile(r"‹([A-Z0-9_]+)›")
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,48}$")


def ensure_prompt_seeded() -> None:
    prompts.load_or_seed(prompts.COMPOSITION_FILE, SYSTEM)


def _strip_fences(s: str) -> str:
    """Drop a leading ```html / trailing ``` if the model wrapped its output."""
    s = s.strip()
    if s.startswith("```"):
        s = _FENCE_RE.sub("", s)
        s = re.sub(r"\n?```\s*$", "", s).strip()
    # If there's prose before the doctype, keep from the first <!doctype/<html.
    m = re.search(r"<!doctype html|<html", s, re.IGNORECASE)
    if m:
        s = s[m.start():]
    return s.strip()


def generate(slug: str, key: str, brief: str) -> dict:
    """Ask the local model to write a HyperFrames composition for `brief`, save it as the
    template named `key`, and return its placeholder field set. No manifest writes — the
    caller renders it via the normal new-title flow (submit_new)."""
    key = (key or "").strip()
    if not _NAME_RE.fullmatch(key):
        raise ValueError("key must be lowercase letters/digits/_/- (used as the composition name)")
    if not (brief or "").strip():
        raise ValueError("a brief is required")

    messages = [
        {"role": "system", "content": prompts.load_or_seed(prompts.COMPOSITION_FILE, SYSTEM)},
        {"role": "user", "content": f"Brief for the card (key `{key}`):\n\n{brief.strip()}\n\nReturn only the index.html."},
    ]
    llm.start()
    try:
        raw = llm.chat_text(messages, temperature=0.4)
    finally:
        llm.stop()

    html = _strip_fences(raw)
    # Minimal contract validation — fail loudly so the operator retries rather than render junk.
    missing = [s for s in ('data-composition-id', '__timelines', '<html', 'data-duration')
               if s not in html]
    if missing or len(html) < 400:
        raise RuntimeError(f"model output isn't a valid composition (missing: {missing or 'too short'})")

    template_dir = hyperframes.TEMPLATES / key
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "index.html").write_text(html)

    placeholders = sorted(set(_PLACEHOLDER_RE.findall(html)))
    fields = {p.lower(): "" for p in placeholders}

    # Create the title_asset so the card appears in the Graphics grid immediately (as an
    # unrendered card). The operator fills the placeholder fields + renders to finish it.
    m = manifest_mod.load(slug)
    m.setdefault("title_assets", {})[key] = {"source": "hyperframes", "composition": key, "fields": fields}
    manifest_mod.save(slug, m)

    return {
        "ok": True,
        "key": key,
        "composition": key,
        "fields": fields,
        "placeholders": placeholders,
        "bytes": len(html),
    }
