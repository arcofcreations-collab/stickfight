"""ambience.py - atmosphere for stickfight (v3).

Post-processing (numpy, once per output frame, after motion blur):
  grade      per-act colour grading (lift / gain / saturation LUTs)
  rays       god rays from the sun or the sky eye
  mist       volumetric haze along the ground and the horizon, drifting
  shimmer    heat shimmer (rows wobble) over burning scenes
  glow       warm light around fires, with flicker
  vignette + film grain
In-world (skia, per sub-frame):
  ash        drifting ash flakes        birds    flocks fleeing across the sky
  flags      cloth banners on roofs     crowd    distant townsfolk silhouettes on the horizon
"""
import math, random
import numpy as np
import skia

RED = (206, 22, 44)

GRADES = {
    "neutral": dict(gain=(1.0, 1.0, 1.0), lift=(0, 0, 0), sat=1.0, con=1.0),
    "warm":    dict(gain=(1.05, 0.98, 0.88), lift=(10, 4, 0), sat=1.0, con=1.04),
    "dusk":    dict(gain=(1.06, 0.95, 0.84), lift=(14, 4, 0), sat=1.05, con=1.06),
    "cold":    dict(gain=(0.86, 0.93, 1.08), lift=(0, 4, 14), sat=0.85, con=1.08),
    "war":     dict(gain=(1.08, 0.94, 0.9), lift=(6, 0, 0), sat=1.1, con=1.12),
    "blood":   dict(gain=(1.05, 0.95, 0.95), lift=(4, 0, 0), sat=1.1, con=1.15),
    "dawn":    dict(gain=(1.03, 1.0, 0.94), lift=(16, 12, 6), sat=0.92, con=0.96),
    "memory":  dict(gain=(1.0, 0.97, 0.9), lift=(30, 24, 16), sat=0.45, con=0.85),
}
PAL_GRADE = {"paper": "neutral", "dusk": "dusk", "night": "cold", "blood": "blood", "dawn": "dawn"}


class Post:
    """all post effects run on PIL's C routines (numpy was too slow on the loaded laptop)."""
    def __init__(self, W, H, seed=1):
        from PIL import Image
        self.W, self.H = W, H
        self._luts = {}
        r = np.random.default_rng(seed)
        self.grain = [Image.fromarray(r.integers(0, 9, size=(H, W, 3), dtype=np.uint8)) for _ in range(4)]
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xx - W / 2) / (W * 0.6)) ** 2 + ((yy - H / 2) / (H * 0.6)) ** 2)
        v = (255 * (1 - 0.32 * np.clip((d - 0.45) / 0.85, 0, 1) ** 1.5)).astype(np.uint8)
        self.vig = Image.fromarray(np.dstack([v, v, v]))
        self.lw, self.lh = W // 8, H // 8
        self.ly, self.lx = np.mgrid[0:self.lh, 0:self.lw].astype(np.float32)
        self.img = None

    def begin(self, buf):
        from PIL import Image
        self.img = Image.fromarray(buf[:, :, :3])

    def end(self, buf):
        buf[:, :, :3] = np.asarray(self.img)

    # ------------------------------------------------------------------ grade
    def grade(self, buf, name):
        from PIL import ImageEnhance
        if not name or name == "neutral": return
        g = GRADES[name]
        if name not in self._luts:
            v = np.arange(256, dtype=np.float32); lut = []
            for ch in range(3):
                x = (v - 128) * g["con"] + 128
                x = x * g["gain"][ch] + g["lift"][ch] * (1 - v / 255)
                lut += [int(q) for q in np.clip(x, 0, 255).astype(np.uint8)]
            self._luts[name] = lut
        if g["sat"] != 1.0:
            self.img = ImageEnhance.Color(self.img).enhance(g["sat"])
        self.img = self.img.point(self._luts[name])

    # ------------------------------------------------------------------ god rays
    def rays(self, buf, sx, sy, t, strength=0.16, color=(255, 236, 228)):
        from PIL import Image, ImageChops
        lx = self.lx * 8 - sx; ly = self.ly * 8 - sy
        ang = np.arctan2(ly, lx)
        rad = np.sqrt(lx * lx + ly * ly) / max(self.W, self.H)
        shafts = (0.5 + 0.5 * np.sin(ang * 13 + t * 0.35)) ** 6 * (0.6 + 0.4 * np.sin(ang * 5 - t * 0.21))             + 0.5 * (0.5 + 0.5 * np.sin(ang * 29 - t * 0.5)) ** 10
        inten = shafts * np.exp(-rad * 2.2) * np.clip(rad * 6, 0, 1) * strength
        small = np.clip(inten[:, :, None] * np.array(color, np.float32), 0, 255).astype(np.uint8)
        layer = Image.fromarray(small).resize((self.W, self.H), Image.BILINEAR)
        self.img = ImageChops.add(self.img, layer)

    # ------------------------------------------------------------------ mist / haze
    def mist(self, buf, ground_y, t, color, strength=0.35, horizon=True):
        from PIL import Image
        H, W = self.H, self.W
        y0 = int(max(0, ground_y - H * 0.32)); y1 = int(min(H, ground_y + H * 0.12))
        if y1 - y0 < 8: return
        hh = max(2, (y1 - y0) // 8); ww = self.lw
        ys = np.linspace(y0, y1, hh, dtype=np.float32)
        row = np.exp(-((ys - ground_y + H * 0.04) / (H * 0.11)) ** 2) * strength
        xs = np.linspace(0, W, ww, dtype=np.float32)
        col = 0.65 + 0.2 * np.sin(xs * 0.006 + t * 0.4) + 0.15 * np.sin(xs * 0.017 - t * 0.7)
        a = np.clip(row[:, None] * col[None, :] * 255, 0, 255).astype(np.uint8)
        mask = Image.fromarray(a, "L").resize((W, y1 - y0), Image.BILINEAR)
        region = self.img.crop((0, y0, W, y1))
        fog = Image.new("RGB", region.size, tuple(int(c) for c in color))
        self.img.paste(Image.composite(fog, region, mask), (0, y0))

    # ------------------------------------------------------------------ heat shimmer
    def shimmer(self, buf, t, amp=2.5, y_from=0.55):
        H, W = self.H, self.W
        arr = np.asarray(self.img).copy()
        y0 = int(H * y_from)
        ys = np.arange(y0, H)
        shift = (amp * np.sin(ys * 0.09 + t * 11) * np.sin(ys * 0.013 + t * 2.3)).round().astype(np.int32)
        for s in np.unique(shift):
            if s == 0: continue
            rows = ys[shift == s]
            arr[rows] = np.roll(arr[rows], s, axis=1)
        from PIL import Image
        self.img = Image.fromarray(arr)

    # ------------------------------------------------------------------ fire glow + flicker
    def glow(self, buf, x, y, r, t, color=(255, 150, 80), strength=0.35):
        from PIL import Image, ImageChops
        fl = 1 + 0.18 * math.sin(t * 23) * math.sin(t * 7.7 + 1)
        r = int(r * fl)
        x0, y0 = int(x - r), int(y - r)
        if r < 4 or x0 > self.W or y0 > self.H or x + r < 0 or y + r < 0: return
        n = 48
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        d = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2) / (n / 2)
        a = np.clip(1 - d, 0, 1) ** 2 * strength * fl
        small = np.clip(a[:, :, None] * np.array(color, np.float32), 0, 255).astype(np.uint8)
        layer = Image.fromarray(small).resize((2 * r, 2 * r), Image.BILINEAR)
        box = (max(0, x0), max(0, y0), min(self.W, x0 + 2 * r), min(self.H, y0 + 2 * r))
        if box[2] <= box[0] or box[3] <= box[1]: return
        lay = layer.crop((box[0] - x0, box[1] - y0, box[2] - x0, box[3] - y0))
        region = self.img.crop(box)
        self.img.paste(ImageChops.add(region, lay), box[:2])

    def vignette_grain(self, buf, fi, grain=True):
        from PIL import ImageChops
        self.img = ImageChops.multiply(self.img, self.vig)
        if grain:
            self.img = ImageChops.add(self.img, self.grain[fi % len(self.grain)], scale=1.0, offset=-4)


# ---------------------------------------------------------------------- in-world
def ash(c, W, H, t, cam, color, sc, n=80, seed=11):
    r = random.Random(seed)
    p = skia.Paint(AntiAlias=True)
    for i in range(n):
        x0, sp, sz, ph, sw = r.uniform(0, 1), r.uniform(0.03, 0.09), r.uniform(1.5, 4.0), r.uniform(0, 1), r.uniform(0, 6.28)
        y = ((ph + t * sp) % 1.0) * (H + 40) - 20
        x = (x0 * W + math.sin(t * 0.9 + sw) * 40 + t * 22 * sz - cam["cx"] * cam["z"] * 0.1 * sz / 3) % (W + 40) - 20
        p.setColor(skia.Color(int(color[0]), int(color[1]), int(color[2]), 150))
        c.drawRect(skia.Rect(x, y, x + sz * sc * 1.6, y + sz * sc), p)


def birds(c, e, t, W, H, color):
    dt = t - e["t"]
    if dt < 0 or dt > e.get("life", 4.0): return
    r = random.Random(e["seed"])
    p = skia.Paint(AntiAlias=True, Color=skia.Color(int(color[0]), int(color[1]), int(color[2])), Style=skia.Paint.kStroke_Style,
                   StrokeWidth=3 * W / 1920, StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
    for i in range(e.get("n", 18)):
        sx = (e.get("x", 0.5) + r.uniform(-0.12, 0.12)) * W; sy = (e.get("y", 0.6) + r.uniform(-0.06, 0.06)) * H
        vx = (e.get("dir", 1) * r.uniform(120, 260)) * W / 1920; vy = -r.uniform(90, 220) * H / 1080
        delay = r.uniform(0, 0.5)
        d = max(0.0, dt - delay)
        x = sx + vx * d; y = sy + vy * d + 20 * math.sin(d * 3 + i)
        s = r.uniform(7, 13) * W / 1920 * (1 + 0.15 * d)
        flap = math.sin(d * 18 + i * 1.7)
        path = skia.Path(); path.moveTo(x - s, y - s * 0.5 * flap); path.lineTo(x, y + s * 0.15); path.lineTo(x + s, y - s * 0.5 * flap)
        c.drawPath(path, p)


def flag(c, x, y, t, color, ink, size=1.0, wind=1.0, pole=70):
    pp = skia.Paint(AntiAlias=True, Color=skia.Color(int(ink[0]), int(ink[1]), int(ink[2])), StrokeWidth=3 * size,
                    Style=skia.Paint.kStroke_Style)
    c.drawLine(x, y, x, y + pole * size, pp)
    top = y + pole * size; L = 46 * size; Hh = 22 * size
    up, dn = [], []
    for k in range(9):
        u = k / 8
        wv = math.sin(t * 6 * wind - u * 5 + x * 0.01) * 6 * size * u
        up.append((x - u * L, top + wv)); dn.append((x - u * L, top - Hh + wv * 1.1 + u * 3 * size))
    p = skia.Path(); p.moveTo(*up[0])
    for q in up[1:]: p.lineTo(*q)
    for q in reversed(dn): p.lineTo(*q)
    p.close()
    c.drawPath(p, skia.Paint(AntiAlias=True, Color=skia.Color(int(color[0]), int(color[1]), int(color[2]))))


def crowd(c, seed, cx, t, color, x0, x1, n=40):
    """distant townsfolk silhouettes standing on the ground line of a far layer (drawn in that layer's coords)."""
    r = random.Random(seed)
    p = skia.Paint(AntiAlias=True, Color=skia.Color(int(color[0]), int(color[1]), int(color[2])), StrokeWidth=7,
                   Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
    hp = skia.Paint(AntiAlias=True, Color=skia.Color(int(color[0]), int(color[1]), int(color[2])))
    for i in range(n):
        x = r.uniform(x0, x1) + math.sin(t * 0.4 + i) * 20 * r.random()
        h = r.uniform(0.75, 1.0)
        sw = math.sin(t * 2 + i) * 8 * (i % 3 == 0)
        c.drawLine(x, 0, x - 10 + sw, 48 * h, p); c.drawLine(x + 12 - sw, 0, x - 10 + sw, 48 * h, p)   # legs
        c.drawLine(x - 10 + sw, 48 * h, x - 6, 110 * h, p)                                             # body
        c.drawCircle(x - 5, 128 * h, 15 * h, hp)
