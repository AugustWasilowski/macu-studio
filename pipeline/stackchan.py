"""StackChan WS2812 progress-bar driver for the MACU pipeline.

Paints the 30-LED Port C strip as an 8-zone progress bar — one color per pipeline
stage. POSTs /leds/buffer to the device at STACKCHAN_URL (optional hardware; unset
= disabled). Designed to be silent + fast-failing so a missing or flaky StackChan
never blocks a render.

Use:
    from stackchan import paint, clear, set_enabled

    set_enabled(True)            # toggled by run.py based on --no-stackchan
    paint(2, 0.5)                # stage 2 (masters) at 50% — zone partially filled
    clear()                      # all off

Stage zone widths cumulate to 30: [4, 4, 3, 4, 4, 4, 3, 4]. Earlier stages stay
lit in their own color once a later stage starts painting.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# Optional LED progress device. Empty = disabled (no calls) — a fresh install must
# not POST to some IP on the user's LAN. Set STACKCHAN_URL to enable it.
STACKCHAN_URL = os.environ.get("STACKCHAN_URL", "").rstrip("/")
HTTP_TIMEOUT_S = 1.0  # paint must never block a render

# Cumulative LED end-indices per stage (inclusive end, exclusive start of next).
# round(i*30/8) for i in 1..8 → [4, 8, 11, 15, 19, 23, 26, 30]
STAGE_END = [4, 8, 11, 15, 19, 23, 26, 30]
TOTAL_LEDS = 30

# Software brightness scaler applied to every RGB value before posting to the
# firmware. The strip's full-scale 255 is uncomfortably bright at desk distance;
# 0.20 reads as a calm indicator. Override at runtime with STACKCHAN_BRIGHTNESS
# (e.g. 0.10 for night-mode, 0.50 for fully-lit-room visibility).
LED_BRIGHTNESS = max(0.0, min(1.0, float(os.environ.get("STACKCHAN_BRIGHTNESS", "0.20"))))

# 8-color palette: (r, g, b) at full scale. _dim() scales these by LED_BRIGHTNESS
# right before the buffer is sent to the firmware.
STAGE_COLORS = [
    (40, 80, 255),    # 1 vo       — blue
    (255, 20, 200),   # 2 masters  — magenta
    (0, 220, 220),    # 3 rife     — cyan
    (255, 200, 0),    # 4 assemble — yellow
    (0, 220, 60),     # 5 music    — green
    (255, 130, 0),    # 6 whisper  — orange
    (255, 40, 40),    # 7 srt      — red
    (255, 255, 255),  # 8 burn     — white
]

ERROR_COLOR = (255, 0, 0)


def _dim(rgb: tuple[int, int, int]) -> list[int]:
    """Scale an RGB triple by LED_BRIGHTNESS and clamp to 0-255 ints."""
    return [max(0, min(255, round(c * LED_BRIGHTNESS))) for c in rgb]

_enabled = False


def set_enabled(flag: bool) -> None:
    global _enabled
    _enabled = bool(flag)


def stage_range(stage_n: int) -> tuple[int, int]:
    """Return (start, end) LED indices for stage_n (1..8). end is exclusive."""
    start = STAGE_END[stage_n - 2] if stage_n > 1 else 0
    end = STAGE_END[stage_n - 1]
    return start, end


def compute_buffer(stage_n: int, frac: float) -> list[list[int]]:
    """Build the 30-element RGB buffer for stage_n at completion fraction frac.

    Stages 1..(stage_n-1) are fully lit in their own colors. Stage_n's zone is
    partially filled left-to-right in its color; the rest of its zone and all
    subsequent zones stay dark.
    """
    if stage_n < 1: stage_n = 1
    if stage_n > 8: stage_n = 8
    if frac < 0.0: frac = 0.0
    if frac > 1.0: frac = 1.0

    pixels: list[list[int]] = [[0, 0, 0]] * TOTAL_LEDS
    out = [list(p) for p in pixels]  # mutable copies

    # Fully fill all earlier stages.
    for s in range(1, stage_n):
        start, end = stage_range(s)
        color = _dim(STAGE_COLORS[s - 1])
        for i in range(start, end):
            out[i] = list(color)

    # Partial fill the current stage's zone.
    start, end = stage_range(stage_n)
    zone_size = end - start
    filled = round(zone_size * frac)
    if filled > zone_size:
        filled = zone_size
    color = _dim(STAGE_COLORS[stage_n - 1])
    for i in range(start, start + filled):
        out[i] = list(color)

    return out


def _post(path: str, body: dict) -> None:
    """POST to stackchan; swallow all errors silently. Never blocks > HTTP_TIMEOUT_S."""
    if not _enabled or not STACKCHAN_URL:
        return
    try:
        req = urllib.request.Request(
            f"{STACKCHAN_URL}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            resp.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        pass


def paint(stage_n: int, frac: float) -> None:
    """Paint stages 1..(stage_n-1) full + stage_n's zone at frac."""
    _post("/leds/buffer", {"pixels": compute_buffer(stage_n, frac)})


def paint_all_done() -> None:
    """All 30 LEDs lit in their stage colors — celebratory final-success state."""
    _post("/leds/buffer", {"pixels": compute_buffer(8, 1.0)})


def paint_error(stage_n: int) -> None:
    """Mark the failing stage's zone solid red, leave earlier zones lit."""
    if stage_n < 1: stage_n = 1
    if stage_n > 8: stage_n = 8
    pixels = compute_buffer(stage_n, 0.0)  # earlier stages filled, current zone dark
    start, end = stage_range(stage_n)
    err = _dim(ERROR_COLOR)
    for i in range(start, end):
        pixels[i] = list(err)
    _post("/leds/buffer", {"pixels": pixels})


def clear() -> None:
    """All LEDs off."""
    _post("/leds/buffer", {"pixels": []})


def reachable() -> bool:
    """Cheap probe — GET /status with a tight timeout."""
    try:
        with urllib.request.urlopen(f"{STACKCHAN_URL}/status", timeout=HTTP_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            return bool(data.get("device") == "stackchan")
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
        return False
