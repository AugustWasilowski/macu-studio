#!/usr/bin/env python3
"""Dub driver for the Localize feature — translate + re-VO + remux + burn, WITHOUT
re-rendering the (expensive) picture.

Because each dubbed cue wav is fit to the original cue's duration, the already-rendered
picture and the music/SFX offsets stay valid. So a dub is:
  D1 translate  cue VO text + the final SRT entries -> target language
  D2 re-VO      per cue, cloned-voice TTS in the target language, fit-to-duration
  D3+D4 remux   place dubbed cues at their cue offsets + the SAME cached music/SFX beds
                onto the existing picture (video stream copied, never re-encoded)
  D5 SRT        rewrite the English SRT text in place (timestamps unchanged)
  D6 burn       burn the translated SRT -> final/<slug>.<lang>.mp4

Stages 2 (masters) and 3 (RIFE) are skipped entirely. Precondition: a completed English
render (the picture + final/<slug>.srt + the cached music bed wavs) must already exist.

Invoked by run.py --dub <lang> --engine <qwen|argos> [--subs-only]; events go through the
caller's emit() so the Studio Assembly page streams progress over the same SSE channel.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib import (episode_paths, dub_paths, load_manifest, probe_dur, run,
                 omnivoice_start, omnivoice_stop)
import translate as translate_mod
import stage_1_vo
import stage_8_burn
import llm_ollama


# ---------------------------------------------------------------------------
# Glossary — proper nouns to keep verbatim, derived from THIS episode's manifest
# (no hardcoded show names → the public pipeline stays show-agnostic). Persisted to
# loc/glossary.json on first run; edit that file to add place/name terms.
# ---------------------------------------------------------------------------

def build_glossary(m):
    names = set()
    sm = (m.get("voice") or {}).get("speaker_map") or {}
    for v in sm.values():
        if isinstance(v, dict) and (v.get("voice_name") or "").strip():
            names.add(v["voice_name"].strip())
    for k in (m.get("characters") or {}):
        if isinstance(k, str) and k and k[0:1].isupper() and " " not in k[:1]:
            names.add(k.strip())
    return [{"source": n, "target": n} for n in sorted(names) if 0 < len(n) < 40]


def _load_or_build_glossary(m, path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                g = json.load(f)
            if isinstance(g, list):
                return g
        except Exception:
            pass
    g = build_glossary(m)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)
    return g


# ---------------------------------------------------------------------------
# SRT parse / write (timestamps preserved; only text is translated)
# ---------------------------------------------------------------------------

def parse_srt(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        blocks = f.read().strip().split("\n\n")
    for b in blocks:
        lines = [ln for ln in b.splitlines() if ln.strip() != ""]
        if len(lines) < 2:
            continue
        idx = lines[0].strip()
        timing = lines[1].strip()
        text = "\n".join(lines[2:]).strip()
        entries.append({"idx": idx, "timing": timing, "text": text})
    return entries


def write_srt(path, entries):
    out = []
    for e in entries:
        out.append(f"{e['idx']}\n{e['timing']}\n{e['text']}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def _load_translations(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_translations(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Subtitle font fallback for non-Latin scripts (Better VCR is Latin-only).
# Returns a Noto family if one is installed for the locale's script, else None
# (keep the manifest font). Langs whose Noto family isn't installed will tofu —
# bundle the family under assets/fonts to fix.
# ---------------------------------------------------------------------------

_SCRIPT_FONT = {
    "zh-Hans": "Noto Sans CJK SC", "zh-Hant": "Noto Sans CJK TC", "ja": "Noto Sans CJK JP",
    "ko": "Noto Sans CJK KR", "ar": "Noto Sans Arabic", "fa": "Noto Sans Arabic",
    "ur": "Noto Sans Arabic", "he": "Noto Sans Hebrew", "hi": "Noto Sans Devanagari",
    "mr": "Noto Sans Devanagari", "bn": "Noto Sans Bengali", "ta": "Noto Sans Tamil",
    "te": "Noto Sans Telugu", "gu": "Noto Sans Gujarati", "kn": "Noto Sans Kannada",
    "ml": "Noto Sans Malayalam", "pa": "Noto Sans Gurmukhi", "th": "Noto Sans Thai",
    "el": "Noto Sans", "uk": "Noto Sans", "am": "Noto Sans Ethiopic",
}


def _font_for_lang(lang):
    fam = _SCRIPT_FONT.get(lang)
    if not fam:
        return None
    try:
        r = subprocess.run(["fc-list", "-q", f":family={fam}"], capture_output=True)
        return fam if r.returncode == 0 else None
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# D3+D4 remux — picture (video copy) + dubbed cues at cue offsets + cached beds/SFX
# ---------------------------------------------------------------------------

def _remux(slug, lang, dialogue, pic):
    p = episode_paths(slug)
    d = dub_paths(slug, lang)
    m = load_manifest(slug)
    total = probe_dur(pic)

    cdurs_path = f"{p['work']}/cue_durs.json"
    if os.path.exists(cdurs_path):
        with open(cdurs_path) as f:
            cue_dur = json.load(f)
    else:
        cue_dur = {c["id"]: probe_dur(f"{p['work']}/{c['id']}.mp4") for c in m["cues"]}
    cum = {}
    t = 0.0
    for cue in m["cues"]:
        cum[cue["id"]] = t
        t += cue_dur[cue["id"]]

    placed = []  # (wav, delay_ms)
    for cue in dialogue:
        w = f"{d['vo_dir']}/{cue['id']}.wav"
        if os.path.exists(w):
            placed.append((w, int(round(cum[cue["id"]] * 1000))))

    # Reuse the EXACT cached music beds + SFX wavs at their recorded offsets (no random
    # re-roll) so the dub's bed/SFX placement is identical to the English mix.
    report_path = f"{p['music_dir']}/music_report.json"
    if os.path.exists(report_path):
        with open(report_path) as f:
            rep = json.load(f)
        for b in rep.get("beds", []):
            w = f"{p['music_dir']}/{b['name']}.wav"
            if os.path.exists(w):
                placed.append((w, int(b.get("delay_ms", 0))))
        for s in rep.get("sfx", []):
            if s.get("skipped"):
                continue
            name = os.path.splitext(s["file"])[0]
            w = f"{p['music_dir']}/sfx_{name}_{s['cue']}_{s.get('at', 'start')}.wav"
            if os.path.exists(w):
                placed.append((w, int(s.get("delay_ms", 0))))

    inputs = ["-i", pic, "-f", "lavfi", "-t", f"{total:.4f}", "-i", "anullsrc=r=24000:cl=mono"]
    for w, _ in placed:
        inputs += ["-i", w]
    streams = []
    labels = []
    for i, (_w, delay) in enumerate(placed, start=2):
        streams.append(f"[{i}:a]adelay={delay}:all=1,aresample=24000[s{i}]")
        labels.append(f"[s{i}]")
    mix = "[1:a]" + "".join(labels) + f"amix=inputs={1 + len(placed)}:normalize=0[a]"
    fc = ";".join(streams + [mix])
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
         "-filter_complex", fc,
         "-map", "0:v", "-c:v", "copy",
         "-map", "[a]", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", d["dub_music_nosubs"]])


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _noop_emit(kind, **payload):
    print(f"[dub] {kind} {payload}")


def run_dub(slug, lang, engine, subs_only=False, emit=None):
    emit = emit or _noop_emit
    p = episode_paths(slug)
    d = dub_paths(slug, lang)
    m = load_manifest(slug)

    pic = p["music_nosubs"] if os.path.exists(p["music_nosubs"]) else p["nosubs"]
    if not (os.path.exists(pic) and os.path.exists(p["out_srt"])):
        emit("job.error", error="no completed English render — render the episode (picture + SRT) first")
        return 1

    os.makedirs(d["loc_dir"], exist_ok=True)
    os.makedirs(os.path.dirname(d["out_mp4"]), exist_ok=True)
    glossary = _load_or_build_glossary(m, d["glossary"])

    dialogue = [c for c in m["cues"]
                if c.get("hold_seconds") is None and (c.get("vo") or "").strip()]
    cue_items = [{"id": c["id"], "text": c["vo"]} for c in dialogue]
    srt_entries = parse_srt(p["out_srt"])
    srt_items = [{"id": f"s{e['idx']}", "text": e["text"]} for e in srt_entries]

    # ---- D1 translate (cache by engine) ----
    emit("dub.stage.started", step="translate", lang=lang, engine=engine)
    cache = _load_translations(d["translations"])
    cue_tr = cache.get("cues", {}) if cache.get("engine") == engine else {}
    srt_tr = cache.get("srt", {}) if cache.get("engine") == engine else {}
    need_cue = [it for it in cue_items if it["id"] not in cue_tr]
    need_srt = [it for it in srt_items if it["id"] not in srt_tr]

    if need_cue or need_srt:
        if engine == "qwen":
            llm_ollama.start()
            close = llm_ollama.stop
        else:
            omnivoice_start()
            close = omnivoice_stop
        try:
            if need_cue:
                cue_tr.update(translate_mod.translate(need_cue, lang, engine, glossary))
            if need_srt:
                srt_tr.update(translate_mod.translate(need_srt, lang, engine, glossary))
        finally:
            close()
    _save_translations(d["translations"], {"engine": engine, "lang": lang,
                                            "cues": cue_tr, "srt": srt_tr})
    emit("dub.stage.done", step="translate", lang=lang, cues=len(cue_tr), srt=len(srt_tr))

    burn_src = pic
    if not subs_only:
        # ---- D2 re-VO ----
        emit("dub.stage.started", step="vo", lang=lang)
        ov_lang = translate_mod.omnivoice_language(lang)
        stats = stage_1_vo.dub_vo(
            slug, lang, cue_tr, ov_lang,
            progress=lambda done, tot: emit("dub.progress", step="vo", done=done, total=tot))
        emit("dub.stage.done", step="vo", lang=lang, **stats)

        # ---- D3+D4 remux ----
        emit("dub.stage.started", step="mix", lang=lang)
        _remux(slug, lang, dialogue, pic)
        emit("dub.stage.done", step="mix", lang=lang)
        burn_src = d["dub_music_nosubs"]

    # ---- D5 SRT ----
    emit("dub.stage.started", step="srt", lang=lang)
    for e in srt_entries:
        e["text"] = srt_tr.get(f"s{e['idx']}") or e["text"]
    write_srt(d["out_srt"], srt_entries)
    emit("dub.stage.done", step="srt", lang=lang, srt=d["out_srt"])

    # ---- D6 burn ----
    emit("dub.stage.started", step="burn", lang=lang)
    res = stage_8_burn.main(slug, src=burn_src, srt=d["out_srt"], final=d["out_mp4"],
                            font=_font_for_lang(lang)) or {}
    emit("dub.stage.done", step="burn", lang=lang, **{k: res[k] for k in ("size_mb", "font_used") if k in res})

    final_dur = None
    try:
        final_dur = round(probe_dur(d["out_mp4"]), 2)
    except Exception:
        pass
    emit("job.done", lang=lang, subs_only=subs_only,
         final=d["out_mp4"], srt=d["out_srt"],
         final_size_mb=res.get("size_mb"), final_duration_s=final_dur)
    return 0


if __name__ == "__main__":
    # python3 dub.py <slug> <lang> [engine] [--subs-only]
    a = sys.argv
    slug = a[1]
    lang = a[2]
    engine = a[3] if len(a) > 3 and not a[3].startswith("--") else "qwen"
    subs = "--subs-only" in a
    sys.exit(run_dub(slug, lang, engine, subs_only=subs))
