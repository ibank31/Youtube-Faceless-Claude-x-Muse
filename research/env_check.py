#!/usr/bin/env python3
"""Muse runs this first. Writes research/env_report.json.
Never writes secrets: it only records whether YOUTUBE_API_KEY is set (true/false)."""
import datetime as dt
import importlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

OUT = Path(__file__).with_name("env_report.json")


def sh(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        text = (p.stdout or p.stderr).strip()
        return text.splitlines()[0] if text else ""
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"


def mem():
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.strip().split()[0])  # kB
    except Exception:  # noqa: BLE001
        return {}
    gb = lambda kb: round(kb / 1048576, 2)  # noqa: E731
    return {
        "total_gb": gb(info.get("MemTotal", 0)),
        "available_gb": gb(info.get("MemAvailable", 0)),
        "swap_total_gb": gb(info.get("SwapTotal", 0)),
    }


def pkg(name):
    if importlib.util.find_spec(name) is None:
        return None
    try:
        return getattr(importlib.import_module(name), "__version__", "installed")
    except Exception as e:  # noqa: BLE001
        return f"import-error: {e}"


def ffmpeg_info():
    if not shutil.which("ffmpeg"):
        return {"present": False}
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                         capture_output=True, text=True, timeout=30).stdout
    return {"present": True, "version": sh(["ffmpeg", "-version"]),
            "libx264": "libx264" in enc, "aac": " aac " in enc}


def bench(frames=120, w=1080, h=1920, circles=300):
    """Rough 2D render speed: draws `circles` circles per 1080x1920 frame with pycairo."""
    try:
        import random

        import cairo
    except ImportError:
        return {"engine": None, "note": "pycairo not installed; bench skipped"}
    try:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surf)
        rnd = random.Random(1)
        t0 = time.perf_counter()
        for _ in range(frames):
            ctx.set_source_rgb(0.05, 0.05, 0.08)
            ctx.paint()
            for _ in range(circles):
                ctx.set_source_rgb(rnd.random(), rnd.random(), rnd.random())
                ctx.arc(rnd.uniform(0, w), rnd.uniform(0, h), rnd.uniform(5, 40), 0, 6.283185)
                ctx.fill()
            surf.get_data()
        secs = time.perf_counter() - t0
        return {"engine": "pycairo", "frames": frames, "circles_per_frame": circles,
                "seconds": round(secs, 2), "fps": round(frames / secs, 1)}
    except Exception as e:  # noqa: BLE001
        return {"engine": "pycairo", "error": str(e)}


def main():
    total, used, free = shutil.disk_usage(".")
    report = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "memory": mem(),
        "disk_free_gb": round(free / 1e9, 1),
        "gpu": sh(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if shutil.which("nvidia-smi") else None,
        "ffmpeg": ffmpeg_info(),
        "packages": {n: pkg(n) for n in (
            "requests", "yaml", "numpy", "scipy", "pandas", "pymunk", "cairo", "skia",
            "PIL", "cv2", "soundfile", "mido", "pretty_midi", "pytrends")},
        "youtube_api_key_env_set": bool(os.environ.get("YOUTUBE_API_KEY")),
        "bench_2d": bench(),
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
