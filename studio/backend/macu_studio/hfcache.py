"""Studio-side view of the Higgsfield shot cache.

The canonical implementation lives in pipeline/hf_cache.py (the pipeline and
Studio share one venv + repo checkout, so unlike the vo-hash mirror this is a
real single source of truth). This shim loads it by path and re-exports it.
"""
from __future__ import annotations

import importlib.util
import sys

from .config import REPO_ROOT

_PATH = REPO_ROOT / "pipeline" / "hf_cache.py"
_spec = importlib.util.spec_from_file_location("macu_pipeline_hf_cache", _PATH)
assert _spec and _spec.loader, f"cannot load {_PATH}"
_mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("macu_pipeline_hf_cache", _mod)
_spec.loader.exec_module(_mod)

sys.modules[__name__ + "._impl"] = _mod
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
