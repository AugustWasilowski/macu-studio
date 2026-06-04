"""Lightweight host stats for the Studio topbar: CPU %, GPU %, GPU RAM."""
from __future__ import annotations

import asyncio
import subprocess


def _cpu_times() -> tuple[int, int]:
    """(idle, total) jiffies from /proc/stat's aggregate cpu line."""
    with open("/proc/stat") as f:
        parts = [int(x) for x in f.readline().split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)  # idle + iowait
    return idle, sum(parts)


async def cpu_pct() -> float | None:
    """Aggregate CPU utilization sampled over a short window."""
    try:
        i1, t1 = _cpu_times()
        await asyncio.sleep(0.1)
        i2, t2 = _cpu_times()
        dt = t2 - t1
        if dt <= 0:
            return None
        return round(100.0 * (1.0 - (i2 - i1) / dt), 1)
    except Exception:
        return None


def gpu_stat() -> dict:
    """GPU utilization % + memory used/total (MiB) via nvidia-smi. Degrades to None."""
    out = {"gpu_pct": None, "gpu_mem_used_mib": None, "gpu_mem_total_mib": None}
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        util, used, total = [c.strip() for c in r.stdout.strip().splitlines()[0].split(",")]
        out["gpu_pct"] = float(util)
        out["gpu_mem_used_mib"] = int(used)
        out["gpu_mem_total_mib"] = int(total)
    except Exception:
        pass
    return out


async def snapshot() -> dict:
    return {"cpu_pct": await cpu_pct(), **gpu_stat()}
