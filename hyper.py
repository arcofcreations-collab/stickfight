"""hyper.py - the big-moment FX for stickfight (v2).

All functions are pure functions of (event, action time) so frames stay independent.
  aura       anime-style flame aura + rising sparks + lightning (Actor.power windows)
  hair       spiky power-up hair
  ghost      afterimage of an actor frozen at the event time, fading
  lift       ground pieces rise and float during a charge-up, then blast outward at release
  burst      screen-filling energy burst (white-out disk, then a ring and spikes)
  beam       two energy beams meeting at a clash point that is pushed back and forth
  prop       a thrown or knocked-away sword spinning along an arc (optionally stuck in the ground)
  fire       campfire flicker with embers
  skysplit   the final strike: a jagged split across the sky that opens up
  bolt       a lightning arc between two points
"""
import math, random
import skia

RED = (206, 22, 44)
WHITE = (255, 251, 245)


def C(rgb, a=255):
    return skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(max(0, min(255, a))))


def _noise(i, t, k=1.0):
    return math.sin(i * 12.9898 + t * 7.3 * k) * 0.5 + math.sin(i * 4.1414 + t * 13.1 * k + 1.3) * 0.5


def poly(c, pts, paint):
    p = skia.Path(); p.moveTo(*pts[0])
    for q in pts[1:]: p.lineTo(*q)
    p.close(); c.drawPath(p, paint)


def aura(c, st, s, level, t, col=RED, core=WHITE, inv=False):
    """flame aura around a figure. st = renderer state dict (world joints), s = scale."""
    W = st["W"]
    hx, hy = W["hip"]; nx, ny = W["neck"]
    cx, cy = (hx + nx) / 2, (hy + ny) / 2 + 10 * s
    rx, ry = 62 * s * level ** 0.5, 120 * s * level ** 0.5
    n = 30
    for layer, (scl, colr, al) in enumerate(((1.0, col, 170), (0.7, core, 150))):
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            up = max(0.0, math.sin(a))                    # flames lick upward
            r = 1 + 0.18 * _noise(i + layer * 7, t * 2.2)
            spike = (0.55 + 0.45 * math.sin(i * 2.7 + t * 24)) * up * (0.9 if i % 2 == 0 else 0.25)
            px = cx + math.cos(a) * rx * scl * r
            py = cy + math.sin(a) * ry * scl * r + spike * ry * 0.85 * scl
            pts.append((px, py))
        poly(c, pts, skia.Paint(AntiAlias=True, Color=C(colr if not inv else (0, 0, 0), al * min(1.0, 0.35 + level * 0.33))))
    # rising sparks
    rr = random.Random(int(t * 30))
    p = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=3 * s, StrokeCap=skia.Paint.kRound_Cap)
    for i in range(int(10 * level)):
        ph = (t * 1.6 + i * 0.137) % 1.0
        x = cx + (rr.random() - 0.5) * rx * 2.2
        y = cy - ry * 0.8 + ph * ry * 2.6
        p.setColor(C(core if i % 2 else col, 255 * (1 - ph)))
        c.drawLine(x, y, x, y + 24 * s, p)
    if level >= 1.5:
        for k in range(2):
            r2 = random.Random(int(t * 15) * 7 + k)
            a0 = r2.uniform(0, 6.28); a1 = a0 + r2.uniform(0.8, 2.2)
            bolt(c, (cx + math.cos(a0) * rx, cy + math.sin(a0) * ry), (cx + math.cos(a1) * rx * 1.1, cy + math.sin(a1) * ry * 1.1),
                 r2, core, 3 * s)


def bolt(c, a, b, r, col, w):
    pts = [a]
    for i in range(1, 7):
        u = i / 7
        pts.append((a[0] + (b[0] - a[0]) * u + r.uniform(-14, 14), a[1] + (b[1] - a[1]) * u + r.uniform(-14, 14)))
    pts.append(b)
    p = skia.Path(); p.moveTo(*pts[0])
    for q in pts[1:]: p.lineTo(*q)
    c.drawPath(p, skia.Paint(AntiAlias=True, Color=C(col), Style=skia.Paint.kStroke_Style, StrokeWidth=w,
                             StrokeJoin=skia.Paint.kMiter_Join))


def hair(c, st, s, f, ink, t, level=1.0):
    hx, hy = st["W"]["head"]; hr = 15 * s
    path = skia.Path()
    n = 6
    for i in range(n):
        a = math.radians(70 + i * 22)          # fan from the front-top round to the back
        ang = math.radians(-f * (i * 22 - 40) + 90) if False else None
        bx = hx - f * math.cos(a) * hr * 0.9; by = hy + math.sin(a) * hr * 0.9
        L = hr * (1.6 + 0.6 * math.sin(i * 1.9 + t * 30) * 0.3) * level ** 0.5
        dx = -f * math.cos(a) * L * 1.1 - f * L * 0.25; dy = math.sin(a) * L + L * 0.35
        w = hr * 0.42
        path.moveTo(bx - w * math.sin(a), by - w * math.cos(a) * 0.3)
        path.lineTo(bx + dx, by + dy)
        path.lineTo(bx + w * math.sin(a), by + w * math.cos(a) * 0.3)
        path.close()
    c.drawPath(path, skia.Paint(AntiAlias=True, Color=C(ink)))


def ghost(c, R, a, e, ta, pal):
    dt = ta - e["t"]; life = e.get("life", 0.45)
    if dt < 0 or dt > life: return
    st = R.state(a, e["t"])
    col = RED if e.get("color", "red") == "red" else pal["ink"]
    if pal["bg1"][0] > 150 and pal["bg1"][1] < 60: col = pal["ink"]      # blood palette: red on red would vanish
    if pal.get("inv"): col = pal["ink"]
    R._figure(c, a, st, col, 0.55 * (1 - dt / life), pal, ghost=True, wide=1.0)


def lift(c, e, ta, pal):
    """rocks rise during [t, t_release] and blast outward after it."""
    r = random.Random(e["seed"])
    x0 = e["x"]; rad = e.get("radius", 400); n = e.get("n", 26)
    t0, t1 = e["t"], e["t_release"]
    if ta < t0: return
    col = pal["near"] if not pal.get("inv") else pal["ink"]
    for i in range(n):
        px = x0 + r.uniform(-rad, rad); sz = r.uniform(8, 30) * e.get("size", 1.0)
        hmax = r.uniform(40, 380); delay = r.uniform(0, 0.6) * (t1 - t0)
        spin = r.uniform(-3, 3); bob = r.uniform(0, 6.28)
        pts = [(math.cos(q) * r.uniform(0.5, 1.0), math.sin(q) * r.uniform(0.5, 1.0))
               for q in sorted(r.uniform(0, 6.28) for _ in range(r.randint(4, 6)))]
        if ta < t1:
            u = max(0.0, min(1.0, (ta - t0 - delay) / max(0.2, (t1 - t0 - delay))))
            y = sz * 0.4 + hmax * (1 - (1 - u) ** 2) + 6 * math.sin(ta * 3 + bob)
            x = px; ang = spin * (ta - t0) * 0.6
        else:
            dt = ta - t1
            if dt > 2.0: continue
            yb = sz * 0.4 + hmax + 6 * math.sin(t1 * 3 + bob)
            dirx = (px - x0) / max(1, abs(px - x0)) if abs(px - x0) > 1 else r.choice((-1, 1))
            sp = e.get("blast", 1400) * r.uniform(0.5, 1.0)
            x = px + dirx * sp * dt; y = yb + 300 * dt - 900 * dt * dt
            if y < -200: continue
            ang = spin * (t1 - t0) * 0.6 + spin * dt * 4
        ca, sa = math.cos(ang), math.sin(ang)
        poly(c, [(x + qx * sz * ca - qy * sz * sa, y + qx * sz * sa + qy * sz * ca) for qx, qy in pts],
             skia.Paint(AntiAlias=True, Color=C(col)))


def burst(c, e, ta, pal, pos):
    dt = ta - e["t"]; life = e.get("life", 0.7)
    if dt < 0 or dt > life: return
    x, y = pos; R = e.get("size", 3000)
    col = RED if e.get("color") == "red" else WHITE
    ink = pal["ink"]
    if dt < 0.14:      # white-out disk racing to the frame edge
        u = dt / 0.14
        c.drawCircle(x, y, R * (0.15 + 0.85 * u), skia.Paint(AntiAlias=True, Color=C(col)))
        c.drawCircle(x, y, R * (0.15 + 0.85 * u) * 0.55, skia.Paint(AntiAlias=True, Color=C(WHITE)))
    else:
        u = (dt - 0.14) / (life - 0.14)
        rr = R * (1.0 + 0.6 * u)
        c.drawCircle(x, y, rr * 0.3, skia.Paint(AntiAlias=True, Color=C(col, 255 * (1 - u)), Style=skia.Paint.kStroke_Style,
                                               StrokeWidth=R * 0.06 * (1 - u) + 2))
        r = random.Random(e["seed"])
        p = skia.Path()
        for i in range(36):
            a = r.uniform(0, 6.28); w0 = r.uniform(0.01, 0.03)
            r0 = R * (0.12 + 0.3 * u); r1 = R * (0.5 + 0.9 * u) * r.uniform(0.6, 1.0)
            p.moveTo(x + math.cos(a - w0) * r0, y + math.sin(a - w0) * r0); p.lineTo(x + math.cos(a) * r1, y + math.sin(a) * r1)
            p.lineTo(x + math.cos(a + w0) * r0, y + math.sin(a + w0) * r0); p.close()
        c.drawPath(p, skia.Paint(AntiAlias=True, Color=C(ink if not pal.get("inv") else WHITE, 200 * (1 - u))))


def beam(c, e, ta, pal, ha, hb, s=1.0):
    """ha/hb = hand positions of the two fighters. e['push'] = list of (t, frac) keys (frac 0 = at A, 1 = at B)."""
    if not (e["t"] <= ta <= e["t1"]): return None
    keys = e["push"]
    frac = keys[-1][1]
    for (t0, f0), (t1, f1) in zip(keys, keys[1:]):
        if t0 <= ta <= t1:
            u = (ta - t0) / max(1e-6, t1 - t0); u = u * u * (3 - 2 * u); frac = f0 + (f1 - f0) * u; break
    if ta < keys[0][0]: frac = keys[0][1]
    frac += 0.025 * math.sin(ta * 37) + 0.015 * math.sin(ta * 61)
    mx, my = ha[0] + (hb[0] - ha[0]) * frac, ha[1] + (hb[1] - ha[1]) * frac
    grow = min(1.0, (ta - e["t"]) / 0.12)
    for (p0, colo, coli) in ((ha, e.get("colA", WHITE), WHITE), (hb, e.get("colB", RED), (255, 170, 170))):
        dx, dy = mx - p0[0], my - p0[1]; L = math.hypot(dx, dy) or 1; nx, ny = -dy / L, dx / L
        for (wid, col, al) in ((46 * s, colo, 230), (18 * s, coli, 255)):
            pts_l, pts_r = [], []
            for i in range(13):
                u = i / 12
                w = wid * grow * (0.45 + 0.55 * u) * (1 + 0.18 * math.sin(i * 1.7 + ta * 45))
                bx, by = p0[0] + dx * u, p0[1] + dy * u
                pts_l.append((bx + nx * w, by + ny * w)); pts_r.append((bx - nx * w, by - ny * w))
            poly(c, pts_l + pts_r[::-1], skia.Paint(AntiAlias=True, Color=C(col, al)))
        if colo == WHITE:  # outline the white beam so it reads on paper
            pass
    rad = (70 + 18 * math.sin(ta * 50)) * s * grow
    r = random.Random(int(ta * 60))
    star = []
    for i in range(24):
        a = math.pi * i / 12 + r.uniform(-0.1, 0.1); rr = rad * (1.9 if i % 2 == 0 else 0.8) * r.uniform(0.8, 1.3)
        star.append((mx + math.cos(a) * rr, my + math.sin(a) * rr))
    poly(c, star, skia.Paint(AntiAlias=True, Color=C(pal["ink"] if not pal.get("inv") else WHITE)))
    c.drawCircle(mx, my, rad, skia.Paint(AntiAlias=True, Color=C(WHITE)))
    c.drawCircle(mx, my, rad * 0.55, skia.Paint(AntiAlias=True, Color=C((255, 230, 230))))
    pz = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=4 * s, StrokeCap=skia.Paint.kRound_Cap)
    for i in range(14):
        a = r.uniform(0, 6.28); v = r.uniform(rad * 1.2, rad * 3.2)
        pz.setColor(C(WHITE if i % 2 else RED))
        c.drawLine(mx + math.cos(a) * rad, my + math.sin(a) * rad, mx + math.cos(a) * v, my + math.sin(a) * v, pz)
    return (mx, my)


def prop(c, e, ta, pal, p0, p1):
    """a sword flying along an arc from p0 to p1 during [t, t1], spinning; stays stuck after if e['stick']."""
    t0, t1 = e["t"], e["t1"]
    if ta < t0: return
    if e.get("kind_") in ("gem", "coin"):
        if ta > t1 and not e.get("stick"): return
        u = min(1.0, (ta - t0) / max(1e-6, t1 - t0))
        x = p0[0] + (p1[0] - p0[0]) * u; y = p0[1] + (p1[1] - p0[1]) * u + 4 * e.get("h", 200) * u * (1 - u)
        if e["kind_"] == "gem": gem(c, x, y, e.get("size", 14), ta)
        else: coin(c, x, y, e.get("size", 9), ta, pal["ink"])
        return
    L = e.get("len", 96) * e.get("scale", 1.0)
    col = RED if e.get("color") == "red" else pal["ink"]
    if ta <= t1:
        u = (ta - t0) / max(1e-6, t1 - t0)
        x = p0[0] + (p1[0] - p0[0]) * u; y = p0[1] + (p1[1] - p0[1]) * u + 4 * e.get("h", 200) * u * (1 - u)
        ang = e.get("a0", 90) + e.get("spins", 2) * 360 * u
    else:
        if not e.get("stick") or ta > e.get("until", t1 + 1e9): return
        x, y = p1; ang = e.get("stick_ang", -100)
        y = max(y, L * 0.55)
    a = math.radians(ang)
    dx, dy = math.cos(a) * L / 2, math.sin(a) * L / 2
    c.drawLine(x - dx, y - dy, x + dx, y + dy, skia.Paint(AntiAlias=True, Color=C(col), StrokeWidth=4.5 * e.get("scale", 1.0),
                                                       Style=skia.Paint.kStroke_Style))
    gx, gy = x - dx * 0.62, y - dy * 0.62
    c.drawLine(gx - dy * 0.18, gy + dx * 0.18, gx + dy * 0.18, gy - dx * 0.18,
               skia.Paint(AntiAlias=True, Color=C(pal["ink"]), StrokeWidth=7, Style=skia.Paint.kStroke_Style))
    if e.get("ribbon") and ta > e.get("ribbon_t", 0):
        rp = skia.Path(); rp.moveTo(gx, gy)
        for k in range(1, 8):
            rp.lineTo(gx - k * 9, gy - k * 2 + 5 * math.sin(ta * 9 + k))
        c.drawPath(rp, skia.Paint(AntiAlias=True, Color=C(RED), Style=skia.Paint.kStroke_Style, StrokeWidth=7,
                                  StrokeCap=skia.Paint.kRound_Cap))


def fire(c, e, ta, pal):
    if not (e["t"] <= ta <= e["t1"]): return
    x, y = e["pos"]; s = e.get("size", 1.0)
    # logs
    lp = skia.Paint(AntiAlias=True, Color=C(pal["ink"]), StrokeWidth=9 * s, Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
    c.drawLine(x - 34 * s, y + 4, x + 30 * s, y + 16 * s, lp); c.drawLine(x - 30 * s, y + 16 * s, x + 34 * s, y + 4, lp)
    for k, (col, sc) in enumerate(((RED, 1.0), ((255, 190, 120), 0.62), (WHITE, 0.32))):
        pts = []
        n = 14
        for i in range(n):
            a = math.pi * i / (n - 1)
            r = 34 * s * sc * (1 + 0.25 * _noise(i + k * 5, ta * 3))
            h = (1.6 + 0.9 * max(0.0, math.sin(i * 1.3 + ta * 17))) if 0 < i < n - 1 else 0.3
            pts.append((x + math.cos(a) * r, y + 10 * s + math.sin(a) * r * h * (1.4 if i % 2 else 1.0)))
        poly(c, pts, skia.Paint(AntiAlias=True, Color=C(col)))
    r = random.Random(3)
    for i in range(10):
        ph = (ta * 0.7 + i * 0.1) % 1.0
        ex = x + (r.random() - 0.5) * 60 * s + math.sin(ta * 3 + i) * 12
        c.drawCircle(ex, y + 40 * s + ph * 220 * s, 2.5 * s * (1 - ph) + 0.5, skia.Paint(AntiAlias=True, Color=C(RED, 255 * (1 - ph))))


def skysplit(c, e, ta, W, H, pal):
    dt = ta - e["t"]
    if dt < 0 or dt > e.get("life", 3.0): return
    r = random.Random(e["seed"])
    u = min(1.0, dt / 0.18)
    gap = min(60, dt * 160) * (W / 1920)
    y0 = H * e.get("y", 0.28); pts = []
    x = 0
    while x <= W:
        pts.append((x, y0 + (x - W / 2) * e.get("slope", -0.08) + r.uniform(-18, 18)))
        x += W / 24
    pts = pts[:max(2, int(len(pts) * u))]
    up = [(px, py - gap) for px, py in pts]; dn = [(px, py + gap) for px, py in pts]
    poly(c, up + dn[::-1], skia.Paint(AntiAlias=True, Color=C(WHITE)))
    p = skia.Path(); p.moveTo(*pts[0])
    for q in pts[1:]: p.lineTo(*q)
    c.drawPath(p, skia.Paint(AntiAlias=True, Color=C(RED), Style=skia.Paint.kStroke_Style, StrokeWidth=max(3, gap * 0.35)))


def gem(c, x, y, s, t, glow=True):
    """the glowing relic: a red diamond with a pulsing halo"""
    pulse = 1 + 0.12 * math.sin(t * 9)
    if glow:
        c.drawCircle(x, y, s * 2.4 * pulse, skia.Paint(AntiAlias=True, Color=C(RED, 70)))
        c.drawCircle(x, y, s * 1.6 * pulse, skia.Paint(AntiAlias=True, Color=C((255, 120, 120), 90)))
    pts = [(x, y + s * 1.3), (x + s * 0.8, y), (x, y - s * 1.3), (x - s * 0.8, y)]
    poly(c, pts, skia.Paint(AntiAlias=True, Color=C(RED)))
    poly(c, [(x, y + s * 0.9), (x + s * 0.35, y + s * 0.1), (x, y - s * 0.4)], skia.Paint(AntiAlias=True, Color=C((255, 200, 200))))


def coin(c, x, y, s, t, ink):
    w = abs(math.cos(t * 22)) * s + 1
    c.drawOval(skia.Rect(x - w, y - s, x + w, y + s), skia.Paint(AntiAlias=True, Color=C((235, 196, 90))))
    c.drawOval(skia.Rect(x - w, y - s, x + w, y + s), skia.Paint(AntiAlias=True, Color=C(ink), Style=skia.Paint.kStroke_Style, StrokeWidth=2))
