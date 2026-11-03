"""THE LANTERN ROAD - the sample story that ships with stickfight (an original story, free to copy and change).

Story (reads with no words): a lone swordswoman walks a hill road at dusk. Three bandits jump her and
fall one per beat. Their masked boss powers up on the drop, they duel on the beat grid, and she wins with
a slow-motion launch. Dawn breaks as she walks on.

Song map for samples/sample_track.wav (120 bpm, 4 beats a bar, beat b -> t = b0 + b * 0.5 s):
  b 0..16 intro | 16..48 build: the walk and the bandits | 44..48 power-up | 48..80 the drop: the duel
  80..96 outro: dawn

To use your own song: run beatmap.py on it, point BEATMAP at the new json and move the beat numbers.
Set STICKFIGHT_HITSTOP=0.5 (or 2) to shorten or stretch every hit-stop; handy for game-feel tests.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from engine import Story
from choreo import duel, minion, kill, power_up, MIXED, SWORD

BEATMAP = os.path.join(os.path.dirname(HERE), "samples", "sample_track.beatmap.json")


def build(fps=30, W=1920, H=1080, vertical=False):
    st = Story(BEATMAP, fps, W, H, seed=11)
    st.hitstop_scale = float(os.environ.get("STICKFIGHT_HITSTOP", "1.0"))
    # beatmap.py's first detected beat on this track is the 2nd beat of bar 1 (downbeat_offset 3), so pull the
    # grid back one beat: then beat 0 is the first downbeat and bars start on b 0, 4, 8, ...
    st.b0 = st.beats[0] - st.beat
    T = st.T

    # ------------------------------------------------------------ cast
    hero = st.actor("ren", kind="hero", look="thief", scale=1.0, weapon=dict(len=110, kind="katana"), scarf="red", z=3)
    boss = st.actor("mask", kind="villain", look="rival", scale=1.15, weapon=dict(len=150, kind="spear"), scarf="ink", z=2)
    boss.spawn = T(39.5)
    # each bandit sprints in from the right just before the beat he falls on (b24, b30, b36)
    bandits = [minion(st, f"bandit{i}", 24 + 6 * i - 3, 1100 + 212 * i) for i in range(3)]

    # ------------------------------------------------------------ places
    st.env("road", sky="sun", sun=(0.66, 0.30, 0.16), seed=5, rubble=True, skyline=0.35, hills=True, mist=0.25,
           rays=0.12, flags=False, x0=-2500, x1=5000)
    st.env("road_hot", sky="sun", sun=(0.6, 0.26, 0.14), seed=5, rubble=True, skyline=0.35, hills=True, mist=0.15,
           rays=0.18, embers=True, ash=True, heat=True, x0=-2500, x1=5000)
    st.env("dawn", sky="sun", sun=(0.5, 0.62, 0.16), seed=5, rubble=False, skyline=0.35, hills=True, mist=0.3,
           rays=0.14, x0=-2500, x1=5000)

    def cam(follow=None, z=1.4, **kw):
        d = dict(zoom=z, **kw)
        if follow: d["follow"] = follow if isinstance(follow, list) else [follow]
        return d

    # ============================================================ INTRO b0..16
    hero.key(-1, pose="stand", x=-900, facing=1, air=0, lock=1)
    hero.key(4, pose="stand", x=-900)
    hero.run(4, 16, -300, kind="walk", pose_end="stand")
    st.shot(0, 8, "road", cam(x=-300, y=420, z=0.55, zoom1=0.65), palette="dusk", tags=("letterbox",))
    st.shot(8, 16, "road", cam(["ren"], z=1.6, dy=40), palette="dusk", tags=("letterbox",))
    st.ev("fade", None, t=0.0, dur=None, t1=T(4), color="black", a0=1.0, a1=0.0)
    st.ev("text", 1, dur=7, s="THE LANTERN ROAD", size=120, y=0.42, color="ink", track=0.05, grow=0.04)
    st.ev("text", 3, dur=5, s="a stickfight sample", size=36, y=0.62, color="ink", font="pal", grow=0.02)

    # ============================================================ BUILD b16..48: three bandits, one per beat
    hero.run(16, 22, 500, kind="run", pose_end="guard")
    st.shot(16, 22, "road", cam(["ren"], z=1.2, dy=30, orbit=8), palette="dusk")
    xh = 500
    for i, m in enumerate(bandits):
        b = 24 + 6 * i
        xh = kill(st, hero, m, b, move=SWORD[i % 3][:2], xh=xh, gap=130, d=1, kb=180, launch=60 if i == 2 else 0,
                  approach=1100 + 212 * i, power=1.2 + 0.2 * i, slash=(i == 2))
        hero.key(b + 2, pose="guard", x=xh + 40)
        if i < 2:
            hero.run(b + 2, b + 5.5, xh + 200, kind="run", pose_end="guard")
            xh += 200
        st.shot(b - 2, b + 4, "road", cam(["ren", m.name], z=1.5 + 0.2 * i, low=(i == 1), rot=(-4 if i == 2 else 0)),
                palette="dusk")
    st.shot(40, 44, "road", cam(["mask"], z=2.6, dy=60, part="head"), palette="night", tags=("letterbox",))
    boss.key(39.5, pose="stand", x=xh + 420, facing=-1, air=0, lock=1)
    boss.key(43, pose="stand", x=xh + 420, head=-10)
    # the boss powers up on the drop
    power_up(st, boss, 44, 48, xh + 420, level=1.6, sky_invert=False, radius=420, hold=6)
    st.shot(44, 48, "road_hot", cam(["mask"], z=1.4, zoom1=1.8, low=True), palette="night")

    # ============================================================ DROP b48..80: the duel
    xa, xb, bend = duel(st, hero, boss, 49, "abab cLpb dD.k abAB r-c. sSa.", xh + 160, gap=160, step=1, seed=3,
                        a_moves=MIXED, b_moves=SWORD, power=1.2, setup=True)
    for (b0, b1, kw) in [(48, 52, dict(z=1.5, orbit=10)), (52, 56, dict(z=2.0, rot=-5)), (56, 60, dict(z=1.3, orbit=-14)),
                         (60, 64, dict(z=1.8, low=True)), (64, 68, dict(z=1.4, orbit=16)), (68, 72, dict(z=2.1, rot=6)),
                         (72, 76, dict(z=1.5, orbit=-10))]:
        st.shot(b0, b1, "road_hot", cam(["ren", "mask"], **kw), palette="night")
    # the finisher: a slow-motion launch on beat 78
    hero.key(77.4, pose="h_wind", x=xa, facing=1 if xb > xa else -1, ease="out")
    hero.key(78, pose="up_cut", x=xa + 30 * (1 if xb > xa else -1), ease="snap")
    boss.key(78, pose="hit_air", x=xb + 40 * (1 if xb > xa else -1), air=20, ease="snap")
    boss.key(79.5, pose="fall", x=xb + 260 * (1 if xb > xa else -1), air=0, arc=220, rot=-200, xease="out")
    boss.flash(78)
    st.slowmo(78, w=1.0, r=0.2)
    st.hit_fx(78, ("mask", "chest"), 2.0, snd="hit")
    st.ev("slashline", 78, angle=-30, life=0.2, cx=0.5, cy=0.5)
    st.ev("dust", 79.5, pos=("mask", "chest"), n=10, size=60)
    st.sfx(79.5, "thud", 0)
    st.shot(76, 80, "road_hot", cam(["ren", "mask"], z=1.7, low=True), palette="night", tags=("letterbox",))

    # ============================================================ OUTRO b80..96: dawn
    hero.key(82, pose="stand", x=xa)
    hero.run(84, 96, xa + 700, kind="walk", pose_end="stand")
    st.shot(80, 88, "dawn", cam(["ren"], z=1.3, dy=40), palette="dawn", tags=("letterbox",))
    st.shot(88, 96, "dawn", cam(x=xa + 300, y=400, z=0.6, zoom1=0.5), palette="dawn", tags=("letterbox",))
    st.ev("fade", None, t=T(93), dur=None, t1=T(96), color="black", a0=0.0, a1=1.0)
    return st
