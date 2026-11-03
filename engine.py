"""engine.py - story model + renderer for stick-figure fight videos.

A story file builds a Story: actors with keyframe tracks (in beats), shots
(cuts, environment, camera, palette) and FX events. Everything is a pure
function of time, so any frame can be rendered on its own (parallel workers).
"""
import math, random, json, bisect
import numpy as np
import skia
from rig import Track, fk, lowest, POSES, pose as mkpose, HEAD_R
import hyper
import ambience

RED = (206, 22, 44)
PALETTES = {
    "paper": dict(bg0=(240, 236, 229), bg1=(214, 207, 200), ink=(14, 12, 14), far=(224, 218, 211), mid=(203, 196, 190),
                  near=(84, 78, 80), ground=(194, 186, 180), minion=(92, 88, 92), win=(214, 208, 202), civ=(120, 112, 112),
                  house=(150, 142, 140), lamp=(232, 120, 90)),
    "night": dict(bg0=(8, 8, 11), bg1=(30, 22, 26), ink=(240, 236, 230), far=(18, 15, 18), mid=(30, 25, 28),
                  near=(58, 52, 56), ground=(14, 12, 14), minion=(150, 146, 150), win=(36, 30, 34), vil=(150, 16, 34), civ=(150, 140, 140), house=(40, 34, 38), lamp=(230, 90, 60)),
    "blood": dict(bg0=(120, 8, 20), bg1=(206, 22, 44), ink=(10, 8, 10), far=(150, 14, 30), mid=(110, 10, 24),
                  near=(40, 6, 12), ground=(70, 6, 16), minion=(60, 10, 16), win=(170, 20, 36), civ=(60, 10, 16),
                  house=(90, 8, 20), lamp=(255, 200, 190)),
    "dawn": dict(bg0=(250, 246, 240), bg1=(236, 214, 206), ink=(20, 16, 18), far=(222, 206, 200), mid=(196, 182, 178),
                 near=(90, 80, 82), ground=(214, 200, 194), minion=(98, 94, 98), win=(240, 230, 224), civ=(120, 110, 110),
                 house=(170, 156, 152), lamp=(232, 120, 90)),
    "dusk": dict(bg0=(236, 214, 200), bg1=(196, 120, 110), ink=(18, 14, 16), far=(214, 180, 170), mid=(184, 140, 132),
                 near=(80, 60, 62), ground=(150, 112, 106), minion=(92, 80, 84), win=(220, 190, 170), civ=(96, 76, 78),
                 house=(120, 88, 86), lamp=(255, 214, 150)),
}

# Title fonts. The first file that exists is used; set STICKFIGHT_FONT_TITLE / STICKFIGHT_FONT_SERIF
# to a .ttf/.otf path to choose your own. Falls back to skia's default typeface.
FONT_TITLE = ["C:/Windows/Fonts/impact.ttf", "/Library/Fonts/Impact.ttf", "/System/Library/Fonts/Supplemental/Impact.ttf",
              "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
FONT_SERIF = ["C:/Windows/Fonts/palab.ttf", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]


def _load_font(env, candidates):
    import os
    for path in [os.environ.get(env)] + candidates:
        if path and os.path.exists(path):
            try:
                tf = skia.Typeface.MakeFromFile(path)
                if tf is not None:
                    return tf
            except Exception:
                pass
    return skia.Typeface.MakeDefault()


def C(rgb, a=255):
    return skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(max(0, min(255, a))))

def mix(a, b, u):
    return tuple(a[i] + (b[i] - a[i]) * u for i in range(3))

def hrand(*xs):
    h = 2166136261
    for x in xs:
        for ch in str(x):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h

# =============================================================== story model
class Actor:
    def __init__(self, story, name, kind="hero", scale=1.0, weapon=None, scarf=None, z=0, look=None):
        self.story, self.name, self.kind, self.scale, self.z = story, name, kind, scale, z
        self.look = look                      # 'thief' (hood), 'rival' (mask), 'warden' (helmet), 'guard' (spike helm)
        self.carry = []                       # (t0, t1) windows when this actor carries the glowing relic
        self.track = Track()
        self.spawn, self.die = -1e9, 1e9
        self.weapons = [(-1e9, weapon)]       # (t, dict(len, kind, color)) timeline
        self.scarves = [(-1e9, scarf)]        # (t, 'ink'|'red'|None)
        self.flashes = []                     # times the body flashes on a hit
        self.aura = []                        # (t0, t1) red aura
        self.eyes = []                        # (t0, t1) glowing red eyes
        self.power = []                       # (t0, t1, level, colour) anime-style flame aura + hair
        self.scale_keys = []                  # (t, scale) for transformations

    # --- keyframing in beats
    def key(self, b, pose=None, x=None, air=None, facing=None, ease="smooth", xease=None, arc=0.0,
            lock=None, cycle=None, armed=None, flipmid=False, spin=False, **over):
        p = None
        if pose is not None:
            p = mkpose(pose, **over) if isinstance(pose, (str, dict)) else pose
        self.track.add(self.story.T(b), x=x, air=air, pose=p, facing=facing, ease=ease, xease=xease, arc=arc,
                       lock=lock, cycle=cycle, armed=armed, flipmid=flipmid, spin=spin or ("rot" in over))
        return self

    def at(self, sec, **kw):   # key at absolute seconds
        b = self.story.B(sec); return self.key(b, **kw)

    def run(self, b0, b1, x1, kind="run", pose_end="guard", steps_per_beat=1.0, ease="linear", **kw):
        stride = 2 * self.story.beat / steps_per_beat
        self.key(b1, pose=pose_end, x=x1, ease="smooth", xease=ease, cycle=(kind, stride), **kw)
        return self

    def jump(self, b1, x1, h, pose_end="land", air_end=0.0, flip=0.0, mid_pose="tuck", **kw):
        """arc from the previous key to b1. flip = degrees of forward spin."""
        p = mkpose(pose_end, **{k: v for k, v in kw.items() if k in POSES["guard"]})
        if flip:
            p["rot"] = p.get("rot", 0.0) + flip
        kk = {k: v for k, v in kw.items() if k not in POSES["guard"]}
        self.key(b1, pose=p, x=x1, air=air_end, arc=h, ease="smooth", xease="linear", spin=float(flip) if flip else False, **kk)
        return self

    def strike(self, b, wind, cut, lead=0.45, x=None, step=0.0, facing=None, hold=None, **over):
        """windup at b-lead (beats), whip into `cut` at exactly b."""
        xs = None
        if x is not None: xs = x
        self.key(b - lead, pose=wind, ease="out", facing=facing)
        self.key(b, pose=cut, ease="snap", x=xs, **over)
        if hold:
            self.key(b + hold, pose=cut, ease="smooth")
        return self

    def weapon(self, b, w):
        self.weapons.append((self.story.T(b), w)); self.weapons.sort(key=lambda a: a[0]); return self

    def scarf(self, b, s):
        self.scarves.append((self.story.T(b), s)); self.scarves.sort(key=lambda a: a[0]); return self

    def flash(self, b):
        self.flashes.append(self.story.T(b)); return self

    def carries(self, b0, b1):
        self.carry.append((self.story.T(b0), self.story.T(b1))); return self

    def grow(self, b, scale):
        self.scale_keys.append((self.story.T(b), float(scale))); self.scale_keys.sort(); return self

    def powerup(self, b0, b1, level=1.0, color=(206, 22, 44)):
        self.power.append((self.story.T(b0), self.story.T(b1), level, color)); return self

    def scale_at(self, t):
        ks = self.scale_keys
        if not ks or t <= ks[0][0]: return self.scale if not ks or t < ks[0][0] else ks[0][1]
        for (t0, s0), (t1, s1) in zip(ks, ks[1:]):
            if t0 <= t <= t1:
                u = (t - t0) / max(1e-6, t1 - t0); u = u * u * (3 - 2 * u); return s0 + (s1 - s0) * u
        return ks[-1][1]

    def power_at(self, t):
        best = None
        for (t0, t1, lv, col) in self.power:
            if t0 <= t <= t1:
                fade = min(1.0, (t - t0) / 0.25, (t1 - t) / 0.3)
                if best is None or lv * fade > best[0]: best = (lv * fade, col)
        return best

    def _at(self, lst, t):
        cur = lst[0][1]
        for tt, v in lst:
            if tt <= t: cur = v
        return cur


class Story:
    def __init__(self, beatmap, fps=30, W=1920, H=1080, seed=7):
        self.bm = json.load(open(beatmap)) if isinstance(beatmap, str) else beatmap
        self.beats = self.bm["beats"]; self.beat = self.bm["beat_period"]; self.b0 = self.beats[0]
        self.duration = self.bm["duration"]
        self.fps, self.W, self.H = fps, W, H
        self.actors, self.events, self.shots, self.envs = {}, [], [], {}
        self.rng = random.Random(seed)
        self.title_font = None
        self.warps = []      # slow-motion ramps and hit-stops (action time vs song time)
        self.cues = []       # sound cues (song time, kind, gain dB)
        self.ambs = []       # ambient beds (t0, t1, kind, gain dB)
        self._Agrid = None
        self.hitstop_scale = 1.0   # multiplies every hit-stop (0 = none, 2 = twice as long): a game-feel knob

    # beats <-> seconds on the fixed grid
    def T(self, b): return self.b0 + b * self.beat
    def B(self, t): return (t - self.b0) / self.beat

    def actor(self, name, **kw):
        a = Actor(self, name, **kw); self.actors[name] = a; return a

    def env(self, name, **kw):
        e = Env(name, **kw); self.envs[name] = e; return e

    def shot(self, b0, b1, env, cam, palette="paper", tags=(), **kw):
        self.shots.append(dict(t0=self.T(b0), t1=self.T(b1), b0=b0, b1=b1, env=env, cam=cam, palette=palette,
                               tags=set(tags), **kw))

    def ev(self, kind, b, **p):
        t = self.T(b) if b is not None else p.pop("t")
        e = dict(kind=kind, t=t, seed=self.rng.randrange(1 << 30), **p)
        if p.get("dur") is not None: e["t1"] = t + p["dur"] * self.beat
        self.events.append(e); return e

    # ---- time warp: slow-mo ramps keep the hit itself on the beat
    def slowmo(self, b, w=1.0, r=0.2):
        """slow-motion ramp centred on beat b, half-width w beats, slowest rate r."""
        self.warps.append(dict(kind="ramp", th=self.T(b), w=w * self.beat, r=r)); return self

    def hitstop(self, b, h=0.06, c=0.12):
        h = h * self.hitstop_scale
        if h <= 0: return self
        self.warps.append(dict(kind="stop", th=self.T(b), h=h, c=c)); return self

    def sfx(self, b, kind, gain=0.0, t=None):
        self.cues.append((self.T(b) if t is None else t, kind, gain)); return self

    def amb(self, b0, b1, kind, gain=0.0):
        """an ambient bed (looped recording) from beat b0 to b1, faded in and out"""
        self.ambs.append((self.T(b0), self.T(b1), kind, gain)); return self

    def afterimages(self, name, b0, b1, every=0.25, life=0.45, color="red"):
        b = b0
        while b <= b1 + 1e-6:
            self.ev("ghost", b, actor=name, life=life, color=color); b += every

    def _build_warp(self):
        dt = 0.001
        n = int((self.duration + 2) / dt) + 1
        tg = np.arange(n) * dt
        off = np.zeros(n)
        ramps = [w for w in self.warps if w["kind"] == "ramp"]
        for w in self.warps:
            if w["kind"] == "ramp":
                i0 = int(max(0, (w["th"] - w["w"]) / dt)); i1 = min(n, int((w["th"] + w["w"]) / dt) + 1)
                tt = tg[i0:i1]; u = (tt - w["th"]) / w["w"]; r = w["r"]
                off[i0:i1] += w["th"] + w["w"] * (r * u + (1 - r) * u ** 3) - tt
            else:
                if any(abs(w["th"] - q["th"]) < q["w"] + 0.15 for q in ramps): continue
                h, cc = w["h"], w["c"]
                i0 = int(max(0, w["th"] / dt)); i1 = min(n, int((w["th"] + h + cc) / dt) + 1)
                tt = tg[i0:i1]; d = tt - w["th"]
                off[i0:i1] += np.where(d < h, -d, -h * (1 - (d - h) / cc))
        A = np.maximum.accumulate(tg + off)            # never run time backwards
        self._tg, self._Agrid = tg, A

    def A(self, t):
        """action time for song time t"""
        if self._Agrid is None or not self.warps: return t
        return float(np.interp(t, self._tg, self._Agrid))

    def rate(self, t):
        return (self.A(t + 0.01) - self.A(t - 0.01)) / 0.02

    def song_time(self, ta):
        """first song time at which the action reaches ta (for placing sounds)"""
        if self._Agrid is None or not self.warps: return ta
        i = int(np.searchsorted(self._Agrid, ta - 1e-6))
        return float(self._tg[min(i, len(self._tg) - 1)])

    # ---- compound FX helpers
    def hit_fx(self, b, pos, power=1.0, color="red", sparks=True, ink=True, stop=True, snd="hit"):
        if stop: self.hitstop(b, h=min(0.11, 0.045 * power + 0.02), c=0.1)
        if snd: self.sfx(b, snd, gain=min(3.0, (power - 1) * 4))
        self.ev("flash", b, pos=pos, size=70 * power, color=color)
        if sparks: self.ev("spark", b, pos=pos, n=int(10 + 10 * power), speed=700 * power, color="white" if color == "white" else "ink")
        if ink: self.ev("ink", b, pos=pos, n=int(8 + 10 * power), speed=420 * power)
        self.ev("shake", b, amp=10 * power, decay=9)
        self.ev("zoom", b, amt=0.05 * power, decay=10)
        if power >= 1.4: self.ev("impact", b, frames=2)

    def clash_fx(self, b, pos, power=1.0, stop=True):
        if stop: self.hitstop(b, h=min(0.1, 0.04 * power + 0.02), c=0.1)
        self.sfx(b, "clash" if power < 1.7 else "clash_big", gain=min(3.0, (power - 1) * 3))
        self.ev("flash", b, pos=pos, size=60 * power, color="white")
        self.ev("spark", b, pos=pos, n=int(14 + 10 * power), speed=800 * power, color="white")
        self.ev("shake", b, amp=7 * power, decay=11)
        if power >= 1.5:
            self.ev("impact", b, frames=1); self.ev("shock", b, pos=pos, size=180 * power)

    def finalize(self):
        for a in self.actors.values():
            a.track.finalize()
        self.shots.sort(key=lambda s: s["t0"])
        self.events.sort(key=lambda e: e["t"])
        for e in self.events:
            _prep_event(e)
        self._sh_t = [s["t0"] for s in self.shots]
        for a_, b_ in zip(self.shots, self.shots[1:]): a_["_next"] = b_
        self.warps.sort(key=lambda w: w["th"])
        self._build_warp()
        self.cues.sort()

    def shot_at(self, t):
        i = max(0, bisect.bisect_right(self._sh_t, t) - 1)
        return self.shots[i]


class Env:
    def __init__(self, name, seed=1, sky="sun", towers=(), x0=-2500, x1=6000, far=True, mid=True, rubble=True,
                 ground=True, fg=False, eye=None, crack=None, sun=(0.72, 0.30, 0.17), embers=False, rain=False,
                 wall=None, houses=(), stars=False, skyline=1.0, ash=False, rays=0.0, mist=0.0, heat=False, flags=False,
                 crowd=False, hills=False, grade=None, gap=None):
        self.name, self.seed, self.sky = name, seed, sky
        self.towers = list(towers)   # shared dicts so cuts apply in every env that uses them
        self.x0, self.x1 = x0, x1
        self.ground, self.fg, self.eye, self.crack, self.sun = ground, fg, eye, crack, sun
        self.embers, self.rain, self.wall = embers, rain, wall
        self.houses = list(houses)   # dicts: x, w, h, (wreck=t)
        self.ash, self.rays, self.mist, self.heat, self.flags = ash, rays, mist, heat, flags
        self.crowd, self.hills, self.grade, self.gap = crowd, hills, grade, gap
        self.stars = stars
        r = random.Random(seed)
        self.far = []
        x = x0
        while far and x < x1:
            w = r.uniform(80, 260); h = r.uniform(120, 520) * skyline; self.far.append((x, w, h, r.random())); x += w * r.uniform(0.7, 1.2)
        self.mid = []
        x = x0
        while mid and x < x1:
            w = r.uniform(90, 220); h = r.uniform(180, 700) * skyline
            broken = r.random() < 0.6
            jag = [r.uniform(-0.25, 0.1) for _ in range(5)]
            wins = r.random() < 0.7
            self.mid.append((x, w, h, broken, jag, wins)); x += w + r.uniform(60, 260)
        self.rubble = []
        if rubble:
            for _ in range(int((x1 - x0) / 140)):
                self.rubble.append((r.uniform(x0, x1), r.uniform(8, 34), r.uniform(-40, 40), r.randint(3, 5), r.random()))
        self.fgs = [(r.uniform(x0, x1), r.uniform(30, 90), r.uniform(300, 900)) for _ in range(int((x1 - x0) / 900))] if fg else []

    def tower(self, tid):
        for t in self.towers:
            if t["id"] == tid: return t


# =============================================================== events prep (random params baked once)
def _prep_event(e):
    r = random.Random(e["seed"])
    k = e["kind"]
    if k == "spark":
        n = e.get("n", 14); base = e.get("dir")
        e["parts"] = []
        for _ in range(n):
            a = math.radians(base + r.uniform(-50, 50)) if base is not None else r.uniform(0, 2 * math.pi)
            v = e.get("speed", 700) * r.uniform(0.35, 1.0)
            e["parts"].append((math.cos(a) * v, math.sin(a) * v + 120, r.uniform(0.18, 0.42)))
    elif k == "ink":
        n = e.get("n", 12); base = e.get("dir")
        e["parts"] = []
        for _ in range(n):
            a = math.radians(base + r.uniform(-40, 40)) if base is not None else r.uniform(0, 2 * math.pi)
            v = e.get("speed", 450) * r.uniform(0.3, 1.0)
            e["parts"].append((math.cos(a) * v, math.sin(a) * v + 200, r.uniform(2.5, 7.5), r.uniform(0.5, 0.9)))
    elif k == "debris":
        n = e.get("n", 14); e["parts"] = []
        for _ in range(n):
            a = math.radians(e.get("dir", 90) + r.uniform(-70, 70)); v = e.get("speed", 600) * r.uniform(0.3, 1.0)
            pts = [(math.cos(q) * r.uniform(0.5, 1.0), math.sin(q) * r.uniform(0.5, 1.0))
                   for q in sorted(r.uniform(0, 6.28) for _ in range(r.randint(3, 5)))]
            e["parts"].append((math.cos(a) * v, math.sin(a) * v, r.uniform(-8, 8), e.get("size", 14) * r.uniform(0.4, 1.3), pts,
                               r.uniform(1.1, 1.9)))
    elif k == "dust":
        n = e.get("n", 8); e["parts"] = [(r.uniform(-1, 1), r.uniform(0.2, 1.0), r.uniform(0.6, 1.4)) for _ in range(n)]
    elif k == "crack":
        e["lines"] = []
        for i in range(e.get("n", 7)):
            a = r.uniform(-1, 1); pts = [(0, 0)]; x = 0
            for j in range(4):
                x += a * r.uniform(30, 80) * e.get("size", 1); pts.append((x, r.uniform(-4, 4)))
            e["lines"].append(pts)
    elif k == "speed":
        e["lines"] = [(r.random(), r.uniform(0.2, 1.0), r.random()) for _ in range(60)]


# =============================================================== renderer
class Renderer:
    def __init__(self, story, W=None, H=None, vertical=False):
        self.S = story
        self.W, self.H = W or story.W, H or story.H
        self.vertical = vertical
        self.info = skia.ImageInfo.Make(self.W, self.H, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType)
        # draw straight into a numpy buffer (no readback); this skia build is slow at
        # blending big areas, so full-screen gradients/vignette/fades are done in numpy.
        self.buf = np.zeros((self.H, self.W, 4), np.uint8)
        self.surf = skia.Surface.MakeRasterDirect(self.info, self.buf, self.W * 4)
        self._bgs = {}
        self.post = ambience.Post(self.W, self.H)
        self._sunpos = None
        self.zk = min(self.W, self.H) / 1080.0 * (1.12 if vertical else 1.25)
        self.gfrac = 0.74 if vertical else 0.80
        self._cache = {}
        self.font_tf = _load_font("STICKFIGHT_FONT_TITLE", FONT_TITLE)
        self.font_tf2 = _load_font("STICKFIGHT_FONT_SERIF", FONT_SERIF)

    # ---------------- actor state
    def state(self, a, t):
        key = (a.name, round(t, 5))
        st = self._cache.get(key)
        if st is not None: return st
        p, x, air, lock, facing, armed = a.track.sample(t)
        sc = a.scale_at(t)
        J = fk(p, sc)
        low = lowest(J, sc)
        hip_y = lock * (air - low) + (1 - lock) * air
        f = 1 if facing >= 0 else -1
        W = {k: (x + f * v[0], hip_y + v[1]) for k, v in J.items() if isinstance(v, tuple)}
        wang = J["w_ang"]
        wd = (f * math.sin(math.radians(wang)), -math.cos(math.radians(wang)))
        wpn = a._at(a.weapons, t)
        if wpn and armed:
            hx, hy = W["haF"]; L = wpn.get("len", 90) * sc
            W["tip"] = (hx + wd[0] * L, hy + wd[1] * L); W["pommel"] = (hx - wd[0] * 10 * sc, hy - wd[1] * 10 * sc)
            if wpn.get("dual"):
                wb = J["wb_ang"]; wdb = (f * math.sin(math.radians(wb)), -math.cos(math.radians(wb)))
                bx, by = W["haB"]; W["tipB"] = (bx + wdb[0] * L, by + wdb[1] * L); W["pommelB"] = (bx - wdb[0] * 8 * sc, by - wdb[1] * 8 * sc)
        st = dict(W=W, f=f, wd=wd, wpn=wpn if armed else None, pose=p, x=x, hip_y=hip_y, s=sc)
        if len(self._cache) > 4000: self._cache.clear()
        self._cache[key] = st
        return st

    def alpha_of(self, a, t):
        if t < a.spawn: return 0.0
        if t > a.die: return max(0.0, 1 - (t - a.die) / 0.35)
        return min(1.0, (t - a.spawn) / 0.08) if a.spawn > -1e8 else 1.0

    def resolve(self, pos, t):
        if pos is None: return (0, 0)
        if isinstance(pos[0], str):
            name, part = pos[0], pos[1]
            off = pos[2] if len(pos) > 2 else (0, 0)
            st = self.state(self.S.actors[name], t)
            W = st["W"]
            if part == "tip" and "tip" in W: q = W["tip"]
            elif part == "mid" and "tip" in W: q = ((W["tip"][0] + W["haF"][0]) / 2, (W["tip"][1] + W["haF"][1]) / 2)
            elif part == "chest": q = ((W["neck"][0] * 2 + W["hip"][0]) / 3, (W["neck"][1] * 2 + W["hip"][1]) / 3)
            elif part == "foot": q = W["ftF"]
            elif part == "hand": q = W["haF"]
            elif part == "ground": q = (W["hip"][0], 0.0)
            else: q = W.get(part, W["hip"])
            return (q[0] + off[0] * st["f"], q[1] + off[1])
        return pos

    # ---------------- camera
    def camera(self, shot, t, tr=None, cam=None):
        cam = cam or shot["cam"]; S = self.S
        tr = t if tr is None else tr
        u = min(1.0, max(0.0, (tr - shot["t0"]) / max(1e-6, shot["t1"] - shot["t0"])))
        ue = u * u * (3 - 2 * u) if cam.get("ease", True) else u
        z = cam.get("zoom", 1.4); z1 = cam.get("zoom1", z); z = z + (z1 - z) * ue
        if self.vertical: z *= cam.get("vz", 1.0)
        rot = cam.get("rot", 0.0) + (cam.get("rot1", cam.get("rot", 0.0)) - cam.get("rot", 0.0)) * ue
        if "x" in cam:
            cx = cam["x"] + (cam.get("x1", cam["x"]) - cam["x"]) * ue
            ty = cam.get("y", None)
        else:
            xs, ys = [], []
            lag = cam.get("lag", 0.12)
            for name in cam["follow"]:
                a = S.actors[name]
                if self.alpha_of(a, t) <= 0 and len(cam["follow"]) > 1: continue
                for k in range(4):
                    st = self.state(a, max(self._t0, t - lag * k / 3))
                    if cam.get("part") in st["W"]:
                        q = st["W"][cam["part"]]; xs.append(q[0]); ys.append(q[1])
                    else:
                        xs.append(st["W"]["hip"][0]); ys.append(st["W"]["hip"][1] + 40 * st["s"])
            cx = sum(xs) / max(1, len(xs)); ty = sum(ys) / max(1, len(ys))
            cx += cam.get("dx", 0) + (cam.get("dx1", cam.get("dx", 0)) - cam.get("dx", 0)) * ue
        zz = z * self.zk
        if cam.get("orbit"):
            rot += cam["orbit"] * (ue - 0.5)
        gf = cam.get("gfrac", 0.94 if cam.get("low") else self.gfrac)
        cy_ground = (gf * self.H - self.H / 2) / zz
        # whip-pan: slide hard into this shot / out toward the next one
        wd = 0.0
        if shot.get("whip"):
            k = 1 - (tr - shot["t0"]) / 0.14
            if k > 0: wd -= shot["whip"] * k * k * self.W * 0.7 / zz
        nxt = shot.get("_next")
        if nxt is not None and nxt.get("whip"):
            k = 1 - (shot["t1"] - tr) / 0.1
            if k > 0: wd += nxt["whip"] * k * k * self.W * 0.7 / zz
        cx += wd
        if cam.get("y") is not None:
            cy = cam["y"] + (cam.get("y1", cam["y"]) - cam["y"]) * ue
        else:
            if cam.get("free", bool(cam.get("part"))) and ty is not None:
                cy = ty + cam.get("dy", 0)          # free camera: may dip below the ground line (canyons, close-ups)
            else:
                cy = max(cy_ground, (ty if ty is not None else 0) + cam.get("dy", 0))
        # shake + zoom punches
        sx = sy = sr = 0.0; zp = 0.0
        for e in self._active(t, ("shake", "zoom", "rumble"), 1.2):
            dt = t - e["t"]
            if e["kind"] == "rumble":
                if t < e["t1"]:
                    amp = e.get("amp", 5) * min(1.0, dt / 0.4 + 0.2)
                    sx += amp * math.sin(tr * 71 + 1.3); sy += amp * math.sin(tr * 89 + 0.4); sr += amp * 0.04 * math.sin(tr * 53)
                continue
            if e["kind"] == "shake":
                amp = e.get("amp", 10) * math.exp(-dt * e.get("decay", 8))
                ph = e["seed"] % 1000
                q = tr * 1.0
                sx += amp * (math.sin(q * 83 + ph) * 0.6 + math.sin(q * 131 + ph * 1.7) * 0.4)
                sy += amp * (math.sin(q * 97 + ph * 0.3) * 0.6 + math.sin(q * 151 + ph) * 0.4)
                sr += amp * 0.05 * math.sin(q * 61 + ph)
            else:
                zp += e.get("amt", 0.05) * math.exp(-dt * e.get("decay", 10))
        sc = self.W / 1920 if not self.vertical else self.W / 1080
        bgs = cam.get("orbit", 0) * 14 * (ue - 0.5)
        scr = cam.get("scr", (0.0, 0.0))
        return dict(cx=cx, cy=cy, z=zz * (1 + zp), rot=rot + sr, sx=sx * sc + scr[0] * self.W, sy=sy * sc + scr[1] * self.H, bgs=bgs)

    def _active(self, t, kinds, maxlife):
        S = self.S
        out = []
        for e in S.events:
            if e["t"] > t: break
            if e["kind"] in kinds and (t - e["t"] < maxlife or e.get("t1", -1) > t):
                out.append(e)
        return out

    # ---------------- frame
    def render(self, t, sub=1, shutter=0.5):
        if sub <= 1:
            self._draw(t); self.post_fx(t); return self.buf
        acc = np.zeros((self.H, self.W, 3), np.uint16)
        dt = shutter / self.S.fps
        for i in range(sub):
            tt = t - dt * (i / (sub - 1)) if sub > 1 else t
            # keep sub-samples inside the current shot so cuts stay hard
            sh = self.S.shot_at(t)
            tt = max(tt, sh["t0"] + 1e-4)
            self._draw(tt)
            acc += self.buf[:, :, :3]
        self.buf[:, :, :3] = (acc // sub).astype(np.uint8)
        self.post_fx(t)
        return self.buf

    def post_fx(self, tr):
        """atmosphere, once per output frame: mist, god rays, fire glow, heat shimmer, grade, vignette, grain."""
        S = self.S
        shot = S.shot_at(tr)
        env = S.envs[shot["env"]] if isinstance(shot["env"], str) else shot["env"]
        cam = getattr(self, "_cam", None)
        P = self.post; pal = PALETTES[shot["palette"]]
        ta = S.A(tr)
        P.begin(self.buf)
        if cam is not None and not shot.get("panels"):
            mist = shot.get("mist", env.mist)
            if mist:
                gy = self.H / 2 + cam["cy"] * cam["z"] + cam["sy"]
                mc = {"paper": (246, 242, 236), "dusk": (250, 214, 190), "night": (70, 62, 74), "blood": (236, 120, 120),
                      "dawn": (252, 246, 238)}[shot["palette"]]
                P.mist(self.buf, gy, tr, mc, strength=mist)
            rays = shot.get("rays", env.rays)
            if rays and self._sunpos is not None:
                rc = (255, 210, 200) if shot["palette"] != "night" else (200, 60, 70)
                P.rays(self.buf, self._sunpos[0], self._sunpos[1], tr, strength=rays, color=rc)
            for e in S.events:
                if e["t"] > ta: break
                if e["kind"] == "fire" and ta <= e["t1"]:
                    x, y = e["pos"]
                    px = self.W / 2 + cam["sx"] + (x - cam["cx"]) * cam["z"]; py = self.H / 2 + cam["sy"] - (y + 30 - cam["cy"]) * cam["z"]
                    P.glow(self.buf, px, py, 330 * cam["z"] / self.zk, tr, strength=0.42)
            if shot.get("heat", env.heat):
                P.shimmer(self.buf, tr, amp=2.5 * self.W / 1920)
        P.grade(self.buf, shot.get("grade") or env.grade or ambience.PAL_GRADE.get(shot["palette"]))
        P.vignette_grain(self.buf, int(tr * S.fps), grain=not shot.get("nograin"))
        P.end(self.buf)

    def _draw(self, tr):
        S = self.S
        shot = S.shot_at(tr)
        ta = S.A(tr)
        self._slow = "slowmo" in shot["tags"] or S.rate(tr) < 0.6
        if shot.get("panels"):
            self._draw_panels(shot, ta, tr)
        else:
            self._view(shot, shot["cam"], ta, tr)
        self._post(shot, ta, tr)

    def _draw_panels(self, shot, ta, tr):
        S = self.S
        comp = np.empty_like(self.buf)
        for i, pn in enumerate(shot["panels"]):
            sv = dict(shot); sv.update(pn.get("over", {}))
            if pn.get("replay") is not None:      # flashback: replay an earlier moment of the story
                tt = S.A(S.T(pn["replay"]) + (tr - shot["t0"]) * pn.get("speed", 1.0))
            elif pn.get("freeze") is not None:     # manga freeze panel
                tt = S.A(S.T(pn["freeze"]))
            else:
                tt = ta
            t0o = S.A(S.T(pn["replay"])) if pn.get("replay") is not None else (tt - 1.0 if pn.get("freeze") is not None else None)
            xs_ = [p[0] for p in pn["poly"]]; ys_ = [p[1] for p in pn["poly"]]
            cs = dict(pn["cam"]); cs.setdefault("scr", (sum(xs_) / len(xs_) - 0.5, sum(ys_) / len(ys_) - 0.5))
            self._view(sv, cs, tt, tr, t0o)
            mask = self._mask(shot, i, pn["poly"])
            np.copyto(comp, self.buf, where=mask[:, :, None])
        self.buf[:] = comp
        c = self.surf.getCanvas()
        sc = self.W / 1920 if not self.vertical else self.W / 1080
        for pn in shot["panels"]:
            p = skia.Path(); pts = [(x * self.W, y * self.H) for x, y in pn["poly"]]
            p.moveTo(*pts[0]); [p.lineTo(*q) for q in pts[1:]]; p.close()
            c.drawPath(p, skia.Paint(AntiAlias=True, Color=C((250, 246, 240)), Style=skia.Paint.kStroke_Style, StrokeWidth=22 * sc))
            c.drawPath(p, skia.Paint(AntiAlias=True, Color=C((12, 10, 12)), Style=skia.Paint.kStroke_Style, StrokeWidth=7 * sc))

    def _mask(self, shot, i, poly):
        key = ("mask", shot["t0"], i, self.W, self.H)
        m = self._bgs.get(key)
        if m is None:
            from PIL import Image, ImageDraw
            im = Image.new("L", (self.W, self.H), 0)
            ImageDraw.Draw(im).polygon([(x * self.W, y * self.H) for x, y in poly], fill=255)
            m = np.array(im) > 127; self._bgs[key] = m
        return m

    def _post(self, shot, ta, tr):
        # whip-pan streak blur on the frames around a whip cut
        k = 0.0
        if shot.get("whip"): k = max(k, 1 - (tr - shot["t0"]) / 0.14)
        nxt = shot.get("_next")
        if nxt is not None and nxt.get("whip"): k = max(k, 1 - (shot["t1"] - tr) / 0.1)
        if k > 0: self.hblur(int(10 + 150 * k * (self.W / 1920)))
        for lay in shot.get("layers", ()):
            self.lowres_layer(lay, shot, ta, tr)

    def hblur(self, n):
        """horizontal box blur of the frame (whip pans)."""
        if n < 2: return
        rgb = self.buf[:, :, :3].astype(np.int32)
        cs = np.cumsum(rgb, axis=1)
        pad = np.concatenate([np.zeros((self.H, 1, 3), np.int32), cs], axis=1)
        h = n // 2
        idx = np.arange(self.W)
        lo = np.clip(idx - h, 0, self.W); hi = np.clip(idx + h + 1, 0, self.W)
        out = (pad[:, hi] - pad[:, lo]) // (hi - lo)[None, :, None]
        self.buf[:, :, :3] = out.astype(np.uint8)

    def lowres_layer(self, lay, shot, ta, tr):
        """soft, out-of-focus foreground (over-the-shoulder silhouettes, near rubble): drawn small, scaled up, blended
        only inside its box so it stays cheap."""
        from PIL import Image
        f = 6
        W, H = self.W, self.H
        lw, lh = W // f, H // f
        arr = np.zeros((lh, lw, 4), np.uint8)
        surf = skia.Surface.MakeRasterDirect(skia.ImageInfo.Make(lw, lh, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType), arr, lw * 4)
        c = surf.getCanvas(); c.scale(1 / f, 1 / f)
        pal = PALETTES[shot["palette"]]
        u = min(1.0, max(0.0, (tr - shot["t0"]) / max(1e-6, shot["t1"] - shot["t0"])))
        drift = lay.get("drift", 0.0) * (u - 0.5) * W
        ink = lay.get("color") or (pal["ink"] if shot["palette"] in ("paper", "dawn", "dusk") else (6, 5, 6))
        side = lay.get("side", -1)
        if lay["kind"] == "ots":
            x = (W * 0.08 if side < 0 else W * 0.92) + drift; y = H * lay.get("y", 0.62); R = H * lay.get("r", 0.2)
            p = skia.Paint(AntiAlias=True, Color=C(ink))
            c.drawOval(skia.Rect(x - R * 1.9, y + R * 0.9, x + R * 1.9, y + R * 4.2), p)        # shoulders
            c.drawRect(skia.Rect(x - R * 0.35, y + R * 0.6, x + R * 0.35, y + R * 1.4), p)      # neck
            c.drawCircle(x, y, R, p)
            if lay.get("who") == "villain":
                hp = skia.Paint(AntiAlias=True, Color=C(ink), Style=skia.Paint.kStroke_Style, StrokeWidth=R * 0.28,
                                StrokeCap=skia.Paint.kRound_Cap)
                for sg in (-1, 1):
                    pth = skia.Path(); pth.moveTo(x + sg * R * 0.5, y - R * 0.7)
                    pth.quadTo(x + sg * R * 1.1, y - R * 1.7, x + sg * R * 0.5 - side * R * 0.4, y - R * 2.4); c.drawPath(pth, hp)
            elif lay.get("who") in ("hero", "ally"):
                sp = skia.Paint(AntiAlias=True, Color=C(RED))
                pth = skia.Path(); pth.moveTo(x, y + R * 1.0)
                for k in range(1, 7):
                    pth.lineTo(x - side * k * R * 0.5, y + R * (1.0 + 0.12 * k) + math.sin(tr * 6 + k) * R * 0.1)
                for k in range(6, 0, -1):
                    pth.lineTo(x - side * k * R * 0.5, y + R * (1.35 + 0.12 * k) + math.sin(tr * 6 + k) * R * 0.1)
                pth.close(); c.drawPath(pth, sp)
            box = (0, 0, int(W * 0.42), H) if side < 0 else (int(W * 0.58), 0, W, H)
        else:   # blurred rubble / pillars across the bottom or one side
            r = random.Random(lay.get("seed", 3))
            p = skia.Paint(AntiAlias=True, Color=C(ink))
            for i in range(lay.get("n", 5)):
                x = r.uniform(-0.1, 1.1) * W + drift; hh = r.uniform(0.1, 0.32) * H
                if lay["kind"] == "pillar":
                    c.drawRect(skia.Rect(x, -10, x + r.uniform(0.05, 0.12) * W, H + 10), p)
                else:
                    c.drawOval(skia.Rect(x - W * 0.12, H - hh, x + W * 0.12, H + hh), p)
            box = (0, 0, W, H) if lay["kind"] == "pillar" else (0, int(H * 0.6), W, H)
        im = Image.fromarray(arr, "RGBA").resize((W, H), Image.BILINEAR)
        x0, y0, x1, y1 = box
        big = np.asarray(im)[y0:y1, x0:x1]
        a = big[:, :, 3:4].astype(np.uint16)
        if not a.any(): return
        dst = self.buf[y0:y1, x0:x1, :3].astype(np.uint16)
        # premultiplied source over destination
        self.buf[y0:y1, x0:x1, :3] = ((big[:, :, :3].astype(np.uint16) * 255 + dst * (255 - a)) // 255).astype(np.uint8)

    def _view(self, shot, camspec, t, tr, t0o=None):
        S = self.S
        self._t_now = t
        self._t0 = S.A(shot["t0"]) if t0o is None else t0o
        env = S.envs[shot["env"]] if isinstance(shot["env"], str) else shot["env"]
        pal = dict(PALETTES[shot["palette"]])
        if shot.get("pal_override"): pal.update(shot["pal_override"])
        invert = False
        for e in self._active(t, ("impact",), 0.2):
            if t - e["t"] < e.get("frames", 2) / S.fps: invert = True
        if invert:
            pal = dict(pal); pal["bg0"], pal["bg1"], pal["ink"] = pal["ink"], pal["ink"], pal["bg0"]
            pal.update(far=pal["ink"], mid=pal["ink"], near=pal["ink"], ground=pal["ink"], minion=pal["bg0"])
            pal["inv"] = True
        cam = self.camera(shot, t, tr, camspec)
        self._cam = cam
        c = self.surf.getCanvas()
        c.save()
        np.copyto(self.buf, self.background(pal["bg0"], pal["bg1"], invert))
        if not invert:
            self.draw_sky(c, env, pal, cam, t, shot)
        # world layers
        self.draw_env(c, env, pal, cam, t, shot)
        self.world_begin(c, cam, 1.0)
        self.draw_fx(c, pal, t, back=True)
        acts = [a for a in S.actors.values() if self.alpha_of(a, t) > 0 and ("only" not in shot or a.name in shot["only"])]
        acts.sort(key=lambda a: a.z)
        for a in acts:
            self.draw_actor(c, a, pal, t, shot)
        self.draw_fx(c, pal, t, back=False)
        self.draw_fg(c, env, pal, cam, t)
        c.restore()
        c.save()
        self.draw_screen_fx(c, pal, t, shot, cam)
        c.restore()
        self.overlays(t)
        self._tr = tr

    def world_begin(self, c, cam, p, zmul=1.0):
        c.restore(); c.save()
        c.translate(self.W / 2 + cam["sx"], self.H / 2 + cam["sy"])
        c.rotate(cam["rot"])
        z = cam["z"] * zmul
        c.scale(z, -z)
        bg = cam.get("bgs", 0.0) * (1 - p) * 60 if p < 1 else 0.0     # orbit: background slides against the stage
        c.translate(-cam["cx"] * p + bg, -cam["cy"] * (p if p < 1 else 1))

    # ---------------- sky / env
    def draw_sky(self, c, env, pal, cam, t, shot):
        W, H = self.W, self.H
        sk = env.sky
        self._sunpos = None
        if sk in ("sun", "eye", "moon"):
            sx = env.sun[0] * W - cam["cx"] * cam["z"] * 0.03
            sy = env.sun[1] * H + cam["cy"] * cam["z"] * 0.02
            r = env.sun[2] * min(W, H) * 1.6
            self._sunpos = (sx, sy) if sk in ("sun", "eye") else None
            col = RED if sk != "moon" else mix(pal["ink"], pal["bg0"], 0.2)
            if shot["palette"] == "blood": col = (20, 6, 8)
            c.drawCircle(sx, sy, r * 1.25, skia.Paint(AntiAlias=True, Color=C(mix(pal["bg0"], col, 0.16))))
            c.drawCircle(sx, sy, r, skia.Paint(AntiAlias=True, Color=C(col)))
            if sk == "eye" and env.eye:
                op = env.eye(t) if callable(env.eye) else env.eye
                if op > 0.01:
                    # the sky eye opening in the sun
                    path = skia.Path()
                    ew, eh = r * 1.9, r * 0.75 * op
                    path.moveTo(sx - ew, sy)
                    path.quadTo(sx, sy - eh * 2, sx + ew, sy)
                    path.quadTo(sx, sy + eh * 2, sx - ew, sy)
                    path.close()
                    c.drawPath(path, skia.Paint(AntiAlias=True, Color=C(pal["ink"])))
                    c.drawCircle(sx, sy, r * 0.62 * min(1, op * 1.3), skia.Paint(AntiAlias=True, Color=C(RED)))
                    pr = skia.Path(); pw = r * 0.12 * op
                    pr.addOval(skia.Rect(sx - pw, sy - r * 0.55 * op, sx + pw, sy + r * 0.55 * op))
                    c.drawPath(pr, skia.Paint(AntiAlias=True, Color=C(pal["ink"])))
        if env.crack:
            op = env.crack(t) if callable(env.crack) else env.crack
            if op > 0:
                r = random.Random(env.seed + 99)
                p = skia.Path(); x, y = W * 0.08, H * 0.12; p.moveTo(x, y)
                pts = []
                for i in range(14):
                    x += W * 0.065 * op; y += r.uniform(-40, 50) * op; pts.append((x, y)); p.lineTo(x, y)
                c.drawPath(p, skia.Paint(AntiAlias=True, Color=C(mix(pal["bg0"], RED, 0.25)), Style=skia.Paint.kStroke_Style,
                                         StrokeWidth=34 * op * W / 1920, StrokeJoin=skia.Paint.kRound_Join))
                c.drawPath(p, skia.Paint(AntiAlias=True, Color=C(pal["ink"]), Style=skia.Paint.kStroke_Style, StrokeWidth=15 * op * W / 1920,
                                         StrokeJoin=skia.Paint.kMiter_Join))
                c.drawPath(p, skia.Paint(AntiAlias=True, Color=C(RED), Style=skia.Paint.kStroke_Style, StrokeWidth=7 * op * W / 1920,
                                         StrokeJoin=skia.Paint.kMiter_Join))

    def draw_env(self, c, env, pal, cam, t, shot):
        c.save()
        if env.hills:
            self.world_begin(c, cam, 0.06, 0.45)
            p = skia.Path(); x0 = cam["cx"] * 0.06 - 5000; p.moveTo(x0, -1500)
            for i in range(0, 101):
                x = x0 + i * 100
                p.lineTo(x, 380 + 120 * math.sin(x * 0.0021) + 70 * math.sin(x * 0.0053 + 1) + 30 * math.sin(x * 0.013))
            p.lineTo(x0 + 10000, -1500); p.close()
            c.drawPath(p, skia.Paint(AntiAlias=True, Color=C(mix(pal["far"], pal["bg1"], 0.45))))
        # far layer
        if env.far:
            self.world_begin(c, cam, 0.15, 0.55)
            pnt = skia.Paint(AntiAlias=True, Color=C(pal["far"]))
            zl = cam["z"] * 0.55; lo = cam["cx"] * 0.15 - self.W / zl; hi = cam["cx"] * 0.15 + self.W / zl
            for (x, w, h, q) in env.far:
                if x + w < lo or x > hi: continue
                c.drawRect(skia.Rect(x, -1500, x + w, h * 0.8 + 120), pnt)
        if env.mid:
            self.world_begin(c, cam, 0.45, 0.78)
            pnt = skia.Paint(AntiAlias=True, Color=C(pal["mid"]))
            wp = skia.Paint(AntiAlias=False, Color=C(pal["win"]))
            zl = cam["z"] * 0.78; lo = cam["cx"] * 0.45 - self.W / zl; hi = cam["cx"] * 0.45 + self.W / zl
            for (x, w, h, broken, jag, wins) in env.mid:
                if x + w < lo or x > hi: continue
                path = skia.Path(); path.moveTo(x, -1500); path.lineTo(x, h)
                if broken:
                    for i, j in enumerate(jag):
                        path.lineTo(x + w * (i + 1) / 6, h * (1 + j))
                path.lineTo(x + w, h * (1 + (jag[-1] if broken else 0)))
                path.lineTo(x + w, -1500); path.close()
                c.drawPath(path, pnt)
                if wins and shot["palette"] != "blood":
                    for wy in range(40, int(h * 0.7), 46):
                        for wx in range(14, int(w) - 20, 34):
                            if hrand(x, wx, wy) % 5 == 0: continue
                            c.drawRect(skia.Rect(x + wx, wy, x + wx + 14, wy + 22), wp)
        if env.stars and shot["palette"] in ("night",):
            self.world_begin(c, cam, 0.05, 0.4)
            r = random.Random(env.seed + 5); sp = skia.Paint(AntiAlias=True, Color=C((200, 196, 190)))
            for i in range(90):
                c.drawCircle(cam["cx"] * 0.05 + r.uniform(-2400, 2400), r.uniform(300, 2200), r.uniform(1.5, 3.5), sp)
        if env.crowd and shot["palette"] != "blood":
            zm = 0.42
            c.restore(); c.save()
            c.translate(self.W / 2 + cam["sx"], self.H / 2 + cam["sy"]); c.rotate(cam["rot"])
            c.scale(cam["z"] * zm, -cam["z"] * zm); c.translate(-cam["cx"] * 0.55, -cam["cy"] / zm)
            ambience.crowd(c, env.seed + 3, cam["cx"], t, mix(pal["mid"], pal["ink"], 0.22),
                           cam["cx"] * 0.55 - 2600, cam["cx"] * 0.55 + 2600, n=60)
        self.world_begin(c, cam, 1.0)
        if env.houses:
            self.draw_houses(c, env, pal, cam, t)
        # stage towers (cuttable)
        lo = cam["cx"] - self.W / cam["z"]; hi = cam["cx"] + self.W / cam["z"]
        for tw in env.towers:
            if tw["x"] + tw["w"] + 1500 < lo or tw["x"] - 1500 > hi: continue
            self.draw_tower(c, tw, pal, t)
        if env.wall:
            self.draw_wall(c, env.wall, pal, t)
        # ground
        if env.ground and env.gap:
            g0, g1 = env.gap["x0"], env.gap["x1"]
            gp = skia.Paint(AntiAlias=True, Color=C(pal["ground"]))
            lp = skia.Paint(AntiAlias=True, Color=C(pal["ink"]), StrokeWidth=5, Style=skia.Paint.kStroke_Style)
            dark_ink = sum(pal["ink"]) < sum(pal["bg0"])
            vbase = mix(pal["ground"], pal["ink"], 0.45) if dark_ink else mix(pal["bg1"], (0, 0, 0), 0.4)
            c.drawRect(skia.Rect(g0, -6000, g1, 0), skia.Paint(AntiAlias=True, Color=C(vbase)))
            for k in range(1, 6):     # canyon depth bands, darker as they go down
                c.drawRect(skia.Rect(g0 + 40 * k, -6000, g1 - 40 * k, -300 * k),
                           skia.Paint(AntiAlias=True, Color=C(mix(vbase, (0, 0, 0), 0.12 * k))))
            c.drawRect(skia.Rect(cam["cx"] - 6000, -6000, g0, 0), gp); c.drawRect(skia.Rect(g1, -6000, cam["cx"] + 6000, 0), gp)
            c.drawLine(cam["cx"] - 6000, 0, g0, 0, lp); c.drawLine(g1, 0, cam["cx"] + 6000, 0, lp)
            c.drawLine(g0, 0, g0 - 30, -6000, lp); c.drawLine(g1, 0, g1 + 30, -6000, lp)
            br = env.gap.get("bridge")
            if br is not None:
                self.draw_bridge(c, g0, g1, br, pal, t)
        elif env.ground:
            gp = skia.Paint(AntiAlias=True, Color=C(pal["ground"]))
            c.drawRect(skia.Rect(cam["cx"] - 6000, -3000, cam["cx"] + 6000, 0), gp)
            lp = skia.Paint(AntiAlias=True, Color=C(pal["ink"]), StrokeWidth=5, Style=skia.Paint.kStroke_Style)
            c.drawLine(cam["cx"] - 6000, 0, cam["cx"] + 6000, 0, lp)
            rp = skia.Paint(AntiAlias=True, Color=C(pal["near"]))
            for (x, s, rr, n, q) in env.rubble:
                if abs(x - cam["cx"]) > 2600: continue
                path = skia.Path()
                for i in range(n):
                    a = math.pi * i / (n - 1)
                    px, py = x + math.cos(a) * s * (1 + 0.3 * q), math.sin(a) * s * (0.5 + q * 0.6)
                    (path.moveTo if i == 0 else path.lineTo)(px, py)
                path.close(); c.drawPath(path, rp)
        c.restore()

    def draw_tower(self, c, tw, pal, t):
        x, w, h = tw["x"], tw["w"], tw["h"]
        col = C(pal["near"]); wcol = C(pal["win"] if pal is not None else (200, 200, 200))
        base = [(x, 0), (x, h), (x + w, h), (x + w, 0)]
        cut = tw.get("cut")
        pnt = skia.Paint(AntiAlias=True, Color=col)
        def poly(pts, paint):
            p = skia.Path(); p.moveTo(*pts[0])
            for q in pts[1:]: p.lineTo(*q)
            p.close(); c.drawPath(p, paint)
        def windows(clip_fn=None):
            wp = skia.Paint(Color=wcol)
            for wy in range(30, int(h) - 20, 44):
                for wx in range(12, int(w) - 18, 30):
                    if hrand(x, wx, wy) % 4 == 0: continue
                    if clip_fn and not clip_fn(x + wx + 6, wy + 10): continue
                    c.drawRect(skia.Rect(x + wx, wy, x + wx + 12, wy + 20), wp)
        if not cut or t < cut["t"]:
            poly(base, pnt); windows()
            if tw.get("flag"): ambience.flag(c, x + w * 0.3, h, t, RED, pal["ink"], size=1.6, pole=90)
            return
        # cut line through (x+w/2, cy) at angle a
        cy, a = cut["y"], math.radians(cut["angle"])
        ux, uy = math.cos(a), math.sin(a)
        def side(px, py): return (px - (x + w / 2)) * uy - (py - cy) * ux
        y_l = cy + (x - (x + w / 2)) * math.tan(a); y_r = cy + (w / 2) * math.tan(a)
        lower = [(x, 0), (x, y_l), (x + w, y_r), (x + w, 0)]
        upper = [(x, y_l), (x, h), (x + w, h), (x + w, y_r)]
        c.save()
        poly(lower, pnt)
        c.save()
        p = skia.Path(); p.moveTo(*lower[0]); [p.lineTo(*q) for q in lower[1:]]; p.close(); c.clipPath(p, doAntiAlias=True)
        windows(); c.restore()
        dt = t - cut["t"]
        d = cut.get("dir", 1)
        slide = 40 * min(dt, 0.35) / 0.35 + (dt * dt * 260 if dt > 0.3 else 0)
        fall = max(0.0, dt - 0.25) ** 2 * 900
        ang = d * max(0.0, dt - 0.2) ** 1.6 * 28
        c.translate(d * slide * abs(ux), slide * uy * d - fall)
        c.translate(x + w / 2, y_r); c.rotate(-ang); c.translate(-(x + w / 2), -y_r)
        poly(upper, pnt)
        p = skia.Path(); p.moveTo(*upper[0]); [p.lineTo(*q) for q in upper[1:]]; p.close(); c.clipPath(p, doAntiAlias=True)
        windows()
        c.restore()
        # glowing cut seam for a moment
        if dt < 0.6:
            lp = skia.Paint(AntiAlias=True, Color=C(RED, 255 * (1 - dt / 0.6)), StrokeWidth=6, Style=skia.Paint.kStroke_Style)
            c.drawLine(x - 30, y_l - 30 * math.tan(a), x + w + 30, y_r + 30 * math.tan(a), lp)

    def draw_houses(self, c, env, pal, cam, t):
        lo = cam["cx"] - self.W / cam["z"] - 400; hi = cam["cx"] + self.W / cam["z"] + 400
        body = skia.Paint(AntiAlias=True, Color=C(pal.get("house", pal["mid"])))
        roof = skia.Paint(AntiAlias=True, Color=C(pal["near"]))
        ink = skia.Paint(AntiAlias=True, Color=C(pal["ink"]))
        lamp = skia.Paint(AntiAlias=True, Color=C(pal.get("lamp", RED)))
        line = skia.Paint(AntiAlias=True, Color=C(pal["ink"]), Style=skia.Paint.kStroke_Style, StrokeWidth=2)
        prev = None
        for hs in env.houses:
            x, w, h = hs["x"], hs["w"], hs["h"]
            if x + w < lo or x > hi: prev = hs; continue
            wrecked = hs.get("wreck") is not None and t >= hs["wreck"]
            if not wrecked:
                c.drawRect(skia.Rect(x, 0, x + w, h), body)
                p = skia.Path(); p.moveTo(x - 18, h); p.lineTo(x + w / 2, h + w * 0.42); p.lineTo(x + w + 18, h); p.close()
                c.drawPath(p, roof)
            else:
                p = skia.Path(); p.moveTo(x, 0); p.lineTo(x, h * 0.55); p.lineTo(x + w * 0.3, h * 0.35); p.lineTo(x + w * 0.55, h * 0.62)
                p.lineTo(x + w * 0.8, h * 0.3); p.lineTo(x + w, h * 0.45); p.lineTo(x + w, 0); p.close(); c.drawPath(p, body)
            c.drawRect(skia.Rect(x + w * 0.4, 0, x + w * 0.6, h * 0.48), ink)                       # door
            if not wrecked:
                c.drawRect(skia.Rect(x + w * 0.12, h * 0.55, x + w * 0.3, h * 0.8), lamp)          # lit window
                c.drawRect(skia.Rect(x + w * 0.7, h * 0.55, x + w * 0.88, h * 0.8), lamp)
            if env.flags and not wrecked and int(x) % 3 == 0:
                ambience.flag(c, x + w / 2, h + w * 0.42 - 4, t, RED, pal["ink"], size=1.1)
            if prev is not None and not wrecked and hs.get("lanterns", True):
                x0, y0 = prev["x"] + prev["w"], prev["h"] * 0.92; x1, y1 = x, h * 0.92
                p = skia.Path(); p.moveTo(x0, y0); p.quadTo((x0 + x1) / 2, min(y0, y1) - 40, x1, y1); c.drawPath(p, line)
                for k in range(1, 5):
                    u = k / 5; lx = x0 + (x1 - x0) * u; ly = (1 - u) ** 2 * y0 + 2 * u * (1 - u) * (min(y0, y1) - 40) + u * u * y1
                    c.drawCircle(lx, ly - 9, 8, lamp)
            prev = hs

    def draw_bridge(self, c, g0, g1, br, pal, t):
        """rope bridge across a canyon; br = dict(cut=t or None, at=x). After the cut both halves swing down."""
        cut = br.get("cut"); at = br.get("at", (g0 + g1) / 2)
        ink = pal["ink"]
        rope = skia.Paint(AntiAlias=True, Color=C(ink), StrokeWidth=3, Style=skia.Paint.kStroke_Style)
        plank = skia.Paint(AntiAlias=True, Color=C(mix(pal["near"], ink, 0.3)))
        def half(x0, x1, pivot, sgn):
            ang = 0.0
            if cut is not None and t >= cut:
                dt = t - cut; ang = sgn * min(86.0, 140 * dt * dt + 20 * dt)
            c.save(); c.translate(pivot, 0); c.rotate(ang); c.translate(-pivot, 0)
            n = int(abs(x1 - x0) / 34)
            lo, hi = min(x0, x1), max(x0, x1)
            for i in range(n):
                px = lo + i * 34 + 3
                sag = -10 * math.sin(math.pi * (px - g0) / max(1, g1 - g0)) if cut is None or t < cut else 0
                c.drawRect(skia.Rect(px, -7 + sag, px + 26, 1 + sag), plank)
            c.drawLine(lo, 55, hi, 55 - (10 if cut is None or t < cut else 0), rope)
            c.drawLine(lo, 0, hi, 0, rope)
            c.restore()
        half(g0, at, g0, -1)
        half(at, g1, g1, 1)
        for x in (g0, g1):
            c.drawLine(x, 0, x, 80, skia.Paint(AntiAlias=True, Color=C(ink), StrokeWidth=8, Style=skia.Paint.kStroke_Style))

    def draw_wall(self, c, wall, pal, t):
        x, w, h = wall["x"], wall["w"], wall["h"]
        brk = wall.get("break", 1e9)
        pnt = skia.Paint(AntiAlias=True, Color=C(pal["near"]))
        if t < brk:
            c.drawRect(skia.Rect(x, 0, x + w, h), pnt)
            lp = skia.Paint(AntiAlias=True, Color=C(pal["win"]), StrokeWidth=2, Style=skia.Paint.kStroke_Style)
            for yy in range(30, int(h), 34): c.drawLine(x, yy, x + w, yy, lp)
        else:
            hole = wall.get("hole", (h * 0.3, h * 0.75))
            c.drawRect(skia.Rect(x, 0, x + w, hole[0]), pnt)
            c.drawRect(skia.Rect(x, hole[1], x + w, h), pnt)

    def draw_fg(self, c, env, pal, cam, t):
        if not env.fgs: return
        self.world_begin(c, cam, 1.35, 1.25)
        p = skia.Paint(AntiAlias=True, Color=C(mix(pal["ink"], pal["bg0"], 0.08)))
        for (x, w, h) in env.fgs:
            c.drawRect(skia.Rect(x * 1.35, -400, x * 1.35 + w, h), p)

    # ---------------- actors
    def draw_actor(self, c, a, pal, t, shot):
        alpha = self.alpha_of(a, t)
        st = self.state(a, t)
        ink = pal["ink"]
        if a.kind == "minion": ink = pal["minion"]
        if a.kind in ("civ", "kid"): ink = pal.get("civ", pal["minion"])
        if a.kind == "villain" and pal is not None and pal.get("vil"): ink = pal["vil"]
        fl = any(0 <= t - ft < 0.07 for ft in a.flashes)
        if fl: ink = RED if not pal.get("inv") else pal["bg0"]
        aura = any(t0 <= t < t1 for (t0, t1) in a.aura)
        # motion trail ghosts (fast moves)
        T0 = self._t0
        ct = lambda tt: max(T0, tt)
        prev = self.state(a, ct(t - 1 / 30))
        v = math.hypot(st["W"]["hip"][0] - prev["W"]["hip"][0], st["W"]["hip"][1] - prev["W"]["hip"][1]) * 30
        tipv = 0
        if "tip" in st["W"] and "tip" in prev["W"]:
            tipv = math.hypot(st["W"]["tip"][0] - prev["W"]["tip"][0], st["W"]["tip"][1] - prev["W"]["tip"][1]) * 30
        slow = getattr(self, "_slow", False)
        dark = shot["palette"] in ("night", "blood")
        pw = a.power_at(t)
        if pw and pw[0] > 0.05:
            acol = pw[1] if shot["palette"] != "blood" or a.kind != "hero" else (250, 238, 232)
            hyper.aura(c, st, st["s"], pw[0], t, col=acol if not pal.get("inv") else pal["ink"],
                       core=(255, 251, 245) if shot["palette"] != "paper" or pw[0] > 1.2 else (255, 236, 236), inv=False)
        if v > 500 or slow and v > 260:
            n = (4 if slow else 3) - (1 if dark or a.kind == "villain" else 0) - (2 if dark and a.kind == "villain" else 0)
            for k in range(n, 0, -1):
                gs = self.state(a, ct(t - k * (0.03 if slow else 0.018)))
                gcol = RED if aura and k % 2 and not dark else ink
                self._figure(c, a, gs, gcol, alpha * (0.22 - 0.045 * k) * (1.15 if slow else 1) * (0.7 if dark else 1), pal, ghost=True)
        # weapon smear (crescent)
        if st["wpn"] and tipv > 900 * max(1.0, st["wpn"].get("len", 90) * st["s"] / 100) ** 1.3:
            self._smear(c, a, t, st, pal, alpha)
        # kick smear
        fv = 0
        fv = math.hypot(st["W"]["ftF"][0] - prev["W"]["ftF"][0], st["W"]["ftF"][1] - prev["W"]["ftF"][1]) * 30
        if fv > 1100:
            path = skia.Path()
            for k in range(7):
                q = self.state(a, ct(t - k * 0.012))["W"]["ftF"]
                (path.moveTo if k == 0 else path.lineTo)(*q)
            c.drawPath(path, skia.Paint(AntiAlias=True, Color=C(ink, 90 * alpha), Style=skia.Paint.kStroke_Style,
                                        StrokeWidth=16 * st["s"], StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join))
        if aura:
            self._figure(c, a, st, RED, alpha * 0.35, pal, ghost=True, wide=2.6)
        self._scarf(c, a, t, st, pal, alpha)
        if pw and pw[0] > 0.6 and a.kind in ("hero", "ally", "villain") and a.look not in ("thief", "warden"):
            hyper.hair(c, st, st["s"], st["f"], ink, t, pw[0])
        self._figure(c, a, st, ink, alpha, pal)
        if any(t0 <= t <= t1 for (t0, t1) in a.carry):
            hand = st["W"]["haB"] if a.look != "warden" else st["W"]["neck"]
            hyper.gem(c, hand[0], hand[1] + (0 if a.look != "warden" else -20 * st["s"]), 14 * st["s"], t)

    def _scarf(self, c, a, t, st, pal, alpha):
        sc = a._at(a.scarves, t)
        if not sc: return
        col = RED if sc == "red" else pal["ink"]
        if a.kind == "villain": col = pal.get("vil", pal["ink"])
        n = 9 if a.kind != "villain" else 8
        pts = []
        for k in range(n):
            s = self.state(a, max(self._t0, t - k * 0.028))
            nk = s["W"]["neck"] if a.kind != "villain" else s["W"]["sh"]
            f = s["f"]
            pwr = a.power_at(t)
            wind = 1.0 + (2.6 * pwr[0] if pwr else 0.0)
            wob = math.sin(t * (11 + 14 * (wind > 1)) + k * 0.9) * 3.5 * k / n * wind
            q = (nk[0] - f * k * 8.5 * st["s"], nk[1] - k * (1.6 if a.kind != "villain" else 9) * st["s"] + wob)
            if pts and math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 46 * st["s"]:
                break      # the body moved too far between samples (a blink or a snap dash): end the scarf here
            pts.append(q)
        width = (7 if a.kind != "villain" else 26) * st["s"]
        path = skia.Path()
        left, right = [], []
        for i, (px, py) in enumerate(pts):
            j = min(i + 1, len(pts) - 1); i0 = max(0, i - 1)
            dx, dy = pts[j][0] - pts[i0][0], pts[j][1] - pts[i0][1]; L = math.hypot(dx, dy) or 1
            nx, ny = -dy / L, dx / L; wv = width * (1 - 0.6 * i / n) * (0.6 if a.kind != "villain" else 1)
            left.append((px + nx * wv, py + ny * wv)); right.append((px - nx * wv, py - ny * wv))
        path.moveTo(*left[0])
        for q in left[1:]: path.lineTo(*q)
        for q in reversed(right): path.lineTo(*q)
        path.close()
        c.drawPath(path, skia.Paint(AntiAlias=True, Color=C(col, 255 * alpha)))

    def _smear(self, c, a, t, st, pal, alpha):
        hand, tip = [], []
        for k in range(10 if st["wpn"].get("kind") != "great" else 6):
            s = self.state(a, max(self._t0, t - k * 0.009))
            if "tip" not in s["W"]: break
            hand.append(s["W"]["haF"]); tip.append(s["W"]["tip"])
        if len(tip) < 3: return
        L = math.hypot(tip[0][0] - hand[0][0], tip[0][1] - hand[0][1]) or 1
        if max(math.hypot(tip[i + 1][0] - tip[i][0], tip[i + 1][1] - tip[i][1]) for i in range(len(tip) - 1)) > 0.55 * L:
            return   # the blade jumped too far between samples: an arc would read as noise
        col = RED if a.kind in ("hero", "villain", "ally") else pal["ink"]
        if pal.get("inv"): col = pal["ink"]
        path = skia.Path(); path.moveTo(*tip[0])
        for q in tip[1:]: path.lineTo(*q)
        # inner edge at 55% of the blade for a crescent
        fr = 0.72 if st["wpn"].get("kind") == "great" else 0.45
        inner = [(h[0] + (tp[0] - h[0]) * fr, h[1] + (tp[1] - h[1]) * fr) for h, tp in zip(hand, tip)]
        for q in reversed(inner): path.lineTo(*q)
        path.close()
        big = st["wpn"].get("kind") == "great"
        if big:   # huge blade: a clean double arc of the tip path instead of a filled crescent
            for frac, wd, al in ((1.0, 9, 200), (0.72, 4, 120)):
                pp = skia.Path()
                pts = [(h[0] + (tp[0] - h[0]) * frac, h[1] + (tp[1] - h[1]) * frac) for h, tp in zip(hand, tip)]
                pp.moveTo(*pts[0])
                for q in pts[1:]: pp.lineTo(*q)
                c.drawPath(pp, skia.Paint(AntiAlias=True, Color=C(col, al * alpha), Style=skia.Paint.kStroke_Style,
                                          StrokeWidth=wd * st["s"], StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join))
            return
        c.drawPath(path, skia.Paint(AntiAlias=True, Color=C(col, 150 * alpha)))
        p2 = skia.Path(); p2.moveTo(*tip[0])
        for q in tip[1:4]: p2.lineTo(*q)
        c.drawPath(p2, skia.Paint(AntiAlias=True, Color=C((255, 250, 245) if not pal.get("inv") else pal["ink"], 200 * alpha),
                                  Style=skia.Paint.kStroke_Style, StrokeWidth=3 * st["s"], StrokeCap=skia.Paint.kRound_Cap))

    def _figure(self, c, a, st, ink, alpha, pal, ghost=False, wide=1.0):
        W, f, s = st["W"], st["f"], st["s"]
        base = (8.6 if a.kind != "villain" else 9.6) * s * wide
        if a.kind == "minion": base = 7.0 * s * wide
        paint = skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha), Style=skia.Paint.kStroke_Style, StrokeWidth=base,
                           StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
        far = skia.Paint(paint); far.setColor(C(mix(ink, pal["bg0"], 0.38 if not ghost else 0.0), 255 * alpha))
        def chain(pts, p):
            path = skia.Path(); path.moveTo(*pts[0])
            for q in pts[1:]: path.lineTo(*q)
            c.drawPath(path, p)
        # back limbs first
        chain([W["sh"], W["elB"], W["haB"]], far)
        chain([W["hip"], W["knB"], W["ftB"]], far)
        # weapon behind the near arm
        wpn = st["wpn"]
        if wpn and not ghost:
            self._weapon(c, a, st, ink, alpha, pal)
        chain([W["hip"], W["neck"]], paint)
        chain([W["hip"], W["knF"], W["ftF"]], paint)
        chain([W["sh"], W["elF"], W["haF"]], paint)
        hx, hy = W["head"]; hr = HEAD_R * s * (1.0 if not ghost else wide ** 0.5)
        hp = skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha))
        if a.look == "thief" and not ghost:
            hood = skia.Path()
            hood.moveTo(hx + f * hr * 0.2, hy + hr * 1.25)
            hood.quadTo(hx - f * hr * 0.9, hy + hr * 1.5, hx - f * hr * 1.7, hy + hr * 0.2)
            hood.quadTo(hx - f * hr * 1.5, hy - hr * 0.9, hx - f * hr * 0.2, hy - hr * 1.15)
            hood.close()
            c.drawPath(hood, skia.Paint(AntiAlias=True, Color=C(RED if not pal.get("inv") else ink, 255 * alpha)))
            c.drawCircle(hx, hy, hr * 1.12, skia.Paint(AntiAlias=True, Color=C(RED if not pal.get("inv") else ink, 255 * alpha)))
        c.drawCircle(hx, hy, hr, hp)
        if ghost: return
        bgc = pal["bg0"]
        eyes_on = (a.kind in ("villain", "minion") and a.look != "warden") or any(t0 <= self._t_now <= t1 for (t0, t1) in a.eyes)
        if a.kind == "villain" and a.look is None:
            # horns
            hpth = skia.Path()
            for sgn in (-1, 1):
                bx = hx + sgn * hr * 0.5; hpth.moveTo(bx, hy + hr * 0.7)
                hpth.quadTo(bx + sgn * hr * 0.9, hy + hr * 1.6, bx + sgn * hr * 0.4 - f * hr * 0.6, hy + hr * 2.4)
            c.drawPath(hpth, skia.Paint(paint))
        if eyes_on:
            ec = RED if not pal.get("inv") else bgc
            ex = hx + f * hr * 0.42; ey = hy + hr * 0.12
            if a.kind == "minion":
                c.drawCircle(ex, ey, hr * 0.26, skia.Paint(AntiAlias=True, Color=C(ec, 255 * alpha)))
            else:
                ep = skia.Path(); ep.moveTo(ex - f * hr * 0.45, ey + hr * 0.12); ep.lineTo(ex + f * hr * 0.5, ey - hr * 0.08)
                ep.lineTo(ex + f * hr * 0.45, ey - hr * 0.24); ep.close()
                c.drawPath(ep, skia.Paint(AntiAlias=True, Color=C(ec, 255 * alpha)))
                c.drawCircle(ex, ey, hr * 1.1, skia.Paint(AntiAlias=True, Color=C(RED, 50 * alpha)))
        elif a.kind in ("hero", "ally"):
            ex = hx + f * hr * 0.45; ey = hy + hr * 0.02
            c.drawLine(ex - f * hr * 0.28, ey, ex + f * hr * 0.3, ey - hr * 0.04,
                       skia.Paint(AntiAlias=True, Color=C(bgc, 255 * alpha), StrokeWidth=hr * 0.13, Style=skia.Paint.kStroke_Style))
            # headband knot gap: a thin bg line across the head reads as a band
            if a.look is None:
              bp = skia.Paint(AntiAlias=True, Color=C(bgc if a.kind == "hero" else RED, 255 * alpha), StrokeWidth=hr * 0.2,
                            Style=skia.Paint.kStroke_Style)
              c.drawLine(hx - hr * 0.95, hy + hr * 0.25, hx + hr * 0.95, hy + hr * 0.25, bp)
        lk = a.look
        if lk == "rival":
            mp = skia.Path()
            mp.addArc(skia.Rect(hx - hr * 0.95, hy - hr * 0.95, hx + hr * 0.95, hy + hr * 0.95), -90 if f > 0 else 90, 180)
            mp.close()
            c.drawPath(mp, skia.Paint(AntiAlias=True, Color=C(mix(bgc, (255, 255, 255), 0.5), 255 * alpha)))
            sp_ = skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha), StrokeWidth=hr * 0.16, Style=skia.Paint.kStroke_Style)
            c.drawLine(hx + f * hr * 0.2, hy + hr * 0.15, hx + f * hr * 0.7, hy + hr * 0.05, sp_)
            if getattr(a, "mask_cracked", 1e9) <= self._t_now:
                c.drawLine(hx + f * hr * 0.1, hy + hr * 0.8, hx + f * hr * 0.45, hy - hr * 0.1, sp_)
        elif lk == "warden":
            c.drawRect(skia.Rect(hx - hr * 1.15, hy - hr * 1.05, hx + hr * 1.15, hy + hr * 1.25), skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha)))
            c.drawRect(skia.Rect(hx - hr * 0.2 if f > 0 else hx - hr * 1.1, hy + hr * 0.05, hx + hr * 1.1 if f > 0 else hx + hr * 0.2, hy + hr * 0.3),
                       skia.Paint(AntiAlias=True, Color=C(RED, 255 * alpha)))
            shp = skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha))
            sx_, sy_ = W["sh"]
            c.drawOval(skia.Rect(sx_ - hr * 1.6, sy_ - hr * 0.6, sx_ + hr * 1.6, sy_ + hr * 0.7), shp)
        elif lk == "guard":
            gp_ = skia.Path(); gp_.moveTo(hx - hr * 0.9, hy + hr * 0.3); gp_.lineTo(hx, hy + hr * 2.0); gp_.lineTo(hx + hr * 0.9, hy + hr * 0.3); gp_.close()
            c.drawPath(gp_, skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha)))
        if a.kind == "ally" and a.look is None:
            # ponytail
            tp = skia.Path(); tp.moveTo(hx - f * hr * 0.6, hy + hr * 0.6)
            tp.quadTo(hx - f * hr * 1.8, hy + hr * 0.8, hx - f * hr * 2.2, hy - hr * 0.6)
            c.drawPath(tp, skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha), Style=skia.Paint.kStroke_Style,
                                      StrokeWidth=hr * 0.45, StrokeCap=skia.Paint.kRound_Cap))

    def _weapon(self, c, a, st, ink, alpha, pal):
        W = st["W"]; wpn = st["wpn"]
        if "tip" not in W: return
        kind = wpn.get("kind", "katana")
        col = RED if wpn.get("color") == "red" else ink
        if pal.get("inv"): col = ink
        hx, hy = W["haF"]; tx, ty = W["tip"]; px, py = W["pommel"]
        wdt = {"katana": 4.2, "great": 9.5, "broken": 4.2, "staff": 5.0, "dagger": 5.0, "spear": 4.6, "hammer": 6.5}.get(kind, 4) * st["s"]
        if wpn.get("dual") and "tipB" in W:
            bp = skia.Paint(AntiAlias=True, Color=C(mix(col, pal["bg0"], 0.25), 255 * alpha), Style=skia.Paint.kStroke_Style, StrokeWidth=wdt)
            c.drawLine(W["pommelB"][0], W["pommelB"][1], W["tipB"][0], W["tipB"][1], bp)
        p = skia.Paint(AntiAlias=True, Color=C(col, 255 * alpha), Style=skia.Paint.kStroke_Style, StrokeWidth=wdt,
                       StrokeCap=skia.Paint.kButt_Cap if kind != "staff" else skia.Paint.kRound_Cap)
        if kind == "spear":
            dx, dy = tx - px, ty - py; L = math.hypot(dx, dy) or 1; ux, uy = dx / L, dy / L
            sp = skia.Paint(p); sp.setColor(C(ink, 255 * alpha))
            c.drawLine(hx - ux * L * 0.35, hy - uy * L * 0.35, tx - ux * 18 * st["s"], ty - uy * 18 * st["s"], sp)
            tri = skia.Path(); k = 7 * st["s"]
            tri.moveTo(tx, ty); tri.lineTo(tx - ux * 26 * st["s"] - uy * k, ty - uy * 26 * st["s"] + ux * k)
            tri.lineTo(tx - ux * 26 * st["s"] + uy * k, ty - uy * 26 * st["s"] - ux * k); tri.close()
            c.drawPath(tri, skia.Paint(AntiAlias=True, Color=C(col, 255 * alpha)))
            return
        if kind == "hammer":
            dx, dy = tx - px, ty - py; L = math.hypot(dx, dy) or 1; ux, uy = dx / L, dy / L
            hp_ = skia.Paint(p); hp_.setColor(C(ink, 255 * alpha)); c.drawLine(px, py, tx, ty, hp_)
            hw, hl = 30 * st["s"], 22 * st["s"]
            pts = [(tx - uy * hw, ty + ux * hw), (tx + ux * hl - uy * hw, ty + uy * hl + ux * hw),
                   (tx + ux * hl + uy * hw, ty + uy * hl - ux * hw), (tx + uy * hw, ty - ux * hw)]
            hpth = skia.Path(); hpth.moveTo(*pts[0]); [hpth.lineTo(*q) for q in pts[1:]]; hpth.close()
            c.drawPath(hpth, skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha)))
            c.drawLine(pts[0][0] * 0.5 + pts[3][0] * 0.5, pts[0][1] * 0.5 + pts[3][1] * 0.5,
                       pts[1][0] * 0.5 + pts[2][0] * 0.5, pts[1][1] * 0.5 + pts[2][1] * 0.5,
                       skia.Paint(AntiAlias=True, Color=C(RED, 255 * alpha), StrokeWidth=4 * st["s"], Style=skia.Paint.kStroke_Style))
            return
        c.drawLine(px, py, tx, ty, p)
        if kind == "great":
            # jagged edge teeth
            dx, dy = tx - hx, ty - hy; L = math.hypot(dx, dy) or 1; nx, ny = -dy / L, dx / L
            tp = skia.Path()
            for i in range(1, 6):
                u = i / 6.5; bx, by = hx + dx * u, hy + dy * u
                tp.moveTo(bx + nx * wdt * 0.4, by + ny * wdt * 0.4); tp.lineTo(bx + nx * wdt * 1.3 + dx / L * 6, by + ny * wdt * 1.3 + dy / L * 6)
                tp.lineTo(bx + nx * wdt * 0.4 + dx / L * 14, by + ny * wdt * 0.4 + dy / L * 14)
            c.drawPath(tp, skia.Paint(AntiAlias=True, Color=C(col, 255 * alpha)))
        # guard
        wd = st["wd"]; gx, gy = hx + wd[0] * 4, hy + wd[1] * 4
        gp = skia.Paint(AntiAlias=True, Color=C(ink, 255 * alpha), StrokeWidth=wdt * 1.6, Style=skia.Paint.kStroke_Style)
        c.drawLine(gx - wd[1] * 8 * st["s"], gy + wd[0] * 8 * st["s"], gx + wd[1] * 8 * st["s"], gy - wd[0] * 8 * st["s"], gp)

    # ---------------- FX
    def draw_fx(self, c, pal, t, back=False):
        S = self.S
        for e in S.events:
            if e["t"] > t: break
            dt = t - e["t"]; k = e["kind"]
            if back and k not in ("dust", "shock", "crack", "ghost", "lift", "burst", "fire"): continue
            if not back and k in ("dust", "shock", "crack", "ghost", "lift", "burst", "fire"): continue
            if k == "ghost":
                a_ = S.actors.get(e["actor"])
                if a_ is not None and dt < e.get("life", 0.45): hyper.ghost(c, self, a_, e, t, pal)
                continue
            if k == "lift":
                if t < e["t_release"] + 2.2: hyper.lift(c, e, t, pal)
                continue
            if k == "burst":
                if dt < e.get("life", 0.7): hyper.burst(c, e, t, pal, self.resolve(e["pos"], e["t"]))
                continue
            if k == "fire":
                hyper.fire(c, e, t, pal); continue
            if k == "beam":
                if t <= e["t1"]:
                    hyper.beam(c, e, t, pal, self.resolve((e["fa"], "hand"), t), self.resolve((e["fb"], "hand"), t), e.get("s", 1.0))
                continue
            if k == "prop":
                if t <= e.get("until", e["t1"] + 1e9):
                    hyper.prop(c, e, t, pal, self.resolve(e["p0"], e["t"]), self.resolve(e["p1"], e["t1"]))
                continue
            slow = e.get("slow", 1.0); dt *= slow
            if k == "spark" and dt < 0.45:
                x0, y0 = self.resolve(e["pos"], e["t"])
                col = (255, 252, 240) if e.get("color") == "white" else (RED if e.get("color") == "red" else pal["ink"])
                if pal.get("inv"): col = pal["ink"]
                p = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeCap=skia.Paint.kRound_Cap)
                for (vx, vy, life) in e["parts"]:
                    if dt > life: continue
                    x = x0 + vx * dt; y = y0 + vy * dt - 900 * dt * dt
                    tl = 0.025
                    x2 = x0 + vx * (dt - tl); y2 = y0 + vy * (dt - tl) - 900 * (dt - tl) ** 2
                    p.setStrokeWidth(4.0 * (1 - dt / life) + 1.2); p.setColor(C(col, 255 * (1 - dt / life)))
                    if e.get("color") == "white" and not pal.get("inv"):
                        p2 = skia.Paint(p); p2.setColor(C(pal["ink"], 255 * (1 - dt / life))); p2.setStrokeWidth(p.getStrokeWidth() + 3)
                        c.drawLine(x2, y2, x, y, p2)
                    c.drawLine(x2, y2, x, y, p)
            elif k == "ink" and dt < 0.95:
                x0, y0 = self.resolve(e["pos"], e["t"])
                col = RED if not pal.get("inv") else pal["ink"]
                for (vx, vy, sz, life) in e["parts"]:
                    if dt > life: continue
                    x = x0 + vx * dt; y = max(1.0, y0 + vy * dt - 1300 * dt * dt)
                    c.drawCircle(x, y, sz * (1 - 0.5 * dt / life), skia.Paint(AntiAlias=True, Color=C(col, 255 * (1 - (dt / life) ** 2))))
            elif k == "flash" and dt < 0.16:
                x0, y0 = self.resolve(e["pos"], e["t"])
                u = dt / 0.16; sz = e.get("size", 70) * (0.6 + 0.8 * u)
                col = RED if e.get("color") == "red" else (255, 252, 244)
                if pal.get("inv"): col = pal["ink"]
                r = random.Random(e["seed"]); path = skia.Path()
                n = 10
                for i in range(n * 2):
                    a = math.pi * i / n + r.uniform(-0.12, 0.12)
                    rr = sz * (1.0 if i % 2 == 0 else 0.28) * r.uniform(0.7, 1.3)
                    (path.moveTo if i == 0 else path.lineTo)(x0 + math.cos(a) * rr, y0 + math.sin(a) * rr)
                path.close()
                if col != pal["ink"]:
                    out = skia.Paint(AntiAlias=True, Color=C(pal["ink"], 255 * (1 - u)), Style=skia.Paint.kStroke_Style, StrokeWidth=5)
                    c.drawPath(path, out)
                c.drawPath(path, skia.Paint(AntiAlias=True, Color=C(col, 255 * (1 - u * u))))
                c.drawCircle(x0, y0, sz * 0.3 * (1 - u), skia.Paint(AntiAlias=True, Color=C((255, 255, 255) if not pal.get("inv") else pal["ink"])))
            elif k == "debris" and dt < 2.0:
                x0, y0 = self.resolve(e["pos"], e["t"])
                col = e.get("col") or pal["near"]
                if pal.get("inv"): col = pal["ink"]
                for (vx, vy, w, sz, pts, life) in e["parts"]:
                    if dt > life: continue
                    x = x0 + vx * dt; y = y0 + vy * dt - 1100 * dt * dt
                    if y < sz * 0.4:
                        y = sz * 0.4; x = x0 + vx * min(dt, 0.9)
                    a = w * dt if y > sz * 0.4 else w * min(dt, 0.9)
                    ca, sa = math.cos(a), math.sin(a)
                    path = skia.Path()
                    for i, (px, py) in enumerate(pts):
                        qx, qy = px * sz, py * sz
                        (path.moveTo if i == 0 else path.lineTo)(x + qx * ca - qy * sa, y + qx * sa + qy * ca)
                    path.close()
                    c.drawPath(path, skia.Paint(AntiAlias=True, Color=C(col, 255 * min(1, (life - dt) * 4))))
            elif k == "dust" and dt < 1.0:
                x0, y0 = self.resolve(e["pos"], e["t"])
                col = mix(pal["bg0"], pal["ink"], 0.25) if not pal.get("inv") else pal["ink"]
                for (dx, dy, s) in e["parts"]:
                    u = dt / 1.0
                    r = e.get("size", 40) * s * (0.4 + 1.4 * (1 - (1 - u) ** 2))
                    c.drawCircle(x0 + dx * e.get("size", 40) * 3.2 * (1 - (1 - u) ** 2), y0 + dy * r * 0.8, r,
                                 skia.Paint(AntiAlias=True, Color=C(col, 150 * (1 - u))))
            elif k == "shock" and dt < 0.45:
                x0, y0 = self.resolve(e["pos"], e["t"])
                u = dt / 0.45; r = e.get("size", 160) * (0.2 + 1.2 * (1 - (1 - u) ** 3))
                col = (255, 250, 245) if not pal.get("inv") else pal["ink"]
                c.drawOval(skia.Rect(x0 - r, y0 - r * e.get("flat", 0.28), x0 + r, y0 + r * e.get("flat", 0.28)),
                           skia.Paint(AntiAlias=True, Color=C(pal["ink"] if not pal.get("inv") else pal["bg0"], 220 * (1 - u)),
                                      Style=skia.Paint.kStroke_Style, StrokeWidth=12 * (1 - u) + 2))
                c.drawOval(skia.Rect(x0 - r, y0 - r * e.get("flat", 0.28), x0 + r, y0 + r * e.get("flat", 0.28)),
                           skia.Paint(AntiAlias=True, Color=C(col, 200 * (1 - u)), Style=skia.Paint.kStroke_Style, StrokeWidth=5 * (1 - u) + 1))
            elif k == "crack" and (t < e.get("until", e["t"] + 30)):
                x0, y0 = self.resolve(e["pos"], e["t"])
                u = min(1.0, dt / 0.12)
                p = skia.Paint(AntiAlias=True, Color=C(RED if e.get("red") else pal["ink"]), Style=skia.Paint.kStroke_Style,
                               StrokeWidth=4, StrokeJoin=skia.Paint.kMiter_Join)
                for ln in e["lines"]:
                    path = skia.Path(); path.moveTo(x0, 1)
                    for (px, py) in ln[1:int(1 + u * (len(ln) - 1))]: path.lineTo(x0 + px, 1 + py * 0.3)
                    c.drawPath(path, p)

    def draw_screen_fx(self, c, pal, t, shot, cam):
        W, H, S = self.W, self.H, self.S
        sc = W / 1920 if not self.vertical else W / 1080
        # embers / ash drifting in screen space
        env = S.envs[shot["env"]] if isinstance(shot["env"], str) else shot["env"]
        if env.embers:
            r = random.Random(5)
            for i in range(70):
                x0, sp, sz, ph = r.uniform(0, 1), r.uniform(0.04, 0.16), r.uniform(1.5, 4.5), r.uniform(0, 1)
                y = ((ph - t * sp) % 1.0) * (H + 40) - 20
                x = (x0 * W + math.sin(t * 1.3 + i) * 30 - cam["cx"] * cam["z"] * 0.15 * sz / 4) % (W + 40) - 20
                c.drawCircle(x, H - y, sz * sc, skia.Paint(AntiAlias=True, Color=C(RED, 200)))
        if env.ash:
            ambience.ash(c, W, H, t, cam, mix(pal["ink"], pal["bg0"], 0.45), sc)
        for e in S.events:
            if e["t"] > t: break
            if e["kind"] == "birds": ambience.birds(c, e, t, W, H, mix(pal["ink"], pal["bg0"], 0.15))
        if env.rain:
            r = random.Random(6); p = skia.Paint(AntiAlias=True, Color=C(pal["ink"], 70), StrokeWidth=2 * sc)
            for i in range(120):
                x0, sp, ph = r.uniform(0, 1), r.uniform(1.6, 2.4), r.uniform(0, 1)
                y = ((ph + t * sp) % 1.0) * (H + 100) - 50; x = (x0 * W - y * 0.25) % W
                c.drawLine(x, y, x - 10 * sc, y + 46 * sc, p)
        for e in S.events:
            if e["t"] > t: break
            k = e["kind"]; dt = t - e["t"]
            if k == "speed" and t < e["t1"]:
                a = math.radians(e.get("angle", 0)); ux, uy = math.cos(a), math.sin(a)
                col = RED if e.get("color") == "red" else pal["ink"]
                fi = int(t * S.fps)
                for i, (q, ln, ph) in enumerate(e["lines"]):
                    if hrand(e["seed"], i, fi // 2) % 3 == 0: continue
                    off = (q - 0.5) * (W + H) * 1.1
                    cx0, cy0 = W / 2 - uy * off, H / 2 + ux * off
                    if e.get("radial"):
                        continue
                    s0 = ((ph + t * 3.1 * (0.6 + ln)) % 1.0 - 0.5) * (W + H)
                    L = 300 * ln * sc
                    x1, y1 = cx0 + ux * s0, cy0 + uy * s0
                    if e.get("center") and abs(q - 0.5) < 0.18: continue
                    c.drawLine(x1, y1, x1 + ux * L, y1 + uy * L,
                               skia.Paint(AntiAlias=True, Color=C(col, 120 + 100 * ln), StrokeWidth=(2 + 5 * ln) * sc))
            elif k == "radial" and t < e["t1"]:
                # focus lines from the frame edge toward the centre
                col = pal["ink"]; r = random.Random(e["seed"] + int(t * S.fps) // 2)
                path = skia.Path()
                for i in range(64):
                    a = r.uniform(0, 2 * math.pi); w0 = r.uniform(0.004, 0.012)
                    R0, R1 = max(W, H) * 0.9, max(W, H) * r.uniform(0.36, 0.5)
                    path.moveTo(W / 2 + math.cos(a - w0) * R0, H / 2 + math.sin(a - w0) * R0)
                    path.lineTo(W / 2 + math.cos(a) * R1, H / 2 + math.sin(a) * R1)
                    path.lineTo(W / 2 + math.cos(a + w0) * R0, H / 2 + math.sin(a + w0) * R0)
                    path.close()
                c.drawPath(path, skia.Paint(AntiAlias=True, Color=C(col, 230)))
            elif k == "slashline" and dt < e.get("life", 0.2):
                u = dt / e.get("life", 0.2)
                a = math.radians(e.get("angle", -20)); ux, uy = math.cos(a), math.sin(a)
                L = (W + H) * (0.3 + 0.9 * min(1, u * 4))
                cx0, cy0 = W * e.get("cx", 0.5), H * e.get("cy", 0.5)
                col = RED if e.get("color") == "red" else (255, 252, 246)
                w = e.get("width", 18) * (1 - u) * sc + 1
                c.drawLine(cx0 - ux * L / 2, cy0 - uy * L / 2, cx0 + ux * L / 2, cy0 + uy * L / 2,
                           skia.Paint(AntiAlias=True, Color=C(pal["ink"] if col != pal["ink"] else pal["bg0"]), StrokeWidth=w + 8 * sc,
                                      StrokeCap=skia.Paint.kRound_Cap))
                c.drawLine(cx0 - ux * L / 2, cy0 - uy * L / 2, cx0 + ux * L / 2, cy0 + uy * L / 2,
                           skia.Paint(AntiAlias=True, Color=C(col), StrokeWidth=w, StrokeCap=skia.Paint.kRound_Cap))
        for e in S.events:
            if e["t"] > t: break
            if e["kind"] == "skysplit": hyper.skysplit(c, e, t, W, H, pal)
        # slow-mo treatment: letterbox + red edge
        if "slowmo" in shot["tags"] or "letterbox" in shot["tags"]:
            bh = H * (0.11 if not self.vertical else 0.07)
            p = skia.Paint(Color=C((6, 4, 6)))
            c.drawRect(skia.Rect(0, 0, W, bh), p); c.drawRect(skia.Rect(0, H - bh, W, H), p)
        for e in S.events:
            if e["t"] > t: break
            if e["kind"] == "text" and t < e["t1"]:
                self.draw_text(c, e, t, pal)

    def overlays(self, t):
        """full-screen fades, blended in numpy (fast)"""
        for e in self.S.events:
            if e["t"] > t: break
            k = e["kind"]
            if k in ("fade", "hold") and t < e["t1"]:
                if k == "fade":
                    u = (t - e["t"]) / (e["t1"] - e["t"]); a0, a1 = e.get("a0", 1.0), e.get("a1", 0.0); al = a0 + (a1 - a0) * u
                else:
                    al = e.get("a", 1.0)
                col = {"black": (0, 0, 0), "white": (255, 255, 255), "red": RED}[e.get("color", "black")]
                if al <= 0.003: continue
                a = int(al * 256)
                rgb = self.buf[:, :, :3]
                if col == (0, 0, 0):
                    rgb[:] = (rgb.astype(np.uint16) * (256 - a) >> 8).astype(np.uint8)
                else:
                    cc = np.array(col, np.uint16) * a
                    rgb[:] = ((rgb.astype(np.uint16) * (256 - a) + cc) >> 8).astype(np.uint8)

    def background(self, c0, c1, invert):
        key = (tuple(int(v) for v in c0), tuple(int(v) for v in c1), invert)
        bg = self._bgs.get(key)
        if bg is None:
            H, W = self.H, self.W
            y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
            g = np.array(c0, np.float32) * (1 - y) + np.array(c1, np.float32) * y
            g = np.broadcast_to(g, (H, W, 3)).copy()
            if not invert:
                yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
                r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62 if W > H else H * 0.55)) ** 2)
                v = 1 - 0.42 * np.clip((r - 0.55) / 0.75, 0, 1) ** 1.6
                g *= v[:, :, None]
            bg = np.empty((H, W, 4), np.uint8); bg[:, :, :3] = np.clip(g, 0, 255).astype(np.uint8); bg[:, :, 3] = 255
            self._bgs[key] = bg
        return bg

    def draw_text(self, c, e, t, pal):
        W, H = self.W, self.H
        sc = W / 1920 if not self.vertical else W / 1080 * 0.82
        dur = e["t1"] - e["t"]; u = (t - e["t"]) / dur
        fade = min(1.0, (t - e["t"]) / 0.25, (e["t1"] - t) / 0.35)
        tf = self.font_tf if e.get("font", "impact") == "impact" else self.font_tf2
        size = e.get("size", 120) * sc
        font = skia.Font(tf, size)
        font.setEdging(skia.Font.Edging.kAntiAlias)
        txt = e["s"]
        spacing = e.get("track", 0.0) * size
        widths = font.getWidths(font.textToGlyphs(txt))
        total = sum(widths) + spacing * (len(txt) - 1)
        x = W * e.get("x", 0.5) - total / 2
        y = H * (e.get("y", 0.5) if not self.vertical else e.get("vy", e.get("y", 0.5))) + size * 0.35
        col = RED if e.get("color") == "red" else ({"ink": pal["ink"], "white": (245, 240, 235)}.get(e.get("color", "white")))
        grow = 1.0 + e.get("grow", 0.06) * u
        c.save(); c.translate(W / 2, y); c.scale(grow, grow); c.translate(-W / 2, -y)
        p = skia.Paint(AntiAlias=True, Color=C(col, 255 * fade))
        for ch, w in zip(txt, widths):
            c.drawString(ch, x, y, font, p); x += w + spacing
        c.restore()

    def frame(self, t, sub=1):
        self._t_now = t
        return self.render(t, sub)
