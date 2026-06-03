#!/usr/bin/env python3
"""Validate a MACU episode manifest before handing it to Max.

Checks structure, the locked render settings, and referential integrity (every shot points at a real
character / broll / title asset, seeds line up, ids are unique, music beds name real cues). Catches the
slow-to-debug mistakes before a render is kicked off.

Usage:  python validate_manifest.py episodes/<slug>/manifest.json
Exit 0 = clean, exit 1 = errors found. Warnings don't fail the build but are worth a look.
"""
import json, sys

LOCKED_COMFYUI = {"checkpoint": "zeroscope_v2_576w", "width": 384, "height": 384,
                  "frames": 24, "steps": 30, "cfg": 15}


def main(path):
    errors, warnings = [], []
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except Exception as e:
        print(f"FATAL: could not parse JSON: {e}")
        return 1

    # --- required top-level keys ---
    for key in ("episode", "voice", "comfyui", "style", "characters", "broll", "cues",
                "title_assets", "music", "subtitles"):
        if key not in m:
            errors.append(f"missing top-level key: {key}")
    if errors:
        for e in errors:
            print("ERROR:", e)
        return 1

    # --- locked render settings ---
    cy = m["comfyui"]
    for k, v in LOCKED_COMFYUI.items():
        if cy.get(k) != v:
            errors.append(f"comfyui.{k} = {cy.get(k)!r}, expected locked value {v!r}")

    # --- style ---
    if "shutterstock" not in m["style"].get("negative", ""):
        warnings.append("style.negative is missing 'shutterstock' (belt-and-suspenders; keep it)")

    chars, broll = m["characters"], m["broll"]
    titles = set(m.get("title_assets", {}))

    # --- characters need seed + core ---
    for k, c in chars.items():
        if "seed" not in c:
            errors.append(f"character '{k}' has no seed")
        if not c.get("core"):
            errors.append(f"character '{k}' has no core prompt")

    # --- cues / shots ---
    cue_ids, shot_ids = set(), set()
    for cue in m["cues"]:
        cid = cue.get("id")
        if not cid:
            errors.append("a cue has no id")
            continue
        if cid in cue_ids:
            errors.append(f"duplicate cue id: {cid}")
        cue_ids.add(cid)
        if not cue.get("vo"):
            warnings.append(f"cue {cid} has empty vo (no speech / no subtitle)")
        if not cue.get("shots"):
            errors.append(f"cue {cid} has no shots")
        for sh in cue.get("shots", []):
            sid = sh.get("id")
            if not sid:
                errors.append(f"cue {cid} has a shot with no id")
            elif sid in shot_ids:
                errors.append(f"duplicate shot id: {sid}")
            else:
                shot_ids.add(sid)
            kind = sh.get("kind")
            if kind == "character":
                who = sh.get("who")
                if who not in chars:
                    errors.append(f"shot {sid}: character '{who}' not in characters{{}}")
                else:
                    want = chars[who]["seed"]
                    if sh.get("seed", want) != want:
                        warnings.append(f"shot {sid}: seed {sh['seed']} overrides character "
                                        f"'{who}' default {want} (intentional? fine if so)")
            elif kind == "broll":
                if sh.get("who") not in broll:
                    errors.append(f"shot {sid}: broll '{sh.get('who')}' not in broll{{}}")
            elif kind == "title":
                if sh.get("asset") not in titles:
                    errors.append(f"shot {sid}: title asset '{sh.get('asset')}' not in title_assets{{}}")
            else:
                errors.append(f"shot {sid}: unknown kind {kind!r} (use character|broll|title)")

    # --- voice speaker_map coverage (soft: unmapped speakers fall back to default Piper HAL) ---
    smap = m.get("voice", {}).get("speaker_map", {})
    for sp in sorted({cue.get("speaker") for cue in m["cues"] if cue.get("speaker")}):
        entry = smap.get(sp)
        if entry is None:
            warnings.append(f"speaker '{sp}' has no voice.speaker_map entry — falls back to default (Piper HAL)")
        elif entry.get("engine") == "omnivoice" and not entry.get("profile_id"):
            errors.append(f"speaker '{sp}' is engine=omnivoice but has no profile_id")

    # --- music beds reference real cues ---
    for bed in m.get("music", {}).get("beds", []):
        for c in bed.get("cues", []):
            if c not in cue_ids:
                errors.append(f"music bed '{bed.get('name')}' references unknown cue '{c}'")

    # --- standard episode bookends (soft — see references/thumbnail.md) ---
    intro_cue = next((c for c in m["cues"]
                      if c.get("segment") == "intro" or c.get("no_subs")), None)
    if intro_cue is None:
        warnings.append("no intro cue — expected a front WALTER cue with an 'intro' title shot, "
                        "pad_seconds, no_subs:true (the animated open).")
    else:
        intro_shots = [s for s in intro_cue.get("shots", [])
                       if s.get("kind") == "title" and s.get("asset") in ("intro", "thumb")]
        if not intro_shots:
            warnings.append("intro cue has no {kind:title, asset:'intro'} shot")
        else:
            for s in intro_shots:
                if s.get("asset") not in titles:
                    errors.append(f"intro references title asset '{s.get('asset')}' not in title_assets{{}}")
        if not intro_cue.get("no_subs"):
            warnings.append("intro cue should set no_subs:true (the card shows the title; the gag is in the VO)")
    # closing bumper: a WALTER cue near the end teasing next (over the 'next' card)
    tail = m["cues"][-3:] if len(m["cues"]) >= 3 else m["cues"]
    if not any(c.get("speaker") == "WALTER"
               and ("tune in" in (c.get("vo") or "").lower()
                    or "stay tuned" in (c.get("vo") or "").lower()
                    or "next week" in (c.get("vo") or "").lower())
               for c in tail):
        warnings.append("no Walter next-episode bumper near the end — weekday: \"Tune in for tomorrow's "
                        "episode: <Subtitle>\" over the 'next' card; Friday: \"Tune in next week for a new "
                        "installment of the Mayor Awesome Cinematic Universe!\"")

    # --- report ---
    n_char = sum(1 for cue in m["cues"] for sh in cue["shots"] if sh.get("kind") == "character")
    n_broll = sum(1 for cue in m["cues"] for sh in cue["shots"] if sh.get("kind") == "broll")
    n_title = sum(1 for cue in m["cues"] for sh in cue["shots"] if sh.get("kind") == "title")
    unique_masters = len({sh["who"] for cue in m["cues"] for sh in cue["shots"]
                          if sh.get("kind") in ("character", "broll")})

    for w in warnings:
        print("WARN:", w)
    for e in errors:
        print("ERROR:", e)
    print(f"\n{m['episode']}: {len(m['cues'])} cues, "
          f"{n_char} character + {n_broll} broll + {n_title} title shots, "
          f"~{unique_masters} unique masters to generate.")
    if errors:
        print(f"\n{len(errors)} error(s) — fix before handoff.")
        return 1
    print(f"\nOK{' (with ' + str(len(warnings)) + ' warning(s))' if warnings else ''}. Ready for Max.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
