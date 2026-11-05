"""Format A engine: log-scale zoom from the smallest to the largest object, 100% code.
Every number on screen is derived from the spec; nothing is typed by hand.
Needs: pycairo, numpy, soundfile, ffmpeg. No generative AI, no sample libraries, no Blender."""
import colorsys
import json
import math
import re
import subprocess
from pathlib import Path

import cairo
import numpy as np
import soundfile as sf
import yaml

LY = 9.4607304725808e15
UNITS = {"pm": 1e-12, "nm": 1e-9, "um": 1e-6, "mm": 1e-3, "m": 1.0, "km": 1e3,
         "million km": 1e9, "AU": 149597870700.0, "ly": LY,
         "million ly": LY * 1e6, "billion ly": LY * 1e9}
SHOW = {"um": "\u00b5m", "ly": "light-years", "million ly": "million light-years", "billion ly": "billion light-years"}
SUP = str.maketrans("0123456789-", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207b")
SR = 44100
SCALE = [0, 2, 4, 7, 9, 12, 14, 16, 19, 21, 24, 26]


def sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def sci(x, digits=1):
    e = int(math.floor(math.log10(x)))
    return f"{x / 10 ** e:.{digits}f}\u00d710{str(e).translate(SUP)}"


def fmt_value(v, unit, decimals, approx=False):
    name = SHOW.get(unit, unit)
    if unit == "ly" and abs(v - 1) < 1e-12:
        name = "light-year"
    return f"{'~' if approx else ''}{v:,.{decimals}f} {name}"


def fmt_fov(m):
    """Human-readable field-of-view width for the on-screen readout."""
    if m < 1e-9:
        return f"{m / 1e-12:,.0f} pm"
    for lim, u, d in ((1e-6, "nm", 1e-9), (1e-3, "\u00b5m", 1e-6), (1.0, "mm", 1e-3), (1e3, "m", 1.0),
                      (0.3 * UNITS["AU"], "km", 1e3), (0.1 * LY, "AU", UNITS["AU"])):
        if m < lim:
            return f"{m / d:,.3g} {u}" if m / d < 1000 else f"{m / d:,.0f} {u}"
    ly = m / LY
    if ly < 1e6:
        return f"{ly:,.3g} light-years" if ly < 1000 else f"{ly:,.0f} light-years"
    if ly < 1e9:
        return f"{ly / 1e6:,.3g} million light-years"
    return f"{ly / 1e9:,.3g} billion light-years"


def mavg(x, n):
    cs = np.cumsum(np.insert(x, 0, 0.0))
    y = (cs[n:] - cs[:-n]) / n
    return np.pad(y, (n // 2, len(x) - len(y) - n // 2))


def measure_lufs(wav):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(wav), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?\d+\.\d+) LUFS", r.stderr)
    p = re.findall(r"Peak:\s+(-?\d+\.\d+) dBFS", r.stderr)
    return float(i[-1]), float(p[-1]) if p else None


class Episode:
    def __init__(self, spec):
        self.spec = spec
        v = spec["video"]
        self.W, self.H, self.FPS = v["width"], v["height"], v["fps"]
        self.cy = spec["layout"]["center_y"]
        self.tl = spec["timeline"]
        objs = []
        for o in spec["objects"]:
            objs.append({**o, "meters": o["value"] * UNITS[o["unit"]]})
        objs.sort(key=lambda o: o["meters"])
        for i, o in enumerate(objs):
            o["color"] = colorsys.hsv_to_rgb((0.52 + 0.083 * i) % 1.0, 0.62, 1.0)
            o["size_text"] = fmt_value(o["value"], o["unit"], o["decimals"], o.get("approx", False)) + \
                             {"across": " across", "tall": " tall", "long": " long"}.get(o.get("measure"), "")
        self.objs = objs
        self._timeline()
        self.D = self.tl["zoom_seconds"] + self.tl["hold_seconds"]
        self.ratio = objs[-1]["meters"] / objs[0]["meters"]
        self._ev = self.events()
        self._background()
        self.surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.W, self.H)

    # ---------- timeline ----------
    def _timeline(self):
        tl, objs = self.tl, self.objs
        for o in objs:
            o["L"] = math.log10(o["meters"] / 2 / tl["label_center_px"])  # log10(m/px) when ring radius == label_center_px
        self.L0 = math.log10(objs[0]["meters"] / 2 / tl["start_radius_px"])
        self.L1 = math.log10(objs[-1]["meters"] / 2 / tl["end_radius_px"])
        Lg = np.linspace(self.L0, self.L1, 40001)
        centers = np.array([o["L"] + tl["slow_center_shift"] for o in objs])
        dist = np.abs(Lg[:, None] - centers[None, :]).min(axis=1)
        w = sstep((dist - tl["slow_halfwidth"]) / tl["ramp"])
        speed = tl["slow_speed"] * (1 - w) + tl["fast_speed"] * w
        dt = np.diff(Lg) / (0.5 * (speed[1:] + speed[:-1]))
        t = np.concatenate([[0.0], np.cumsum(dt)])
        t *= tl["zoom_seconds"] / t[-1]
        self.Lg, self.tg = Lg, t

    def L_of_t(self, t):
        t = np.asarray(t, dtype=float)
        tz = self.tl["zoom_seconds"]
        return np.where(t <= tz, np.interp(t, self.tg, self.Lg), self.L1 + self.tl["end_creep"] * (t - tz))

    def t_of_L(self, L):
        return float(np.interp(L, self.Lg, self.tg))

    def events(self):
        tl = self.tl
        out = []
        for o in self.objs:
            lo = self.t_of_L(o["L"] + math.log10(tl["label_center_px"] / 520.0))   # label fully visible (r=520)
            hiL = o["L"] + math.log10(tl["label_center_px"] / 40.0)
            hi = self.t_of_L(hiL) if hiL < self.L1 else self.tl["zoom_seconds"] + self.tl["hold_seconds"]  # label ends (r=40) or video ends
            te = self.t_of_L(o["L"])
            Le = float(self.L_of_t(te))
            dL = float((self.L_of_t(te + 0.005) - self.L_of_t(te - 0.005)) / 0.01)
            r_e = o["meters"] / 2 / 10 ** Le
            i = len(out)
            out.append({"name": o["name"], "t": round(te, 4), "ring_radius_px": round(r_e, 2),
                        "ring_speed_px_s": round(-r_e * math.log(10) * dL, 1),
                        "blip_hz": round(261.63 * 2 ** (SCALE[i % len(SCALE)] / 12), 2),
                        "color_rgb": [round(c * 255) for c in o["color"]], "label_dwell_s": round(hi - lo, 3),
                        "size_text": o["size_text"], "meters": o["meters"], "note": o.get("note", "")})
        return out

    # ---------- drawing ----------
    def _background(self):
        W, H = self.W, self.H
        self.bg = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        c = cairo.Context(self.bg)
        g = cairo.LinearGradient(0, 0, 0, H)
        g.add_color_stop_rgb(0, 0.016, 0.027, 0.075)
        g.add_color_stop_rgb(1, 0.035, 0.07, 0.17)
        c.set_source(g)
        c.paint()
        rng = np.random.default_rng(self.spec["audio"]["seed"])
        n = 220
        self.st_ang = rng.uniform(0, 2 * np.pi, n)
        self.st_log = rng.uniform(0, 1, n)          # position along the wrapped log-radius axis
        self.st_a = rng.uniform(0.35, 0.9, n)

    def _text(self, c, s, x, y, size, rgba, bold=True):
        c.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        c.set_font_size(size)
        ext = c.text_extents(s)
        c.move_to(x - ext.width / 2 - ext.x_bearing, y)
        c.set_source_rgba(*rgba)
        c.show_text(s)

    def draw(self, t):
        W, H, cy, cx = self.W, self.H, self.cy, self.W / 2
        c = cairo.Context(self.surf)
        c.set_source_surface(self.bg, 0, 0)
        c.paint()
        Lt = float(self.L_of_t(t))
        mpp = 10 ** Lt
        lo, hi = math.log10(30.0), math.log10(1400.0)
        flow = (Lt - self.L0) * 0.22
        spd = abs(float(self.L_of_t(t + 0.01) - self.L_of_t(t - 0.01)) / 0.02) * 0.22
        for ang, u, al in zip(self.st_ang, self.st_log, self.st_a):
            fr_ = (u - flow / (hi - lo)) % 1.0           # inward drift while zooming out
            rr = 10 ** (lo + fr_ * (hi - lo))
            fade = math.sin(math.pi * fr_) ** 0.8
            x, y = cx + rr * math.cos(ang), cy + rr * math.sin(ang)
            if not (0 <= x < W and 0 <= y < H):
                continue
            ln = min(rr * (10 ** (spd * 0.035) - 1) * 4, 90)   # streak grows with zoom speed
            c.set_source_rgba(0.85, 0.92, 1, al * fade * 0.8)
            c.set_line_width(1.6 + 1.2 * (rr / 1400))
            c.move_to(x, y)
            c.line_to(x + ln * math.cos(ang), y + ln * math.sin(ang))
            c.stroke()
        for o in self.objs:
            r = o["meters"] / 2 / mpp
            a = float(sstep((r - 2) / 6) * (1 - sstep((r - 600) / 700)))
            if a <= 0.001:
                continue
            cr, cg, cb = o["color"]
            if r < 6:
                for rad, al in ((16, 0.10), (9, 0.22), (4, 0.9)):
                    c.set_source_rgba(cr, cg, cb, al * a)
                    c.arc(cx, cy, rad, 0, 6.2832)
                    c.fill()
                continue
            sh = cairo.RadialGradient(cx - 0.35 * r, cy - 0.4 * r, 0.05 * r, cx, cy, r)
            sh.add_color_stop_rgba(0, min(cr + 0.35, 1), min(cg + 0.35, 1), min(cb + 0.35, 1), 0.42 * a)
            sh.add_color_stop_rgba(0.55, cr, cg, cb, 0.16 * a)
            sh.add_color_stop_rgba(1, cr * 0.5, cg * 0.5, cb * 0.5, 0.30 * a)
            c.set_source(sh)
            c.arc(cx, cy, r, 0, 6.2832)
            c.fill()
            for wd, al in ((44, 0.03), (24, 0.06), (11, 0.12)):
                c.set_source_rgba(cr, cg, cb, al * a)
                c.set_line_width(wd)
                c.arc(cx, cy, r, 0, 6.2832)
                c.stroke()
            c.set_source_rgba(cr, cg, cb, a)
            c.set_line_width(5)
            c.arc(cx, cy, r, 0, 6.2832)
            c.stroke()
            if 40 <= r <= 520:
                la = float(sstep((r - 40) / 50) * (1 - sstep((r - 440) / 80)))
                self._text(c, o["name"].upper(), cx, cy - r - 92, 62, (1, 1, 1, la))
                self._text(c, o["size_text"], cx, cy - r - 36, 42, (cr, cg, cb, la), bold=False)
        for ev in self._ev:
            dtp = t - ev["t"]
            if 0 <= dtp < 0.6:
                k = dtp / 0.6
                c.set_source_rgba(*[x / 255 for x in ev["color_rgb"]], 0.55 * (1 - k) ** 2)
                c.set_line_width(4)
                c.arc(cx, cy, ev["ring_radius_px"] + 90 * k, 0, 6.2832)
                c.stroke()
        c0 = self.objs[0]["color"]
        c.set_source_rgba(*c0, 0.95)
        c.arc(cx, cy, 3.5, 0, 6.2832)
        c.fill()
        # hook / header
        tl_txt = self.spec["text"]
        hs = tl_txt["hook_seconds"]
        hook_a = 1.0 - float(sstep((t - (hs - 0.4)) / 0.4))
        if hook_a > 0:
            for k, line in enumerate(tl_txt["hook_lines"]):
                self._text(c, line, cx, 250 + k * 110, 96, (1, 1, 1, hook_a))
        head_a = float(sstep((t - (hs - 0.4)) / 0.4)) * 0.85
        if head_a > 0:
            self._text(c, tl_txt["header"], cx, 190, 56, (0.75, 0.85, 1.0, head_a))
        # bottom readout / final reveal
        tz = self.tl["zoom_seconds"]
        rev = float(sstep((t - tz) / 0.5))
        if rev < 1:
            self._text(c, "FIELD OF VIEW", cx, 1440, 34, (0.6, 0.7, 0.85, 0.8 * (1 - rev)), bold=False)
            self._text(c, fmt_fov(W * mpp), cx, 1520, 64, (1, 1, 1, 1 - rev))
        if rev > 0:
            self._text(c, "UNIVERSE \u00f7 ATOM", cx, 1440, 36, (0.6, 0.7, 0.85, rev), bold=False)
            self._text(c, sci(self.ratio), cx, 1540, 120, (1, 0.85, 0.35, rev))
        return np.frombuffer(self.surf.get_data(), np.uint8).reshape(H, W, 4)

    def contact_sheet(self, path, n=12, cols=4):
        w, h = self.W // 4, self.H // 4
        rows = math.ceil(n / cols)
        sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * cols, h * rows)
        c = cairo.Context(sheet)
        for i in range(n):
            t = (self.D - 0.05) * i / (n - 1)
            self.draw(t)
            c.save()
            c.translate((i % cols) * w, (i // cols) * h)
            c.scale(0.25, 0.25)
            c.set_source_surface(self.surf, 0, 0)
            c.paint()
            c.restore()
        sheet.write_to_png(str(path))

    # ---------- audio ----------
    def audio(self):
        D, n = self.D, int(self.D * SR)
        t = np.arange(n) / SR
        rng = np.random.default_rng(self.spec["audio"]["seed"])
        L = self.L_of_t(t)
        p = np.clip((L - self.L0) / (self.L1 - self.L0), 0, 1)
        f = 110.0 * 2 ** (1.5 * p)
        ph = 2 * np.pi * np.cumsum(f) / SR
        trem = 1 + 0.12 * np.sin(2 * np.pi * 0.3 * t)
        drone = (np.sin(ph) + 0.5 * np.sin(1.5 * ph) + 0.25 * np.sin(2.0 * ph)) * (0.07 + 0.05 * p) * trem
        # whoosh follows zoom speed
        tc = np.arange(0, D, 0.01)
        sp = np.abs(np.gradient(self.L_of_t(tc), 0.01))
        sp = np.interp(t, tc, (sp - sp.min()) / (np.ptp(sp) + 1e-9))
        nz = rng.standard_normal(n)
        low, mid = mavg(nz, 400) * 20, mavg(nz, 24) * 4.9
        whoosh = (low * (1 - sp) + mid * sp) * (0.015 + 0.10 * sp ** 1.5)
        mix = drone + whoosh
        for i, ev in enumerate(self.events()):
            fr = ev["blip_hz"]
            k = int(ev["t"] * SR)
            m = min(int(1.1 * SR), n - k)
            tt = np.arange(m) / SR
            env = np.minimum(tt / 0.003, 1) * np.exp(-tt / 0.28)
            tone = (np.sin(2 * np.pi * fr * tt) + 0.3 * np.sin(4 * np.pi * fr * tt)) * env * 0.30
            for d, g in ((0.18, 0.35), (0.36, 0.18)):
                s = int(d * SR)
                if s < m:
                    tone[s:] += tone[:m - s] * g
            mix[k:k + m] += tone
        k = int((self.tl["zoom_seconds"] + 0.05) * SR)
        m = min(int(2.0 * SR), n - k)
        tt = np.arange(m) / SR
        fi = 35 + 55 * np.exp(-tt / 0.25)
        boom = np.sin(2 * np.pi * np.cumsum(fi) / SR) * np.exp(-tt / 0.6) * 0.8
        boom += mavg(rng.standard_normal(m), 60) * 7.7 * np.exp(-tt / 0.25) * 0.25
        mix[k:k + m] += boom
        mix *= np.minimum(t / 0.01, 1) * np.minimum((D - t) / 0.4, 1)
        return mix.astype(np.float32)

    def write_audio(self, wav):
        x = self.audio()
        sf.write(str(wav), x, SR, subtype="PCM_16")
        lufs, _ = measure_lufs(wav)
        g = 10 ** ((self.spec["audio"]["target_lufs"] - lufs) / 20)
        x = x * g
        pk = float(np.abs(x).max())
        if pk > 0.78:
            x = 0.78 * np.tanh(x / 0.78)
        sf.write(str(wav), x, SR, subtype="PCM_16")
        return measure_lufs(wav)

    # ---------- video ----------
    def render(self, out_mp4, wav, preset="veryfast"):
        W, H, fps = self.W, self.H, self.FPS
        n = int(round(self.D * fps))
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
               "-r", str(fps), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", preset, "-crf", "18",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(out_mp4)]
        pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        first = self.draw(0.0).astype(np.float32).copy()
        nx = self.tl["loop_crossfade_frames"]
        for i in range(n):
            fr = self.draw(i / fps)
            if i >= n - nx:
                a = (i - (n - nx) + 1) / (nx + 1)
                fr = (fr.astype(np.float32) * (1 - a) + first * a).astype(np.uint8)
            pr.stdin.write(fr.tobytes())
        pr.stdin.close()
        if pr.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        return n


def load(path):
    return Episode(yaml.safe_load(Path(path).read_text()))
