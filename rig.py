"""rig.py - 2D stick-figure skeleton, pose library, cycles and keyframe tracks.

World units: y is up, ground is y=0. A standard figure is ~196 units tall.
Angles are degrees. Limb angles are measured from "straight down", positive =
toward the way the figure faces. Arms are relative to the torso, legs are
absolute. Elbow/knee/weapon are relative to the bone before them.
`rot` spins the whole body (positive = forward flip).
"""
import math

TORSO, NECK, HEAD_R, UARM, FARM, THIGH, SHIN = 62.0, 7.0, 15.0, 40.0, 38.0, 49.0, 48.0
KEYS = ("lean", "head", "sF", "eF", "sB", "eB", "hF", "kF", "hB", "kB", "w", "rot")
ZERO = dict.fromkeys(KEYS, 0.0)
ZERO["w"] = 40.0

def P(**kw):
    d = dict(ZERO); d.update({k: float(v) for k, v in kw.items()}); return d

# ---------------------------------------------------------------- pose library
POSES = {
    "stand":   P(lean=2, sF=8, eF=10, sB=-6, eB=12, hF=4, kF=-3, hB=-4, kB=-2, w=150),
    "guard":   P(lean=10, head=-4, sF=34, eF=78, sB=-14, eB=70, hF=24, kF=-28, hB=-20, kB=-14, w=36),
    "guard_lo":P(lean=16, sF=20, eF=40, sB=-20, eB=60, hF=34, kF=-52, hB=-26, kB=-30, w=70),
    "fists":   P(lean=12, sF=46, eF=104, sB=26, eB=118, hF=22, kF=-26, hB=-20, kB=-16, w=150),
    "cross":   P(lean=-2, sF=28, eF=118, sB=36, eB=112, hF=6, kF=-2, hB=-6, kB=-2, w=150),  # arms folded
    "crouch":  P(lean=34, sF=30, eF=40, sB=-20, eB=50, hF=72, kF=-118, hB=24, kB=-118, w=110),
    "land":    P(lean=40, head=10, sF=60, eF=10, sB=-60, eB=20, hF=84, kF=-128, hB=10, kB=-112, w=120),
    "tuck":    P(lean=30, sF=60, eF=80, sB=40, eB=90, hF=110, kF=-150, hB=90, kB=-140, w=90),
    "jump":    P(lean=6, sF=150, eF=10, sB=130, eB=20, hF=40, kF=-80, hB=-20, kB=-40, w=40),
    "fall":    P(lean=-30, head=-20, sF=120, eF=30, sB=160, eB=40, hF=40, kF=-30, hB=10, kB=-60, w=200),
    "down":    P(rot=-92, lean=0, head=-10, sF=150, eF=20, sB=-30, eB=10, hF=8, kF=-4, hB=-6, kB=-10, w=60),
    "downF":   P(rot=88, lean=0, head=10, sF=160, eF=10, sB=-20, eB=10, hF=4, kF=-20, hB=-8, kB=-30, w=90),
    "kneel":   P(lean=16, head=14, sF=10, eF=20, sB=-8, eB=10, hF=86, kF=-92, hB=-16, kB=-86, w=170),
    "kneel_hold": P(lean=30, head=24, sF=50, eF=50, sB=40, eB=60, hF=90, kF=-96, hB=-12, kB=-86, w=170),
    "rise":    P(lean=4, head=-12, sF=-20, eF=20, sB=-26, eB=16, hF=10, kF=-10, hB=-12, kB=-6, w=170),
    "hit":     P(lean=-26, head=-24, sF=-30, eF=40, sB=-60, eB=30, hF=12, kF=-12, hB=-30, kB=-24, w=200),
    "hit_lo":  P(lean=42, head=20, sF=40, eF=10, sB=10, eB=10, hF=30, kF=-60, hB=-10, kB=-50, w=150),
    "hit_air": P(lean=-40, head=-30, sF=150, eF=40, sB=120, eB=30, hF=50, kF=-60, hB=20, kB=-90, w=220),
    "block":   P(lean=-4, head=-6, sF=58, eF=104, sB=-10, eB=70, hF=10, kF=-12, hB=-34, kB=-20, w=26),
    "block_lo":P(lean=24, sF=40, eF=30, sB=-20, eB=40, hF=40, kF=-70, hB=-30, kB=-30, w=100),
    # sword: windups / follow-throughs
    "hi_wind": P(lean=-8, head=-4, sF=176, eF=24, sB=150, eB=40, hF=20, kF=-20, hB=-26, kB=-10, w=70),
    "hi_cut":  P(lean=28, head=10, sF=60, eF=6, sB=40, eB=10, hF=46, kF=-56, hB=-36, kB=-6, w=20),
    "h_wind":  P(lean=-6, sF=-70, eF=50, sB=40, eB=80, hF=14, kF=-14, hB=-24, kB=-12, w=100),
    "h_cut":   P(lean=24, sF=104, eF=0, sB=-40, eB=30, hF=50, kF=-50, hB=-40, kB=-6, w=-4),
    "up_wind": P(lean=34, sF=-50, eF=10, sB=10, eB=40, hF=56, kF=-90, hB=-20, kB=-50, w=150),
    "up_cut":  P(lean=-14, head=-12, sF=178, eF=4, sB=-40, eB=20, hF=20, kF=-20, hB=-30, kB=-10, w=0),
    "thrust_w":P(lean=-4, sF=-30, eF=120, sB=40, eB=60, hF=20, kF=-30, hB=-20, kB=-20, w=-30),
    "thrust":  P(lean=26, sF=86, eF=2, sB=-50, eB=20, hF=56, kF=-46, hB=-46, kB=-4, w=0),
    "spin_cut":P(lean=10, sF=100, eF=0, sB=100, eB=0, hF=30, kF=-20, hB=-30, kB=-10, w=0),
    # unarmed
    "punch_w": P(lean=6, sF=10, eF=130, sB=40, eB=100, hF=24, kF=-30, hB=-20, kB=-16, w=150),
    "punch":   P(lean=22, head=-6, sF=92, eF=0, sB=20, eB=120, hF=40, kF=-40, hB=-36, kB=-8, w=150),
    "upper":   P(lean=-10, head=-14, sF=160, eF=30, sB=10, eB=100, hF=20, kF=-30, hB=-30, kB=-20, w=150),
    "kick_w":  P(lean=-6, sF=40, eF=90, sB=30, eB=100, hF=70, kF=-120, hB=-4, kB=-6, w=150),
    "kick":    P(lean=-24, head=6, sF=-30, eF=40, sB=50, eB=60, hF=96, kF=0, hB=-6, kB=-2, w=150),
    "hikick":  P(lean=-40, head=10, sF=-50, eF=30, sB=60, eB=50, hF=136, kF=-4, hB=-8, kB=-2, w=150),
    "sweep":   P(lean=46, sF=120, eF=10, sB=40, eB=40, hF=88, kF=0, hB=90, kB=-150, w=120),
    "dropkick":P(rot=-40, lean=-20, sF=120, eF=20, sB=100, eB=20, hF=96, kF=0, hB=86, kB=-20, w=120),
    # villain / drama
    "summon":  P(lean=-10, head=-16, sF=150, eF=10, sB=150, eB=10, hF=16, kF=-6, hB=-16, kB=-6, w=0),
    "loom":    P(lean=8, head=12, sF=4, eF=4, sB=-4, eB=6, hF=10, kF=-4, hB=-10, kB=-4, w=170),
    "rest_sword": P(lean=4, head=6, sF=20, eF=10, sB=-8, eB=14, hF=12, kF=-6, hB=-10, kB=-4, w=168),
    "shatter": P(lean=-30, head=-30, sF=-60, eF=10, sB=170, eB=10, hF=40, kF=-10, hB=-20, kB=-10, w=200),
    "wallrun": P(rot=-90, lean=10, sF=-40, eF=40, sB=40, eB=60, hF=60, kF=-80, hB=-30, kB=-30, w=150),
    "dive":    P(rot=40, lean=20, sF=170, eF=0, sB=160, eB=0, hF=-10, kF=-20, hB=-20, kB=-30, w=0),
    "plunge":  P(lean=30, sF=150, eF=-10, sB=150, eB=-10, hF=60, kF=-100, hB=20, kB=-110, w=200),
    "lift":    P(lean=10, head=-20, sF=120, eF=10, sB=110, eB=10, hF=10, kF=-4, hB=-12, kB=-4, w=170),
    "triumph": P(lean=-6, head=-14, sF=170, eF=4, sB=-10, eB=10, hF=10, kF=-4, hB=-12, kB=-4, w=10),
    # v2: daily life
    "sit":     P(lean=4, head=6, sF=40, eF=90, sB=30, eB=96, hF=86, kF=-150, hB=78, kB=-146, w=170),
    "eat":     P(lean=10, head=16, sF=60, eF=120, sB=44, eB=100, hF=86, kF=-150, hB=78, kB=-146, w=170),
    "laugh":   P(lean=-14, head=-26, sF=20, eF=110, sB=10, eB=120, hF=86, kF=-150, hB=78, kB=-146, w=170),
    "give":    P(lean=14, head=10, sF=80, eF=10, sB=10, eB=30, hF=10, kF=-6, hB=-10, kB=-4, w=170),
    "receive": P(lean=6, head=6, sF=70, eF=40, sB=60, eB=50, hF=8, kF=-6, hB=-8, kB=-4, w=170),
    "hold_up": P(lean=-4, head=-20, sF=160, eF=10, sB=150, eB=20, hF=8, kF=-4, hB=-10, kB=-4, w=170),
    "point":   P(lean=-6, head=-30, sF=140, eF=0, sB=-10, eB=20, hF=6, kF=-4, hB=-8, kB=-2, w=170),
    "cower":   P(lean=40, head=30, sF=130, eF=110, sB=140, eB=100, hF=70, kF=-120, hB=30, kB=-110, w=170),
    "carry":   P(lean=10, head=-4, sF=60, eF=80, sB=50, eB=90, hF=20, kF=-20, hB=-20, kB=-10, w=170),
    "fall_back": P(rot=-70, lean=0, head=-10, sF=160, eF=10, sB=140, eB=20, hF=70, kF=-20, hB=40, kB=-30, w=150),
    "sheathe": P(lean=4, head=4, sF=-20, eF=100, sB=-10, eB=20, hF=8, kF=-4, hB=-8, kB=-4, w=200),
    "draw":    P(lean=14, head=-8, sF=110, eF=4, sB=-30, eB=30, hF=36, kF=-46, hB=-30, kB=-12, w=8),
    # v2: two-fighter moves
    "lock":    P(lean=30, head=-4, sF=80, eF=60, sB=70, eB=70, hF=52, kF=-40, hB=-52, kB=-8, w=78),
    "parry":   P(lean=-10, head=-10, sF=120, eF=40, sB=-20, eB=40, hF=14, kF=-20, hB=-34, kB=-20, w=40),
    "grab":    P(lean=24, head=-4, sF=86, eF=4, sB=60, eB=60, hF=40, kF=-40, hB=-36, kB=-8, w=170),
    "throw":   P(lean=-30, head=-20, sF=200, eF=20, sB=170, eB=30, hF=20, kF=-30, hB=-40, kB=-10, w=170),
    "held":    P(lean=-20, head=-30, sF=150, eF=40, sB=120, eB=60, hF=30, kF=-60, hB=-10, kB=-40, w=200),
    "slam":    P(lean=50, head=20, sF=40, eF=0, sB=40, eB=10, hF=60, kF=-90, hB=-30, kB=-40, w=40),
    "spin_back": P(lean=10, head=20, sF=-60, eF=40, sB=40, eB=60, hF=20, kF=-40, hB=-20, kB=-30, w=150),
    "push":    P(lean=22, head=-4, sF=90, eF=0, sB=86, eB=4, hF=46, kF=-40, hB=-50, kB=-6, w=-4),
    "charge":  P(lean=26, head=24, sF=-30, eF=60, sB=-40, eB=60, hF=52, kF=-90, hB=-30, kB=-50, w=170),
    "power":   P(lean=-18, head=-34, sF=120, eF=20, sB=120, eB=20, hF=30, kF=-20, hB=-30, kB=-14, w=150),
    "catch":   P(lean=-6, head=-24, sF=170, eF=10, sB=-10, eB=30, hF=14, kF=-10, hB=-14, kB=-8, w=0),
    "toss":    P(lean=-10, head=-20, sF=160, eF=-10, sB=-20, eB=20, hF=20, kF=-20, hB=-20, kB=-10, w=60),
    "crescent":P(rot=0, lean=20, head=-10, sF=180, eF=10, sB=150, eB=20, hF=100, kF=-140, hB=70, kB=-120, w=30),
    "teach":   P(lean=6, head=0, sF=100, eF=10, sB=-30, eB=40, hF=40, kF=-30, hB=-30, kB=-10, w=10),
    "blink":   P(lean=40, sF=-80, eF=10, sB=-70, eB=10, hF=40, kF=-80, hB=-40, kB=-40, w=180),
}

def pose(name_or_dict, **over):
    base = dict(POSES[name_or_dict]) if isinstance(name_or_dict, str) else dict(name_or_dict)
    base.update({k: float(v) for k, v in over.items()})
    return base

def lerp_pose(a, b, u):
    return {k: a[k] + (b[k] - a[k]) * u for k in KEYS}

# ---------------------------------------------------------------- cycles
def cycle_pose(kind, ph, armed=True):
    """ph in [0,1) is one stride (two steps)."""
    s, c = math.sin(2 * math.pi * ph), math.cos(2 * math.pi * ph)
    if kind == "heavy":      # a big charge: legs drive, arms and blade held steady (no sweeping blade)
        return P(lean=30, head=-8, hF=10 + 44 * s, hB=10 - 44 * s, kF=-18 - 80 * max(0.0, c), kB=-18 - 80 * max(0.0, -c),
                 sF=-40, eF=40, sB=-30, eB=50, w=150)
    if kind in ("run", "ninja", "wallrun"):
        p = P(lean=24, head=-6, hF=12 + 52 * s, hB=12 - 52 * s,
              kF=-18 - 95 * max(0.0, c), kB=-18 - 95 * max(0.0, -c))
        if kind == "ninja" or kind == "wallrun":
            p.update(lean=38, sF=-70 + 6 * s, eF=20, sB=-64 - 6 * s, eB=24, w=175)
        else:
            p.update(sF=10 - 58 * s, eF=86, sB=10 + 58 * s, eB=86, w=40 if armed else 150)
        if kind == "wallrun":
            p["rot"] = -90.0
        return p
    if kind == "walk":
        return P(lean=4, head=2, hF=4 + 22 * s, hB=4 - 22 * s, kF=-6 - 30 * max(0.0, c), kB=-6 - 30 * max(0.0, -c),
                 sF=6 - 16 * s, eF=12, sB=6 + 16 * s, eB=12, w=165)
    if kind == "idle":
        b = 0.5 + 0.5 * s
        p = dict(POSES["guard"]); p["lean"] += 3 * b; p["sF"] += 3 * b; p["eF"] -= 4 * b
        p["hF"] += 3 * b; p["kF"] -= 6 * b; p["hB"] -= 2 * b; p["kB"] -= 5 * b
        return p
    raise KeyError(kind)

# ---------------------------------------------------------------- forward kinematics
def _down(a):
    r = math.radians(a); return (math.sin(r), -math.cos(r))

def fk(p, scale=1.0):
    """Joints in local coords (hip at origin, facing +x), before ground lock."""
    L = scale
    lean = p["lean"]
    tr = math.radians(lean)
    td = (math.sin(tr), math.cos(tr))
    hip = (0.0, 0.0)
    neck = (td[0] * TORSO * L, td[1] * TORSO * L)
    hr = math.radians(lean + p["head"])
    hd = (math.sin(hr), math.cos(hr))
    head = (neck[0] + hd[0] * (NECK + HEAD_R) * L, neck[1] + hd[1] * (NECK + HEAD_R) * L)
    sh = (td[0] * TORSO * 0.9 * L, td[1] * TORSO * 0.9 * L)
    J = {"hip": hip, "neck": neck, "head": head, "sh": sh}
    for side in "FB":
        a1 = p["s" + side] + lean; a2 = a1 + p["e" + side]
        d1, d2 = _down(a1), _down(a2)
        el = (sh[0] + d1[0] * UARM * L, sh[1] + d1[1] * UARM * L)
        ha = (el[0] + d2[0] * FARM * L, el[1] + d2[1] * FARM * L)
        J["el" + side], J["ha" + side] = el, ha
        if side == "F":
            J["fa_ang"] = a2
        else:
            J["fb_ang"] = a2
        h1 = p["h" + side]; h2 = h1 + p["k" + side]
        d1, d2 = _down(h1), _down(h2)
        kn = (d1[0] * THIGH * L, d1[1] * THIGH * L)
        ft = (kn[0] + d2[0] * SHIN * L, kn[1] + d2[1] * SHIN * L)
        J["kn" + side], J["ft" + side] = kn, ft
    J["w_ang"] = J["fa_ang"] + p["w"]
    J["wb_ang"] = J["fb_ang"] + p["w"]
    rot = p["rot"]
    if rot:
        # spin around the body centre (between hip and chest)
        cx, cy = td[0] * TORSO * 0.35 * L, td[1] * TORSO * 0.35 * L
        r = math.radians(-rot); cr, sr = math.cos(r), math.sin(r)
        for k, v in list(J.items()):
            if isinstance(v, tuple):
                x, y = v[0] - cx, v[1] - cy
                J[k] = (cx + x * cr - y * sr, cy + x * sr + y * cr)
        J["w_ang"] = J["w_ang"] + rot
        J["wb_ang"] = J["wb_ang"] + rot
    return J

def lowest(J, scale=1.0):
    ys = [v[1] for k, v in J.items() if isinstance(v, tuple) and k != "head"]
    ys.append(J["head"][1] - HEAD_R * scale)
    return min(ys)

# ---------------------------------------------------------------- easing
def ease(name, u):
    u = min(1.0, max(0.0, u))
    if name == "linear": return u
    if name == "step": return 0.0 if u < 1.0 else 1.0
    if name == "in": return u * u * u
    if name == "out": return 1 - (1 - u) ** 3
    if name == "snap": return 1 - (1 - u) ** 5          # whip into the pose then settle
    if name == "back": s = 1.7; v = u - 1; return v * v * ((s + 1) * v + s) + 1
    if name == "hold": return 0.0 if u < 0.85 else (u - 0.85) / 0.15
    return u * u * (3 - 2 * u)                           # smooth (default)

# ---------------------------------------------------------------- track
class Track:
    """Keyframes: t (s), x, air (height of lowest point, or hip y when lock=0),
    pose dict, facing (+1/-1), ease, xease, arc (jump height), cycle (kind, stride_s)."""
    def __init__(self):
        self.keys = []
        self._sorted = True

    def add(self, t, **k):
        self.keys.append(dict(t=float(t), **k)); self._sorted = False

    def finalize(self):
        self.keys.sort(key=lambda k: k["t"])
        prev = None
        for k in self.keys:      # fill missing fields from previous key
            if prev:
                for f in ("x", "air", "pose", "facing", "lock", "armed"):
                    if k.get(f) is None: k[f] = prev[f]
            else:
                k.setdefault("x", 0.0); k.setdefault("air", 0.0); k.setdefault("facing", 1)
                k.setdefault("lock", 1.0); k.setdefault("armed", True)
                if k.get("pose") is None: k["pose"] = POSES["guard"]
                if k.get("air") is None: k["air"] = 0.0
                if k.get("lock") is None: k["lock"] = 1.0
                if k.get("x") is None: k["x"] = 0.0
                if k.get("facing") is None: k["facing"] = 1
                if k.get("armed") is None: k["armed"] = True
            prev = k
        # keep whole-body spin continuous: a plain pose after a flip should not unspin.
        prev_rot = None
        for k in self.keys:
            r = k["pose"]["rot"]
            sp = k.get("spin")
            if prev_rot is not None and isinstance(sp, float):     # relative flip from jump()
                base = k["pose"]["rot"] - sp
                n = round((prev_rot - base) / 360.0)
                k["pose"] = dict(k["pose"]); k["pose"]["rot"] = base + 360.0 * n + sp
            elif prev_rot is not None and not sp:
                n = round((prev_rot - r) / 360.0)
                if n:
                    k["pose"] = dict(k["pose"]); k["pose"]["rot"] = r + 360.0 * n
            prev_rot = k["pose"]["rot"]
        self._sorted = True
        self._ts = [k["t"] for k in self.keys]

    def sample(self, t):
        ks = self.keys
        if t <= ks[0]["t"]: a = b = ks[0]; u = 0.0
        elif t >= ks[-1]["t"]: a = b = ks[-1]; u = 0.0
        else:
            import bisect
            i = bisect.bisect_right(self._ts, t) - 1
            a, b = ks[i], ks[i + 1]
            u = (t - a["t"]) / max(1e-9, b["t"] - a["t"])
        e = ease(b.get("ease") or "smooth", u) if a is not b else 0.0
        ex = ease(b.get("xease") or b.get("ease") or "smooth", u) if a is not b else 0.0
        cyc = b.get("cycle") if a is not b else None
        if cyc:
            kind, stride = cyc[0], cyc[1]
            ph = ((t - a["t"]) / stride + (cyc[2] if len(cyc) > 2 else 0.0)) % 1.0
            cp = cycle_pose(kind, ph, a.get("armed", True))
            span = b["t"] - a["t"]; edge = min(0.09, span * 0.3)
            wa = min(1.0, (t - a["t"]) / edge) if edge > 0 else 1.0
            wb = min(1.0, (b["t"] - t) / edge) if edge > 0 else 1.0
            w = min(wa, wb)
            base = lerp_pose(a["pose"], b["pose"], u)
            p = lerp_pose(base, cp, w)
        else:
            p = lerp_pose(a["pose"], b["pose"], e)
        x = a["x"] + (b["x"] - a["x"]) * ex
        air = a["air"] + (b["air"] - a["air"]) * ex + 4 * b.get("arc", 0.0) * ex * (1 - ex)
        lock = a["lock"] + (b["lock"] - a["lock"]) * e
        facing = a["facing"] if u < 1.0 or a is b else b["facing"]
        if b.get("flipmid") and u >= 0.5: facing = b["facing"]
        return p, x, air, lock, facing, a.get("armed", True)
