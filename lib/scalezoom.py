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


def fmt_times(r):
    """How many times bigger: readable, 2-3 significant digits."""
    if r < 10:
        return f"{r:.1f}\u00d7"
    if r < 1000:
        return f"{round(r, 2 - int(math.floor(math.log10(r)))):,.0f}\u00d7"
    if r < 1e6:
        return f"{round(r, 1 - int(math.floor(math.log10(r)))):,.0f}\u00d7"
    if r < 1e9:
        return f"{r / 1e6:.0f} million\u00d7" if r >= 1e8 else f"{r / 1e6:.1f} million\u00d7"
    if r < 1e12:
        return f"{r / 1e9:.1f} billion\u00d7"
    return sci(r) + "\u00d7"


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
        self._segments()
        self.ratio = objs[-1]["meters"] / objs[0]["meters"]
        self._ev = self.events()
        self._background()
        self.surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.W, self.H)

    # ---------- timeline: hold -> transition -> hold ... ----------
    def _segments(self):
        tl, objs = self.tl, self.objs
        Rh, cr, n = tl["hold_radius_px"], tl["hold_creep"], len(objs)
        t, self.seg = 0.0, []
        for k, o in enumerate(objs):
            o["Ls"] = math.log10(o["meters"] / 2 / Rh)                       # log10(m/px) at hold start
            o["H"] = tl["first_hold_seconds"] if k == 0 else (tl["last_hold_seconds"] if k == n - 1 else tl["hold_seconds"])
            if k > 0:
                prev = objs[k - 1]
                self.seg.append({"type": "trans", "k": k, "t0": t, "t1": t + tl["transition_seconds"],
                                 "La": prev["Ls"] + cr * prev["H"], "Lb": o["Ls"]})
                t += tl["transition_seconds"]
            o["t_hold0"] = t
            self.seg.append({"type": "hold", "k": k, "t0": t, "t1": t + o["H"], "L0": o["Ls"]})
            t += o["H"]
        self.D = t
        self.L0, self.L1 = objs[0]["Ls"], objs[-1]["Ls"] + cr * objs[-1]["H"]

    def state(self, t):
        for s in self.seg:
            if s["t0"] <= t < s["t1"]:
                return {"type": s["type"], "k": s["k"], "u": (t - s["t0"]) / (s["t1"] - s["t0"]), "t0": s["t0"]}
        s = self.seg[-1]
        return {"type": s["type"], "k": s["k"], "u": 1.0, "t0": s["t0"]}

    def L_of_t(self, t):
        scalar = np.ndim(t) == 0
        t = np.atleast_1d(np.asarray(t, dtype=float))
        cr = self.tl["hold_creep"]
        out = np.full_like(t, self.L1)
        for s in self.seg:
            m = (t >= s["t0"]) & (t < s["t1"])
            if s["type"] == "hold":
                out[m] = s["L0"] + cr * (t[m] - s["t0"])
            else:
                out[m] = s["La"] + (s["Lb"] - s["La"]) * sstep((t[m] - s["t0"]) / (s["t1"] - s["t0"]))
        return float(out[0]) if scalar else out

    def jump(self, k):
        """(multiplier text, caption, volume line or None) comparing object k with object k-1."""
        o, p = self.objs[k], self.objs[k - 1]
        r = o["meters"] / p["meters"]
        pre = "~" if (o.get("approx") or p.get("approx")) else ""
        vol = None
        if o.get("volume_line"):
            vol = f"That is ~{r ** 3 / 1e6:.1f} million {o['volume_line']} by volume"
        return pre + fmt_times(r), f"bigger than {p['name']}", vol

    def label_alphas(self, t):
        """Alpha of: target label above its ring, previous object's label above its ring, previous object's dot annotation."""
        st = self.state(t)
        k = st["k"]
        mpp = 10 ** self.L_of_t(t)
        rk = self.objs[k]["meters"] / 2 / mpp
        a_t = float(sstep((560 - rk) / 80))
        a_p = a_a = 0.0
        if k > 0:
            rp = self.objs[k - 1]["meters"] / 2 / mpp
            a_p = float(sstep((rp - 70) / 50) * sstep((560 - rp) / 80))
            a_a = float(1 - sstep((rp - 70) / 50))
        return a_t, a_p, a_a

    def label_coverage(self):
        n = int(self.D * self.FPS)
        bad = [round(i / self.FPS, 2) for i in range(n) if max(self.label_alphas(i / self.FPS)) < 0.5]
        return 1 - len(bad) / n, bad

    def events(self):
        out = []
        cr, Rh = self.tl["hold_creep"], self.tl["hold_radius_px"]
        for k, o in enumerate(self.objs):
            if k == 0:
                t_lab = 0.0
            else:
                tr = [s for s in self.seg if s["type"] == "trans" and s["k"] == k][0]
                ts = np.linspace(tr["t0"], tr["t1"], 400)
                r = o["meters"] / 2 / 10 ** self.L_of_t(ts)
                t_lab = float(ts[np.argmax(r <= 520)])
            out.append({"name": o["name"], "t": round(o["t_hold0"], 4), "ring_radius_px": Rh,
                        "ring_speed_px_s": round(-Rh * math.log(10) * cr, 2),
                        "blip_hz": round(261.63 * 2 ** (SCALE[k % len(SCALE)] / 12), 2),
                        "color_rgb": [round(c * 255) for c in o["color"]],
                        "label_dwell_s": round(o["t_hold0"] + o["H"] - t_lab, 3),
                        "hold": [round(o["t_hold0"], 3), round(o["t_hold0"] + o["H"], 3)],
                        "size_text": o["size_text"], "meters": o["meters"], "note": o.get("note", ""),
                        "jump": list(self.jump(k)) if k > 0 else None})
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

    def _text(self, c, s, x, y, size, rgba, bold=True, max_w=None):
        c.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
        c.set_font_size(size)
        ext = c.text_extents(s)
        if max_w and ext.width > max_w:
            c.set_font_size(size * max_w / ext.width)
            ext = c.text_extents(s)
        c.move_to(x - ext.width / 2 - ext.x_bearing, y)
        c.set_source_rgba(*rgba)
        c.show_text(s)
        c.new_path()

    def _ring(self, c, o, r, a):
        cx, cy = self.W / 2, self.cy
        cr, cg, cb = o["color"]
        if r < 6:
            for rad, al in ((16, 0.10), (9, 0.22), (4, 0.9)):
                c.set_source_rgba(cr, cg, cb, al * a)
                c.arc(cx, cy, rad, 0, 6.2832)
                c.fill()
            return
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

    def _ladder(self, c, t):
        st = self.state(t)
        pos = st["k"] if st["type"] == "hold" else (st["k"] - 1) + float(sstep(st["u"]))
        n = len(self.objs)
        y0, y1, x = 330.0, 1230.0, 46.0
        ys = [y0 + (y1 - y0) * i / (n - 1) for i in range(n)]
        c.set_line_width(3)
        c.set_source_rgba(0.6, 0.7, 0.9, 0.25)
        c.move_to(x, y0)
        c.line_to(x, y1)
        c.stroke()
        ypos = y0 + (y1 - y0) * pos / (n - 1)
        c.set_source_rgba(0.6, 0.9, 1.0, 0.8)
        c.move_to(x, y0)
        c.line_to(x, ypos)
        c.stroke()
        for i, o in enumerate(self.objs):
            cr, cg, cb = o["color"]
            cur = abs(i - pos) < 0.5
            if cur:
                c.set_source_rgba(cr, cg, cb, 1)
                c.arc(x, ys[i], 12, 0, 6.2832)
                c.fill()
                c.set_source_rgba(1, 1, 1, 1)
                c.set_line_width(3)
                c.arc(x, ys[i], 12, 0, 6.2832)
                c.stroke()
            elif i < pos:
                c.set_source_rgba(cr, cg, cb, 0.55)
                c.arc(x, ys[i], 7, 0, 6.2832)
                c.fill()
            else:
                c.set_source_rgba(0.7, 0.75, 0.9, 0.5)
                c.set_line_width(2.5)
                c.arc(x, ys[i], 7, 0, 6.2832)
                c.stroke()
            c.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if cur else cairo.FONT_WEIGHT_NORMAL)
            c.set_font_size(36 if cur else 30)
            c.set_source_rgba(1, 1, 1, 1) if cur else c.set_source_rgba(0.75, 0.8, 0.92, 0.75 if i < pos else 0.5)
            c.move_to(x + 28, ys[i] + 11)
            c.show_text(o["short"])
            c.new_path()

    def draw(self, t):
        W, H, cy, cx = self.W, self.H, self.cy, self.W / 2
        c = cairo.Context(self.surf)
        c.set_source_surface(self.bg, 0, 0)
        c.paint()
        st = self.state(t)
        kt = st["k"]
        Lt = self.L_of_t(t)
        mpp = 10 ** Lt
        lo, hi = math.log10(30.0), math.log10(1400.0)
        flow = (Lt - self.L0) * 0.22
        spd = abs(self.L_of_t(t + 0.01) - self.L_of_t(t - 0.01)) / 0.02 * 0.22
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
        rs = [o["meters"] / 2 / mpp for o in self.objs]
        for o, r in zip(self.objs, rs):
            a = float(sstep((r - 2) / 6) * (1 - sstep((r - 600) / 700)))
            if a > 0.001:
                self._ring(c, o, r, a)
        a_t, a_p, a_a = self.label_alphas(t)
        for i, al in ((kt, a_t), (kt - 1, a_p)):
            if i >= 0 and al > 0.01:
                o, r = self.objs[i], rs[i]
                cr, cg, cb = o["color"]
                self._text(c, o["name"].upper(), cx, cy - r - 92, 62, (1, 1, 1, al), max_w=640)
                self._text(c, o["size_text"], cx, cy - r - 36, 42, (cr, cg, cb, al), bold=False, max_w=700)
        if kt > 0 and a_a > 0.01:                       # previous object shown as a dot inside the current one
            cr, cg, cb = self.objs[kt - 1]["color"]
            for rad, al in ((14, 0.15), (8, 0.35), (4.5, 1.0)):
                c.set_source_rgba(cr, cg, cb, al * a_a)
                c.arc(cx, cy, rad, 0, 6.2832)
                c.fill()
            c.set_source_rgba(cr, cg, cb, a_a * 0.9)
            c.set_line_width(2.5)
            c.move_to(cx + 8, cy + 8)
            c.line_to(cx + 70, cy + 70)
            c.line_to(cx + 96, cy + 70)
            c.stroke()
            c.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            c.set_font_size(38)
            c.move_to(cx + 106, cy + 82)
            c.set_source_rgba(cr, cg, cb, a_a)
            c.show_text(f"{self.objs[kt - 1]['short']} \u2248 this dot")
            c.new_path()
        for ev in self._ev:
            dtp = t - ev["t"]
            if 0 <= dtp < 0.6:
                k = dtp / 0.6
                c.set_source_rgba(*[x / 255 for x in ev["color_rgb"]], 0.55 * (1 - k) ** 2)
                c.set_line_width(4)
                c.arc(cx, cy, ev["ring_radius_px"] + 90 * k, 0, 6.2832)
                c.stroke()
        lad_a = float(sstep((t - 1.8) / 0.6))
        if lad_a > 0.01:
            c.push_group()
            self._ladder(c, t)
            c.pop_group_to_source()
            c.paint_with_alpha(lad_a)
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
        # comparison block (one jump sentence per step) and, at the very end, the grand ratio
        last = len(self.objs) - 1
        blocks = []                                      # (object index, alpha)
        if st["type"] == "hold" and kt > 0:
            blocks.append((kt, float(sstep((t - st["t0"]) / 0.35))))
        elif st["type"] == "trans" and kt - 1 > 0:
            blocks.append((kt - 1, 1 - float(sstep((t - st["t0"]) / 0.25))))
        rev = 0.0
        if kt == last and st["type"] == "hold":
            rev = float(sstep((t - st["t0"] - self.tl["final_ratio_delay"]) / 0.5))
        for idx, al in blocks:
            al *= 1 - rev
            if al <= 0.01:
                continue
            mult, cap, vol = self.jump(idx)
            self._text(c, mult, cx, 1340, 112, (1, 0.85, 0.35, al), max_w=880)
            self._text(c, cap, cx, 1404, 44, (1, 1, 1, al), bold=False, max_w=820)
            if vol:
                self._text(c, vol, cx, 1460, 38, (0.75, 0.88, 1.0, al), bold=False, max_w=860)
        if rev > 0:
            self._text(c, "UNIVERSE \u00f7 ATOM", cx, 1340, 36, (0.6, 0.7, 0.85, rev), bold=False)
            self._text(c, sci(self.ratio), cx, 1450, 120, (1, 0.85, 0.35, rev))
        return np.frombuffer(self.surf.get_data(), np.uint8).reshape(H, W, 4)

    def contact_sheet(self, path, n=12, cols=4):
        w, h = self.W // 4, self.H // 4
        rows = math.ceil(n / cols)
        sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * cols, h * rows)
        c = cairo.Context(sheet)
        mids = [(o["t_hold0"] + 0.6 * o["H"]) for o in self.objs]
        trs = [sg for sg in self.seg if sg["type"] == "trans"]
        times = sorted(mids + [(trs[3]["t0"] + trs[3]["t1"]) / 2, (trs[7]["t0"] + trs[7]["t1"]) / 2])[:n]
        for i, t in enumerate(times):
            self.draw(min(t, self.D - 0.05))
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
        k = int((self.objs[-1]["t_hold0"] + 0.05) * SR)
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
