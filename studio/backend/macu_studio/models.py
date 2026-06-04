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


class Manifest(BaseModel):
    model_config = _CFG
    episode: Optional[str] = None  # the slug, e.g. "ep-006"
    title: Optional[str] = None
    version: Optional[int] = None
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


def parse(data: dict[str, Any]) -> Manifest:
    """Typed view of a manifest dict (raises ValueError on malformed input)."""
    try:
        return Manifest.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"manifest failed validation:\n{e}") from e


def validate(data: dict[str, Any]) -> None:
    """Structural gate used by manifest.save(); raises ValueError if malformed."""
    parse(data)
