#!/usr/bin/env python3
"""Stage 4b: composite spanning title-card graphics onto the assembled video.

Reads manifest.overlays[] (the video twin of music beds — see Overlay model) and
rewrites .work/<slug>_nosubs.mp4 IN PLACE with each graphic baked in. Keeps a clean
snapshot at .work/<slug>_nosubs_clean.mp4 so re-applying after an overlay edit never
needs a full re-assemble. The audio plane is left untouched (`-c:a copy`), so stage 5
(music mix, -c:v copy), stage 6 (whisper off clean VO), and stage 8 (sub burn) all
consume nosubs exactly as before — zero downstream changes.

Two placement modes per overlay:
  insert  — full-frame card REPLACES the footage for [start,end] (works with the
            existing opaque 1024x1024 cards). Pre-rendered to the window length via
            stage_4's title_shot(), then overlaid full-frame with a between() gate.
  overlay — alpha card composited ON TOP of the footage (lower-third/bug/chyron).
            Needs an alpha-capable asset (<asset>.webm / .mov); see stage 5 / the
            HyperFrames alpha export. Skipped with a warning if no alpha asset exists.

Timing mirrors stage_5_music: start_s = cum[anchor_cue] + start_offset, where cum is
the cumulative per-cue offset from .work/cue_durs.json.

Invoked automatically at the tail of stage 4; also runnable standalone for testing:
    python3 stage_4b_graphics.py <slug>
"""
import sys, os, json, shutil, time
sys.path.insert(0, os.path.dirname(__file__))
from lib import episode_paths, load_manifest, probe_dur, run
from stage_4_assemble import title_shot

SHARES = "/mnt/storage/shares/MACU"

# overlay-mode screen positions → ffmpeg overlay x:y expressions (W/H base, w/h card)
_POS = {
    "lower_third": ("(W-w)/2", "H-h-72"),
    "bug_tl":      ("48", "48"),
    "bug_tr":      ("W-w-48", "48"),
    "center":      ("(W-w)/2", "(H-h)/2"),
    "full":        ("0", "0"),
}


def _cum_offsets(m, cue_durs):
    cum, t = {}, 0.0
    for cue in m["cues"]:
        cum[cue["id"]] = t
        t += float(cue_durs.get(cue["id"], 0.0))
    return cum, t


def _card_path(p, asset, alpha=False):
    """Per-episode titles dir wins; fall back to shared assets/titles/. For alpha
    (overlay) mode prefer a .webm/.mov; for insert use the opaque .mp4."""
    exts = ([".webm", ".mov"] if alpha else [".mp4"])
    for base in (p["titles"], f"{SHARES}/assets/titles"):
        for ext in exts:
            cand = f"{base}/{asset}{ext}"
            if os.path.exists(cand):
                return cand
    return None


def apply(slug, refresh_clean=False):
    """Bake manifest.overlays[] into nosubs. refresh_clean=True snapshots the current
    (just-assembled) nosubs as the clean base first — set by stage 4. Standalone runs
    reuse an existing clean snapshot so they don't need a fresh assemble."""
    p = episode_paths(slug)
    m = load_manifest(slug)
    overlays = [o for o in (m.get("overlays") or []) if isinstance(o, dict) and o.get("asset")]
    nosubs, clean = p["nosubs"], p["nosubs_clean"]
    warnings = []

    if not overlays:
        # No graphics: leave nosubs as-is (clean snapshot is irrelevant). If a clean
        # snapshot exists from a prior overlay run, restore it so removing all overlays
        # cleanly reverts the baked-in graphics.
        if os.path.exists(clean) and os.path.exists(nosubs):
            shutil.copy2(clean, nosubs)
        return {"overlays": 0, "applied": 0, "warnings": warnings}

    if not os.path.exists(nosubs):
        raise FileNotFoundError(f"stage 4b: {nosubs} missing — run stage 4 first")
    if refresh_clean or not os.path.exists(clean):
        shutil.copy2(nosubs, clean)

    cd_path = f"{p['work']}/cue_durs.json"
    cue_durs = json.load(open(cd_path)) if os.path.exists(cd_path) else {}
    if not cue_durs:  # fall back to probing the per-cue VO
        for cue in m["cues"]:
            vo = f"{p['vo']}/{cue['id']}.wav"
            cue_durs[cue["id"]] = probe_dur(vo) if os.path.exists(vo) else 0.0
    cum, total = _cum_offsets(m, cue_durs)

    start = time.time()
    inputs = ["-i", clean]
    fc = []        # filter_complex parts
    prev = "[0:v]"
    n_applied = 0
    insert_spans = []  # (start,end) for overlap warning

    for ov in overlays:
        anchor = ov.get("anchor_cue")
        if anchor not in cum:
            warnings.append(f"overlay '{ov.get('id') or ov['asset']}': anchor '{anchor}' not a cue — skipped")
            continue
        s = cum[anchor] + float(ov.get("start_offset") or 0.0)
        dur = float(ov.get("duration") or 0.0)
        e = min(s + dur, total)
        wl = e - s
        if wl <= 0.05:
            warnings.append(f"overlay '{ov.get('id') or ov['asset']}': zero-length — skipped")
            continue
        mode = ov.get("mode") or "insert"
        fi = max(0.0, float(ov.get("fade_in") or 0.0))
        fo = max(0.0, float(ov.get("fade_out") or 0.0))

        if mode == "overlay":
            # Prefer a true-alpha asset (<asset>.webm/.mov from the HyperFrames alpha
            # export). Otherwise fall back to keying black out of the opaque card —
            # MACU cards are white-on-black, so colorkey composites just the
            # text/graphics over the footage. Cheap, works with every existing card.
            card = _card_path(p, ov["asset"], alpha=True)
            keyblack = False
            if not card:
                card = _card_path(p, ov["asset"], alpha=False)
                keyblack = True
            if not card:
                warnings.append(f"overlay '{ov.get('id') or ov['asset']}': no asset for '{ov['asset']}' — skipped")
                continue
            # loop the card to fill the window; gate by enable.
            idx = len(inputs) // 2  # next input index
            inputs += ["-stream_loop", "-1", "-i", card]
            scale = float(ov.get("scale") or 1.0)
            opacity = float(ov.get("opacity") or 1.0)
            px, py = _POS.get(ov.get("position") or "lower_third", _POS["lower_third"])
            key = "colorkey=0x000000:0.16:0.06," if keyblack else ""
            chain = f"[{idx}:v]{key}format=yuva420p,scale=iw*{scale}:-1"
            if opacity < 0.999:
                chain += f",colorchannelmixer=aa={opacity}"
            if fi > 0:
                chain += f",fade=t=in:st=0:d={fi}:alpha=1"
            if fo > 0:
                chain += f",fade=t=out:st={max(0.0, wl - fo):.4f}:d={fo}:alpha=1"
            chain += f",setpts=PTS-STARTPTS+{s:.4f}/TB[g{idx}]"
            fc.append(chain)
            fc.append(f"{prev}[g{idx}]overlay={px}:{py}:enable='between(t,{s:.4f},{e:.4f})':eof_action=pass[v{idx}]")
            prev = f"[v{idx}]"
            n_applied += 1
            continue

        # insert mode (full-frame opaque) — pre-render the card to exactly the window.
        card = _card_path(p, ov["asset"], alpha=False)
        if not card:
            warnings.append(f"overlay '{ov.get('id') or ov['asset']}': card '{ov['asset']}.mp4' not found — skipped")
            continue
        insert_spans.append((s, e))
        sid = f"ovins_{n_applied}"
        prerend = title_shot(card, sid, wl, p["work"], loop=False)  # 1024x1024, silent, wl seconds
        idx = len(inputs) // 2
        inputs += ["-i", prerend]
        chain = f"[{idx}:v]format=yuva420p,scale=1024:1024"
        if fi > 0:
            chain += f",fade=t=in:st=0:d={fi}:alpha=1"
        if fo > 0:
            chain += f",fade=t=out:st={max(0.0, wl - fo):.4f}:d={fo}:alpha=1"
        chain += f",setpts=PTS-STARTPTS+{s:.4f}/TB[g{idx}]"
        fc.append(chain)
        fc.append(f"{prev}[g{idx}]overlay=0:0:enable='between(t,{s:.4f},{e:.4f})':eof_action=pass[v{idx}]")
        prev = f"[v{idx}]"
        n_applied += 1

    # warn on overlapping inserts (ambiguous footage replacement)
    insert_spans.sort()
    for (a0, a1), (b0, b1) in zip(insert_spans, insert_spans[1:]):
        if b0 < a1 - 0.01:
            warnings.append(f"insert graphics overlap at ~{b0:.1f}s — later one wins")

    if n_applied == 0:
        # everything skipped; revert to clean
        shutil.copy2(clean, nosubs)
        return {"overlays": len(overlays), "applied": 0, "warnings": warnings}

    tmp = f"{p['work']}/{slug}_gfx.mp4"
    cmd = ["ffmpeg", "-y", *inputs,
           "-filter_complex", ";".join(fc),
           "-map", prev, "-map", "0:a?",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "24",
           "-c:a", "copy", "-movflags", "+faststart", tmp]
    run(cmd)
    shutil.move(tmp, nosubs)
    info = {"overlays": len(overlays), "applied": n_applied,
            "warnings": warnings, "wall_s": round(time.time() - start, 2)}
    print(f"[stage 4b graphics] baked {n_applied}/{len(overlays)} overlay(s) into {nosubs}"
          + (f" · warnings: {warnings}" if warnings else ""))
    return info


def main(slug):
    return apply(slug, refresh_clean=False)


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), indent=2))
