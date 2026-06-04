"""Generate a manifest's `cues` from script.md, merging into the existing
manifest (everything else — voice/characters/broll/comfyui/style/music/title
assets — is preserved).

Script grammar (see episodes/*/script.md):
  ## SEGMENT HEADER          -> segment boundary (slug inherited from old manifest
                                by VO match; freshly slugified + warned otherwise)
  **SPEAKER:** dialogue …     -> one cue; dialogue may wrap across lines until the
                                next `»`, blank line, `**`, or `##`
  » Foo core → b-roll: bar → BAZ title card
                              -> shots for that cue, in written order. `X core` =>
                                character shot (who resolved against manifest.characters,
                                seed copied); `b-roll: X` => broll shot; `… card`/`… bumper`
                                => title shot (asset matched against manifest.title_assets).
                                When a cue has no `»`, it gets one character shot for its
                                speaker.

This is a heuristic, surfaced through a preview/diff before anything is written.
"""
from __future__ import annotations
import copy, re, shutil, time
from typing import Any

from .episodes import episode_dir, manifest_path
from . import manifest as manifest_mod

SEG_RE = re.compile(r"^##\s+(.*\S)\s*$")
SPEAKER_RE = re.compile(r"^\*\*([^*:]+):\*\*\s*(.*)$")
SHOT_RE = re.compile(r"^»\s*(.*)$")
END_RE = re.compile(r"^###\s")  # trailer sections (Shot tally / Arc) end the body


# ---------- text helpers ----------

def _clean_vo(text: str) -> str:
    text = re.sub(r"_\([^)]*\)_", " ", text)        # _(beat)_  _(HAL)_  _(thrilled)_
    text = re.sub(r"^\s*\([^)]*\)\s*", " ", text)   # leading (voiceover)
    return re.sub(r"\s+", " ", text).strip()


def _norm(text: str) -> str:
    """Normalized VO key for matching cues across script edits. Punctuation and
    case are dropped (the manifest VO is hand-cleaned for TTS), and whitespace is
    collapsed so a removed em-dash doesn't leave a phantom double space."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def _slug(s: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", s.lower())).strip("_")


def _slug_segment(header: str) -> str:
    h = re.sub(r"^segment\s+\d+\s*[—\-:]*\s*", "", header.strip(), flags=re.I)
    h = re.sub(r"\([^)]*\)", " ", h)                # drop (callback)
    h = h.split("—")[0].split("/")[0].strip(' "“”')  # first clause
    words = [w for w in re.split(r"\s+", _slug(h).replace("_", " ")) if w]
    return "_".join(words[:3]) or _slug(header)[:24]


# ---------- shot resolution ----------

def _resolve_character(name: str, characters: dict) -> str | None:
    s = _slug(name)
    if s in characters:
        return s
    # last word then first word (THE VENDOR -> vendor, BUCK BOUNTIFUL -> buck)
    parts = [p for p in re.split(r"[\s_]+", s) if p and p != "the"]
    for cand in (parts[-1:] + parts[:1]):
        if cand in characters:
            return cand
    for key in characters:
        if key in parts:
            return key
    return None


def _resolve_broll(name: str, broll: dict) -> str | None:
    s = _slug(name)
    if s in broll:
        return s
    toks = set(s.split("_"))
    best, score = None, 0
    for key in broll:
        ov = len(toks & set(key.split("_")))
        if ov > score:
            best, score = key, ov
    return best if score else None


def _resolve_title(desc: str, title_assets: dict) -> str | None:
    toks = set(_slug(desc).split("_"))
    best, score = None, 0
    for key in title_assets:
        ov = len(toks & set(key.split("_")))
        if ov > score:
            best, score = key, ov
    return best if score else None


def _parse_shot_line(line: str, speaker_who: str | None, manifest: dict,
                     warnings: list[str], cue_id: str) -> list[dict]:
    characters = manifest.get("characters") or {}
    broll = manifest.get("broll") or {}
    titles = manifest.get("title_assets") or {}
    shots: list[dict] = []
    for raw in re.split(r"→|->", line):
        part = raw.strip()
        if not part:
            continue
        low = part.lower()
        if re.search(r"b-?roll", low):
            name = re.sub(r".*b-?roll\s*:?\s*", "", part, flags=re.I)
            key = _resolve_broll(name, broll)
            if key:
                shots.append({"kind": "broll", "who": key})
            else:
                warnings.append(f"{cue_id}: b-roll '{name.strip()}' not found in manifest.broll")
        elif re.search(r"\b(title card|card|bumper|title)\b", low):
            asset = _resolve_title(part, titles)
            if asset:
                shots.append({"kind": "title", "asset": asset})
            else:
                warnings.append(f"{cue_id}: title '{part}' not matched to a title_assets key")
        elif "core" in low:
            who = _resolve_character(re.sub(r"\bcore\b", "", part, flags=re.I), characters)
            if who:
                shots.append({"kind": "character", "who": who})
            else:
                warnings.append(f"{cue_id}: character '{part}' not found in manifest.characters")
        else:
            warnings.append(f"{cue_id}: unrecognized shot token '{part}'")
    # default: speaker's own character shot
    if not shots and speaker_who:
        shots.append({"kind": "character", "who": speaker_who})
    # stamp ids + seeds
    out = []
    for i, sh in enumerate(shots, 1):
        sh = {"id": f"{cue_id}_s{i}", **sh}
        if sh["kind"] == "character":
            ch = characters.get(sh["who"])
            if isinstance(ch, dict) and ch.get("seed") is not None:
                sh["seed"] = ch["seed"]
        out.append(sh)
    return out


# ---------- script parse ----------

def _parse_script(text: str) -> list[dict]:
    """Returns raw cues [{header, speaker, vo}] in order (shots resolved later)."""
    cues: list[dict] = []
    cur_header = ""
    cur: dict | None = None
    pending_shot: str | None = None

    def flush():
        nonlocal cur, pending_shot
        if cur is not None:
            cur["vo"] = _clean_vo(" ".join(cur["vo_lines"]))
            cur["shot_line"] = pending_shot
            cur.pop("vo_lines")
            cues.append(cur)
        cur, pending_shot = None, None

    for line in text.splitlines():
        if END_RE.match(line):
            flush()
            break
        m = SEG_RE.match(line)
        if m:
            flush()
            cur_header = m.group(1).strip()
            continue
        m = SPEAKER_RE.match(line)
        if m:
            flush()
            cur = {"header": cur_header, "speaker": m.group(1).strip(),
                   "vo_lines": [m.group(2)], "shot_line": None}
            continue
        m = SHOT_RE.match(line)
        if m:
            if cur is not None and pending_shot is None:
                pending_shot = m.group(1).strip()
            continue
        if not line.strip() or line.startswith("---"):
            flush()
            continue
        # continuation of dialogue (only before the » line)
        if cur is not None and pending_shot is None and not line.startswith("#"):
            cur["vo_lines"].append(line.strip())
    flush()
    return cues


# ---------- merge ----------

def _shot_sig(shots: list[dict]) -> set:
    """Order-independent identity of a shot set, for merge equality."""
    return {(s.get("kind"), s.get("who"), s.get("asset")) for s in (shots or [])}


def _build(slug: str) -> dict:
    old = manifest_mod.load(slug)
    raw = _parse_script(slug_text(slug))
    warnings: list[str] = []

    old_cues = old.get("cues") or []
    # vo -> queue of old cues (each consumed once for stable 1:1 matching)
    old_by_vo: dict[str, list[dict]] = {}
    for c in old_cues:
        old_by_vo.setdefault(_norm(c.get("vo") or ""), []).append(c)

    speaker_map = (old.get("voice") or {}).get("speaker_map") or {}
    characters = old.get("characters") or {}

    # segment slug per header block: majority of matched old cues' segments
    hdr_cues: dict[str, list[dict]] = {}
    for c in raw:
        hdr_cues.setdefault(c["header"], []).append(c)
    header_slug: dict[str, str] = {}
    for header, group in hdr_cues.items():
        votes: dict[str, int] = {}
        for c in group:
            for oc in old_by_vo.get(_norm(c["vo"]), []):
                seg = oc.get("segment")
                if seg:
                    votes[seg] = votes.get(seg, 0) + 1
        if votes:
            header_slug[header] = max(votes, key=votes.get)
        else:
            header_slug[header] = _slug_segment(header) if header else ""
            if header:
                warnings.append(f"segment '{header}' is new → slug '{header_slug[header]}' "
                                f"(freshly generated — review)")

    # STABLE IDS: a matched cue keeps its existing id, so its already-rendered
    # vo/<id>.wav + clips/<id>_sN stay attached and any music-bed/sfx ref to it
    # stays valid. Only genuinely-new lines mint a fresh id (next free c<N>), placed
    # in document order. We deliberately do NOT renumber — renumbering detaches every
    # downstream asset and silently repoints music beds at the wrong cues.
    def _idnum(cid: str | None) -> int:
        mo = re.match(r"c0*(\d+)", cid or "")
        return int(mo.group(1)) if mo else 0

    used_ids = {c.get("id") for c in old_cues if c.get("id")}
    next_n = max((_idnum(c.get("id")) for c in old_cues), default=0) + 1

    def _mint() -> str:
        nonlocal next_n
        while f"c{next_n:02d}" in used_ids:
            next_n += 1
        cid = f"c{next_n:02d}"
        used_ids.add(cid)
        next_n += 1
        return cid

    # build new cues. Matched cues inherit hand-tuned VO/shots verbatim (zero churn
    # on an unchanged script); only new/edited cues use raw script-derived content.
    new_cues: list[dict] = []
    changes: list[dict] = []
    n_new, n_edited = 0, 0
    for c in raw:
        speaker = c["speaker"]
        speaker_who = _resolve_character(speaker, characters)
        seg = header_slug.get(c["header"], "")

        queue = old_by_vo.get(_norm(c["vo"]))
        oc = queue.pop(0) if queue else None
        cid = oc["id"] if (oc is not None and oc.get("id")) else _mint()
        script_shots = _parse_shot_line(c["shot_line"] or "", speaker_who, old, warnings, cid)
        if oc is not None:
            # preserve hand-tuned VO; keep old shots iff the script's shot set matches
            shots = (oc.get("shots") if _shot_sig(script_shots) == _shot_sig(oc.get("shots"))
                     else script_shots)
            if shots is not oc.get("shots"):
                n_edited += 1
                changes.append({"id": cid, "type": "reshot", "speaker": speaker,
                                "vo": (oc.get("vo") or "")[:70]})
            cue = copy.deepcopy(oc)  # carry any hand-authored extra fields
            cue.update({"id": cid, "segment": oc.get("segment") or seg,
                        "speaker": speaker, "shots": copy.deepcopy(shots)})
        else:
            n_new += 1
            changes.append({"id": cid, "type": "added", "speaker": speaker,
                            "vo": (c["vo"] or "")[:70]})
            cue = {"id": cid, "segment": seg, "speaker": speaker,
                   "vo": c["vo"], "shots": script_shots}
        new_cues.append(cue)
        if speaker and speaker not in speaker_map:
            warnings.append(f"{cid}: speaker '{speaker}' has no voice.speaker_map entry")

    # preserve HOLD / no-VO cues (not expressible in script): re-anchor after the
    # old cue that preceded them, else append to the matching segment + warn.
    new_norms = {_norm(c.get("vo") or ""): idx for idx, c in enumerate(new_cues)}
    for oi, oc in enumerate(old_cues):
        if (oc.get("vo") or "").strip():
            continue  # has VO -> regenerated from script
        anchor_idx = None
        for back in range(oi - 1, -1, -1):
            if (old_cues[back].get("vo") or "").strip():
                anchor_idx = new_norms.get(_norm(old_cues[back]["vo"]))
                break
        hold = copy.deepcopy(oc)
        if anchor_idx is not None:
            new_cues.insert(anchor_idx + 1, hold)
            new_norms = {_norm(c.get("vo") or ""): idx for idx, c in enumerate(new_cues)}
            warnings.append(f"preserved hold cue '{oc.get('id')}' after cue #{anchor_idx + 1}")
        else:
            new_cues.append(hold)
            warnings.append(f"preserved hold cue '{oc.get('id')}' appended at end (anchor lost)")

    # ids are already stable (matched cues kept theirs, new cues minted unique). Just
    # re-stamp shot ids from the cue id so a reshot/new cue's shots line up — cheap,
    # idempotent, and never reorders or renumbers.
    for cue in new_cues:
        cid = cue["id"]
        for j, sh in enumerate(cue.get("shots") or [], 1):
            sh["id"] = f"{cid}_s{j}"

    merged = dict(old)
    merged["cues"] = new_cues

    # validate cue references (music beds, sfx) against surviving cue ids. With stable
    # ids an unchanged ref just passes through; a ref only goes stale if that cue's VO
    # was removed/edited enough not to match (so it became a new cue). Drop the stale
    # ref + warn rather than let a bed play under the wrong cue.
    valid_ids = {c["id"] for c in new_cues}
    dropped_refs: list[str] = []
    for bed in ((merged.get("music") or {}).get("beds") or []):
        refs = bed.get("cues")
        if isinstance(refs, list):
            gone = [r for r in refs if r not in valid_ids]
            if gone:
                dropped_refs += [f"music/{bed.get('name', '?')}:{r}" for r in gone]
                warnings.append(f"music bed '{bed.get('name')}': dropped stale cue ref(s) "
                                f"{gone} — cue no longer in script; re-add if intended")
            bed["cues"] = [r for r in refs if r in valid_ids]
    for sfx in (merged.get("sfx") or []):
        label = sfx.get("name") or sfx.get("id") or "?"
        refs = sfx.get("cues")
        if isinstance(refs, list):
            gone = [r for r in refs if r not in valid_ids]
            if gone:
                dropped_refs += [f"sfx/{label}:{r}" for r in gone]
                warnings.append(f"sfx '{label}': dropped stale cue ref(s) {gone}")
            sfx["cues"] = [r for r in refs if r in valid_ids]
        ref = sfx.get("cue")
        if isinstance(ref, str) and ref and ref not in valid_ids:
            dropped_refs.append(f"sfx/{label}:{ref}")
            warnings.append(f"sfx '{label}': cue ref '{ref}' no longer in script — review")

    summary = {
        "old_cue_count": len(old_cues),
        "new_cue_count": len(new_cues),
        "cues_added": n_new,
        "cues_reshot": n_edited,
        "new_ids": [ch["id"] for ch in changes if ch["type"] == "added"],
        "dropped_cue_refs": dropped_refs,
        "changes": changes,
        "speakers": sorted({c["speaker"] for c in new_cues if c.get("speaker")}),
        "unmapped_speakers": sorted({c["speaker"] for c in new_cues
                                     if c.get("speaker") and c["speaker"] not in speaker_map}),
        "segments": list(dict.fromkeys(c["segment"] for c in new_cues if c.get("segment"))),
        "warnings": warnings,
        "renumbered": False,  # stable-id policy: cues are never renumbered
    }
    return {"manifest": merged, "summary": summary, "cues": new_cues}


def slug_text(slug: str) -> str:
    from . import script as script_mod
    return script_mod.read(slug)["text"]


def preview(slug: str) -> dict:
    """Dry run — parse + merge, return proposed manifest + summary. No write."""
    return _build(slug)


def apply(slug: str) -> dict:
    """Write the merged manifest, backing up the old one first."""
    built = _build(slug)
    path = manifest_path(slug)
    if path.exists():
        ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(path.stat().st_mtime))
        shutil.copy2(path, path.with_suffix(f".json.bak.{ts}"))
    saved = manifest_mod.save(slug, built["manifest"])
    return {"summary": built["summary"], "saved": saved,
            "backup": str(path.with_suffix(".json.bak.*"))}
