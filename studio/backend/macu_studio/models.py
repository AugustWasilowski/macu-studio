"""Strongly-typed (but lenient) manifest models.

These mirror `episodes/<slug>/manifest.json`. Design rules (see docs/MANIFEST_SCHEMA.md):

- **Every model is `extra="allow"`** so freeform / LOCKED blocks (`comfyui`, `subtitles`)
  and any future fields round-trip untouched.
- **Almost everything is Optional.** Validation is a structural *gate*, not a strict
  schema — it catches genuinely malformed manifests (cues not a list, a cue without an
  id, a seed that isn't an int) without rejecting valid existing files.
- The models are a typed **lens** + a validation gate. `manifest.save()` validates
  through `validate()` but then persists the **original raw dict** (never `model_dump()`),
  so the LOCKED blocks stay byte-identical on disk.
"""
from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, ValidationError

_CFG = ConfigDict(extra="allow")


class VoiceProfile(BaseModel):
    model_config = _CFG
    engine: Optional[str] = None
    profile_id: Optional[str] = None
    voice_name: Optional[str] = None
    speed: Optional[float] = None
    guidance_scale: Optional[float] = None
    seed: Optional[int] = None
    instruct: Optional[str] = None


class Voice(BaseModel):
    model_config = _CFG
    default: Optional[dict[str, Any]] = None
    endpoints: Optional[dict[str, Any]] = None
    format: Optional[str] = None
    out_pattern: Optional[str] = None
    speaker_map: dict[str, VoiceProfile] = {}


class Comfyui(BaseModel):
    """LOCKED render block — opaque-but-typed. No required fields; extra=allow keeps
    width/height/frames/steps/cfg/checkpoint/workflow/endpoint/out_pattern/notes intact."""
    model_config = _CFG


class Subtitles(BaseModel):
    """LOCKED block — opaque (font/force_style/fontsdir/... all preserved via extra)."""
    model_config = _CFG


class Style(BaseModel):
    model_config = _CFG
    suffix: Optional[str] = None
    negative: Optional[str] = None


class CharacterDef(BaseModel):
    model_config = _CFG
    seed: Optional[int] = None
    core: Optional[str] = None


class Shot(BaseModel):
    model_config = _CFG
    id: Optional[str] = None
    kind: Optional[str] = None
    who: Optional[str] = None
    asset: Optional[str] = None
    seed: Optional[int] = None
    fill: Optional[str] = None


class Cue(BaseModel):
    model_config = _CFG
    id: str
    segment: Optional[str] = None
    speaker: Optional[str] = None
    vo: Optional[str] = None
    shots: list[Shot] = []
    hold_seconds: Optional[float] = None
    hold_style: Optional[str] = None
    no_subs: Optional[bool] = None
    pad_seconds: Optional[float] = None


class TitleAssetObj(BaseModel):
    model_config = _CFG
    source: Optional[str] = None
    composition: Optional[str] = None
    resolution: Optional[str] = None
    duration_seconds: Optional[float] = None
    fields: Optional[dict[str, Any]] = None
    path: Optional[str] = None
    render_args: Optional[dict[str, Any]] = None


class Overlay(BaseModel):
    """A title-card placement that spans a range of cues (the video twin of a
    music bed). Cue-tethered (anchor_cue) + sub-cue offsets so a timeline can
    drag/resize freely; render resolves to absolute seconds via the cumulative
    cue-offset map (mirrors stage_5_music)."""
    model_config = _CFG
    id: Optional[str] = None          # stable id, minted ov_NNN by gen_manifest
    asset: Optional[str] = None       # key into title_assets — the card to place
    mode: Optional[str] = None        # "insert" (full-frame replace) | "overlay" (composite)
    anchor_cue: Optional[str] = None  # cue the start is tethered to (validated like bed refs)
    start_offset: Optional[float] = None  # seconds into anchor_cue where it begins
    duration: Optional[float] = None      # seconds on screen
    position: Optional[str] = None    # overlay-mode: lower_third|bug_tl|bug_tr|center|full
    scale: Optional[float] = None
    opacity: Optional[float] = None
    fade_in: Optional[float] = None
    fade_out: Optional[float] = None


class Manifest(BaseModel):
    model_config = _CFG
    episode: Optional[str] = None  # the slug, e.g. "ep-006"
    title: Optional[str] = None
    version: Optional[int] = None
    # Provenance + migration (stamped by manifest.save; see migrate() + MANIFEST_SCHEMA.md):
    schema_version: Optional[int] = None   # the manifest schema this was written under
    studio_commit: Optional[str] = None    # short macu-studio commit that last wrote it
    studio_release: Optional[str] = None   # release tag of that commit (e.g. "v0.2.2")
    riffed_from: Optional[str] = None       # source show id, stamped on import-as-riff (lineage)
    notes: Optional[str] = None            # episode description (macu-web synopsis)
    youtube: Optional[dict[str, Any]] = None  # { video_id, description?, tags? } (replaced youtube.txt)
    published: Optional[bool] = None       # initial macu-web publish state on first reindex
    season: Optional[int] = None       # weekly arc (5 eps/week); ep-006 = S01
    episode_num: Optional[int] = None  # 1..5 within the season
    voice: Optional[Voice] = None
    comfyui: Optional[Comfyui] = None
    style: Optional[Style] = None
    render_rule: Optional[str] = None
    title_assets: dict[str, Union[TitleAssetObj, str]] = {}
    music: Optional[dict[str, Any]] = None
    subtitles: Optional[Subtitles] = None
    characters: dict[str, Union[CharacterDef, str]] = {}
    broll: dict[str, Any] = {}
    cues: list[Cue] = []
    # sfx is normally a list of pinned one-shots, but ep-010..015 carry a legacy
    # config-dict schema; stay lenient (the Studio coerces non-lists to []).
    sfx: Optional[Any] = None
    # overlays are spanning title-card placements (see Overlay). Absent on every
    # existing episode; extra=allow round-trips it, so this is fully backward-compatible.
    overlays: Optional[list[Overlay]] = None


def parse(data: dict[str, Any]) -> Manifest:
    """Typed view of a manifest dict (raises ValueError on malformed input)."""
    try:
        return Manifest.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"manifest failed validation:\n{e}") from e


def validate(data: dict[str, Any]) -> None:
    """Structural gate used by manifest.save(); raises ValueError if malformed."""
    parse(data)


# --------------------------------------------------------------------------- #
# Manifest schema versioning + migrations
#
# manifest.save() stamps `schema_version` (= SCHEMA_VERSION) and `studio_commit` (the
# macu-studio HEAD) into every manifest. manifest.load() runs migrate() so older manifests
# are read as current. When you change the manifest schema in a way old files need fixed up:
#   1. Bump SCHEMA_VERSION.
#   2. Append a MIGRATIONS entry: (new_version, "what changed", fn(dict)->dict).
#   3. Note it in docs/_common/MANIFEST_SCHEMA.md.
# Unstamped (pre-versioning) manifests are treated as schema_version 1 — the baseline at the
# time this was introduced (post youtube.txt→manifest merge).
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = 1

# Ordered upgrades. A manifest at version N gets every fn with to_version > N, in order.
MIGRATIONS: list[tuple[int, str, Any]] = [
    # (2, "describe the schema change + how a v1 manifest becomes v2", _migrate_1_to_2),
]


def migrate(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Bring a manifest dict up to SCHEMA_VERSION in memory. Returns (data, changed)."""
    raw = data.get("schema_version")
    cur = int(raw) if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()) else 1
    changed = False
    for to_v, _desc, fn in MIGRATIONS:
        if cur < to_v:
            data = fn(data)
            cur = to_v
            changed = True
    if changed:
        data["schema_version"] = cur
    return data, changed
