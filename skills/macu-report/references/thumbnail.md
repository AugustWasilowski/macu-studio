# MACU episode open (animated intro), thumbnail & end bumper — spec & templates

Every episode opens on a short **animated intro** and closes on a **bumper** that shows the NEXT episode's
title card — both built from Hyperframes comps in the locked MACU house style. This file is the recipe.

## The three assets (Max renders them and moves them into `episodes/<slug>/titles/`)

| file | size | used for |
|---|---|---|
| `intro.mp4` | **1024×1024** | the on-air **open** — the TONIGHT/MACU-Report animation resolving into THIS episode's title card (with flicker), then a hold |
| `thumb_wide.mp4` | **1920×1080** | source for the **YouTube thumbnail** — this episode's title card; the render auto-extracts `final/<slug>_thumb.png` |
| `next.mp4` | **1024×1024** | the **bumper** — the NEXT episode's title card (Friday: a generic "next week" card) |

`intro` and `next` are referenced by cue shots, so they go in the manifest's `title_assets`. `thumb_wide.mp4`
is consumed only by the render's still-extraction, not by a cue.

## How the bookends wire in (cue JSON: see manifest-schema.md)

- **Open `c00`** — `speaker:"WALTER"`, shot `{kind:title, asset:"intro"}`, `pad_seconds:2.0`, `no_subs:true`.
  Walter's VO is the double gag: **"The MACU Report! In black and white! Tonight's episode: <a DIFFERENT
  title than the card>."** Keep the animation (~5–6s) shorter than the VO so it plays in full, then the
  assembler clone-holds the title for the rest + the 2s pad. Add `c00` to the intro music bed.
- **Bumper (last cue)** — `speaker:"WALTER"`, shot `{kind:title, asset:"next"}`, `pad_seconds:1.5`,
  `no_subs:true`. VO: weekday *"Tune in for tomorrow's episode: <next subtitle>."*; Friday *"Tune in next week
  for a new installment of the Mayor Awesome Cinematic Universe!"* Add it to the outro bed.

### The two gags (Police-Squad lineage)

1. **"In black and white!"** — Police Squad! bragged it was *"IN COLOR!"*; we brag the opposite. Fixed every
   episode.
2. **Wrong title** — the card shows the title you and August chose; Walter announces a *different* one. Pull
   it from the *other* `youtube.txt` title options or a three-segment summary. The mismatch is the joke, which
   is why the open is `no_subs` (don't print Walter's wrong title — let the ear catch it against the card).

## Locked house style (monochrome — never use colour)

- **Canvas** `#0c0c10`; **palette** ink `#f4f4f4`, greys `#e8e8e8`/`#bdbdbd`/`#cfcfcf`, dark `#18181c`.
- **Fonts** (Google Fonts `<link>`): **Anton** (display), **JetBrains Mono** 500 (kicker / sub / idtag). The
  Hyperframes compiler fetches + injects both faces — ignore the lint `font_family_without_font_face` warning.
- **Striped title** (the signature): Anton, `-webkit-text-stroke:2px #f4f4f4`, fill = a clipped horizontal
  stripe (`repeating-linear-gradient(to bottom,#f6f6f6 0 7px,transparent 7px 12px)`, `-webkit-background-clip:text`).
- **One faint motif** behind a radial scrim (crater, moon, vending machine, market chart, tally marks,
  spotlight, …), built from CSS gradients, opacity ~.12–.18.
- **Three analog layers, last in the stack:** `.grain` (feTurbulence, .07) → `.scan` (multiply scanlines) →
  `.vig` (inset vignette). `idtag` bottom-right (`EP N • MACU` / `SPORTS • CH 13`).
- **The title-card flicker is back** (unlike the earlier looped-card idea): the title flickers in and settles.
  The intro plays once and holds, so a one-time entrance + flicker is correct.

## Template A — the animated `intro` comp (1024×1024)

Fill the `‹…›` slots (kicker / title lines / sub / motif / idtag). Phases: **TONIGHT** zoom → **on the** →
**THE MACU REPORT** wordmark → title card flickers in → hold.

```html
<!doctype html><html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1024, height=1024"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:1024px;height:1024px;overflow:hidden;background:#000}
  #card{position:relative;width:1024px;height:1024px;background:#0c0c10;overflow:hidden;
        display:flex;align-items:center;justify-content:center}
  .layer{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column}
  /* phase text */
  .tonight{font-family:'Anton',sans-serif;font-size:240px;letter-spacing:.02em;color:#f4f4f4;opacity:0}
  .onthe{font-family:'JetBrains Mono',monospace;letter-spacing:.5em;font-size:34px;color:#cfcfcf;opacity:0;padding-left:.5em}
  .wordmark{font-family:'Anton',sans-serif;font-size:150px;line-height:.9;text-align:center;opacity:0;
    -webkit-text-stroke:2px #f4f4f4;
    background-image:repeating-linear-gradient(to bottom,#f6f6f6 0 7px,transparent 7px 12px);
    -webkit-background-clip:text;background-clip:text;color:transparent}
  /* the title card (revealed last) */
  .card-layer{opacity:0}
  .motif{position:absolute;left:50%;top:54%;width:1280px;height:1280px;transform:translate(-50%,-50%);border-radius:50%;
    background:repeating-radial-gradient(circle at center,rgba(216,216,216,.85) 0 2px,transparent 2px 54px);opacity:.15}
  .scrim{position:absolute;inset:0;background:radial-gradient(circle at 50% 46%,rgba(12,12,16,.86) 0 36%,rgba(12,12,16,.46) 70%,rgba(12,12,16,.05) 100%)}
  .stack{position:relative;text-align:center}
  .kicker{font-family:'JetBrains Mono',monospace;font-weight:500;letter-spacing:.4em;font-size:28px;color:#e8e8e8;opacity:.8;margin-bottom:26px;padding-left:.4em}
  .macu-title{font-family:'Anton',sans-serif;line-height:.9;letter-spacing:.02em;-webkit-text-stroke:2px #f4f4f4;
    background-image:repeating-linear-gradient(to bottom,#f6f6f6 0 7px,transparent 7px 12px);
    -webkit-background-clip:text;background-clip:text;color:transparent;font-size:150px}
  .macu-title span{display:block}
  .sub{font-family:'JetBrains Mono',monospace;font-weight:500;letter-spacing:.3em;font-size:24px;color:#cfcfcf;opacity:.72;margin-top:30px;padding-left:.3em}
  /* analog layers + idtag (always on top) */
  .scan{position:absolute;inset:0;mix-blend-mode:multiply;background:repeating-linear-gradient(to bottom,rgba(0,0,0,0) 0 3px,rgba(0,0,0,.28) 3px 5px)}
  .vig{position:absolute;inset:0;box-shadow:inset 0 0 200px 50px #000}
  .grain{position:absolute;inset:0;opacity:.07;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/></filter><rect width='220' height='220' filter='url(%23n)'/></svg>")}
  .idtag{position:absolute;bottom:22px;right:30px;font-family:'JetBrains Mono',monospace;font-size:22px;letter-spacing:.15em;color:#cfcfcf;opacity:.55}
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="6" data-width="1024" data-height="1024">
  <div id="card" class="clip" data-start="0" data-duration="6" data-track-index="1">
    <!-- title card (revealed at ~3s) -->
    <div class="layer card-layer">
      <div class="motif"></div><div class="scrim"></div>
      <div class="stack">
        <div class="kicker">‹KICKER — e.g. TONIGHT'S BULLETIN›</div>
        <div class="macu-title"><span>‹TITLE LINE 1›</span><span>‹TITLE LINE 2›</span></div>
        <div class="sub">‹SUB — one wry line›</div>
      </div>
    </div>
    <!-- animated phases -->
    <div class="layer"><div class="tonight">TONIGHT</div></div>
    <div class="layer"><div class="onthe">ON THE</div></div>
    <div class="layer"><div class="wordmark">THE MACU<br>REPORT</div></div>
    <!-- analog overlays -->
    <div class="grain"></div><div class="scan"></div><div class="vig"></div>
    <div class="idtag">EP ‹N› &#8226; MACU</div>
  </div>
</div>
<script>
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  // 1) TONIGHT zoom-in
  tl.fromTo(".tonight",{scale:1.8,opacity:0},{scale:1,opacity:1,duration:.6,ease:"power3.out"},0.1)
    .to(".tonight",{opacity:0,duration:.3},1.3);
  // 2) on the
  tl.fromTo(".onthe",{opacity:0},{opacity:1,duration:.3},1.4).to(".onthe",{opacity:0,duration:.3},2.0);
  // 3) THE MACU REPORT wordmark slam
  tl.fromTo(".wordmark",{scale:1.15,opacity:0},{scale:1,opacity:1,duration:.45,ease:"back.out(1.4)"},1.9)
    .to(".wordmark",{opacity:0,duration:.35},2.9);
  // 4) title card reveal + signature flicker, then hold
  tl.to(".card-layer",{opacity:1,duration:.35},3.0);
  tl.to(".macu-title",{opacity:.78,duration:.05,repeat:5,yoyo:true},3.3).to(".macu-title",{opacity:1,duration:.05},3.65);
  tl.to(".motif",{rotation:8,duration:2.3,ease:"none"},3.4);   // subtle drift on the hold
  window.__timelines["main"] = tl;
</script></body></html>
```

## Template B — the plain title card (for `thumb_wide` and `next`)

The same card as the end of Template A, standalone, with the entrance flicker. Use it for:
- **`thumb_wide.mp4`** — at **1920×1080**: set `width=1920,height=1080`, the `html/body/#card`/`#root` to
  `1920×1080`, and wrap `.stack` in `<div style="transform:scale(1.4)">…</div>` to fill the wide frame. (Worked
  examples: the `macu-thumb-ep05…ep15` comps on the Hyperframes workspace — square + wide.)
- **`next.mp4`** — at **1024×1024**, built from the **NEXT** episode's title (kicker/title/sub/motif). On
  **Friday**, build a generic card instead: kicker `NEXT WEEK`, title `THE MACU REPORT`, sub `A NEW
  INSTALLMENT OF THE MAYOR AWESOME CINEMATIC UNIVERSE`.

Keep the one-time flicker entrance (`from opacity:0` / a short `repeat:yoyo` on `.macu-title`, settle to 1) —
these cards play once and clone-hold, so an entrance is correct.

## Render & place (Hyperframes on Max)

```
create_composition  name="macu-intro-<slug>"        --example blank   ; write Template A (this episode's title)
render_composition  name="macu-intro-<slug>"        --output renders/intro.mp4 --fps 8 --quality high
create_composition  name="macu-thumb-<slug>-wide"   --example blank   ; write Template B @ 1920×1080
render_composition  name="macu-thumb-<slug>-wide"   --output renders/thumb_wide.mp4 --fps 8 --quality high
create_composition  name="macu-next-<slug>"         --example blank   ; write Template B (NEXT ep title, or Friday card)
render_composition  name="macu-next-<slug>"         --output renders/next.mp4 --fps 8 --quality high
```

Then **Max moves** the three renders into `episodes/<slug>/titles/` as `intro.mp4`, `thumb_wide.mp4`,
`next.mp4` (same Max-side copy step as any title asset — call it out in the Vikunja handoff). The render loops
in the rest: it plays `intro.mp4` under Walter's open and holds, plays `next.mp4` under the bumper, and writes
`final/<slug>_thumb.png` (1920×1080) from `thumb_wide.mp4` for YouTube.
