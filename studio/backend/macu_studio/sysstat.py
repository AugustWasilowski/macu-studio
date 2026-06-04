"""Lightweight host stats for the Studio topbar: CPU %, GPU %, GPU RAM, storage-disk I/O.

Disk read activity on the storage drive (/mnt/storage) is a good proxy for a model being
loaded into VRAM (ComfyUI / agen / OmniVoice weights live there) — it spikes on load.
"""
from __future__ import annotations

import asyncio
import os
import subprocess

_SECTOR = 512  # bytes per /proc/diskstats sector
_WIN = 0.1     # sampling window (s) shared by CPU + disk deltas
_dev_cache: str | None = None  # "" = resolved-but-none; None = not yet resolved


def _cpu_times() -> tuple[int, int]:
    """(idle, total) jiffies from /proc/stat's aggregate cpu line."""
    with open("/proc/stat") as f:
        parts = [int(x) for x in f.readline().split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)  # idle + iowait
    return idle, sum(parts)


def _storage_dev() -> str | None:
    """The block device backing /mnt/storage (e.g. 'sda1'), resolved from /proc/mounts."""
    global _dev_cache
    if _dev_cache is not None:
        return _dev_cache or None
    dev = ""
    try:
        with open("/proc/mounts") as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and p[1] == "/mnt/storage":
                    dev = os.path.basename(p[0])  # /dev/sda1 -> sda1
                    break
    except Exception:
        dev = ""
    _dev_cache = dev
    return dev or None


def _disk_counters(dev: str) -> tuple[int, int, int] | None:
    """(sectors_read, sectors_written, ms_doing_io) for `dev` from /proc/diskstats."""
    try:
        with open("/proc/diskstats") as f:
            for line in f:
                fields = line.split()
                if len(fields) >= 14 and fields[2] == dev:
                    return int(fields[5]), int(fields[9]), int(fields[12])
    except Exception:
        pass
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
    """CPU% + storage-disk I/O (sampled over _WIN) + GPU (nvidia-smi)."""
    out: dict = {
        "cpu_pct": None,
        "disk_read_mibps": None, "disk_write_mibps": None, "disk_busy_pct": None,
        "disk_dev": None,
        "gpu_pct": None, "gpu_mem_used_mib": None, "gpu_mem_total_mib": None,
    }
    dev = _storage_dev()
    out["disk_dev"] = dev
    try:
        c1 = _cpu_times()
        d1 = _disk_counters(dev) if dev else None
        await asyncio.sleep(_WIN)
        c2 = _cpu_times()
        d2 = _disk_counters(dev) if dev else None

        dt = c2[1] - c1[1]
        if dt > 0:
            out["cpu_pct"] = round(100.0 * (1.0 - (c2[0] - c1[0]) / dt), 1)
        if d1 and d2:
            out["disk_read_mibps"] = round((d2[0] - d1[0]) * _SECTOR / _WIN / 1048576, 1)
            out["disk_write_mibps"] = round((d2[1] - d1[1]) * _SECTOR / _WIN / 1048576, 1)
            out["disk_busy_pct"] = min(100.0, round((d2[2] - d1[2]) / (_WIN * 1000) * 100, 0))
    except Exception:
        pass
    out.update(gpu_stat())
    return out
