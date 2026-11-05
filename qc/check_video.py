#!/usr/bin/env python3
"""Objective QC for a rendered episode. Usage: python qc/check_video.py renders/ep001
Reads <dir>/<id>.mp4 and <dir>/<id>.events.json, writes <dir>/qc_report.json, exits 1 on any FAIL.
Uses only ffmpeg/ffprobe + numpy."""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

d = Path(sys.argv[1])
ev = json.loads(next(d.glob("*.events.json")).read_text())
mp4 = d / f"{ev['id']}.mp4"
W, H, FPS, D, CY = ev["width"], ev["height"], ev["fps"], ev["duration_s"], ev["center_y"]
res = []


def check(name, ok, detail):
    res.append({"check": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + " :: " + str(detail))


def frame(t):
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(H, W, 3).astype(np.int16)


# 1 container facts
pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(mp4)],
                               capture_output=True, text=True).stdout)
vs = next(s for s in pr["streams"] if s["codec_type"] == "video")
au = [s for s in pr["streams"] if s["codec_type"] == "audio"]
num, den = map(int, vs["r_frame_rate"].split("/"))
dur = float(pr["format"]["duration"])
check("resolution", (vs["width"], vs["height"]) == (W, H), f"{vs['width']}x{vs['height']}")
check("fps", abs(num / den - FPS) < 0.01, num / den)
check("duration", abs(dur - D) <= 0.15, f"{dur:.2f}s vs spec {D:.2f}s")
check("audio_stream", len(au) == 1, f"{len(au)} stream(s)")
check("duration_limit_60s", dur <= 60, f"{dur:.2f}s")

# 2 motion in the first 0.5 s and no static stretch > 1 s
f0, f5 = frame(0.0), frame(0.5)
m = float(np.abs(f0 - f5).mean())
check("motion_first_0.5s", m > 0.8, f"mean abs diff {m:.2f}")
ts = np.arange(0.0, dur - 0.55, 0.5)
fr = [frame(t) for t in ts]
diffs = [float(np.abs(fr[i + 1] - fr[i]).mean()) for i in range(len(fr) - 1)]
low = [round(float(ts[i]), 1) for i, x in enumerate(diffs) if x < 0.25]
check("no_static_stretch", not low, f"min diff {min(diffs):.2f}; low at {low}")

# 3 hook text visible at 0.8 s
hook = frame(0.8)[150:480, :, :]
white = int(((hook > 230).all(axis=2)).sum())
check("hook_text_by_1s", white > 3000, f"{white} white px in hook zone")

# 4 ring radius at each audio event (picture matches sound). The sampled frame can be the one just before
# or just after the event time, so we accept the radius predicted for either, within 3 px.
bad = []
for e in ev["events"]:
    if e["t"] > dur - 0.05:
        continue
    f = frame(e["t"])
    col = np.array(e["color_rgb"], dtype=np.int16)
    found = []
    for dy in range(-30, 31):
        y = CY - (e["ring_radius_px"] + dy + 0)
        y = int(round(y))
        px = f[y, W // 2 - 1:W // 2 + 2, :].mean(axis=0)
        if np.abs(px - col).max() <= 60:
            found.append(dy)
    # predicted radius offset for the neighbouring frames (+-1 frame) relative to the event time
    cand = [e["ring_speed_px_s"] * k / FPS for k in (-1, 0, 1)]
    ok = any(abs(fd - c) <= 3.5 for fd in found for c in cand)
    if not ok:
        bad.append((e["name"], found[:4], [round(c, 1) for c in cand]))
check("ring_radius_at_events", not bad, f"mismatches: {bad}")

# 5 label dwell
short = [(e["name"], e["label_dwell_s"]) for e in ev["events"] if e["label_dwell_s"] < 1.4]
check("label_dwell>=1.4s", not short, f"min {min(e['label_dwell_s'] for e in ev['events'])}s; short={short}")

# 6 audio loudness / peak
r = subprocess.run(["ffmpeg", "-nostats", "-i", str(mp4), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                   capture_output=True, text=True)
lufs = float(re.findall(r"I:\s+(-?\d+\.\d+) LUFS", r.stderr)[-1])
pk = re.findall(r"Peak:\s+(-?\d+\.\d+) dBFS", r.stderr)
pk = float(pk[-1]) if pk else None
check("loudness_-17..-13_LUFS", -17 <= lufs <= -13, f"{lufs} LUFS")
check("true_peak<=-0.5dBFS", pk is not None and pk <= -0.5, f"{pk} dBFS")

# 7 audio onset of each blip aligned with its event (+-30 ms), measured at the blip's own pitch
sr = 44100
raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(mp4), "-vn", "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                     capture_output=True).stdout
x = np.frombuffer(raw, np.float32).astype(np.float64)
tt = np.arange(len(x)) / sr
k = int(0.004 * sr)
offs = []
for e in ev["events"]:
    if e["t"] > dur - 0.3:
        continue
    z = x * np.exp(-2j * np.pi * e["blip_hz"] * tt)
    env = np.abs(np.convolve(z, np.ones(k) / k, mode="same"))
    c = int(e["t"] * sr)
    pre = float(np.median(env[max(c - int(0.15 * sr), 0):max(c - int(0.03 * sr), 1)]))
    seg = env[c - int(0.08 * sr):c + int(0.15 * sr)]
    pk_ = float(seg.max())
    if pk_ < 3 * max(pre, 1e-6):
        offs.append((e["name"], None))
        continue
    thr = pre + 0.5 * (pk_ - pre)
    idx = int(np.argmax(seg > thr))
    offs.append((e["name"], round((idx - int(0.08 * sr)) / sr * 1000, 1)))
badoff = [o for o in offs if o[1] is None or abs(o[1]) > 30]
worst = max([abs(o[1]) for o in offs if o[1] is not None] or [0])
check("audio_onset_within_30ms", not badoff, f"worst {worst} ms; bad={badoff}")

(d / "qc_report.json").write_text(json.dumps({"id": ev["id"], "results": res}, indent=2))
sys.exit(0 if all(r["pass"] for r in res) else 1)
