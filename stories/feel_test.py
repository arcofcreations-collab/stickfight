"""FEEL TEST - a locked-off camera and a plain exchange of hits, made for game-feel measurements.

Render it twice with different hit-stop and compare the clips with Feel Gap
(https://github.com/arcofcreations-collab/feel-gap, or any frame-by-frame tool):

  STICKFIGHT_HITSTOP=0.5 python render.py stories/feel_test.py --fps 60 --w 960 --h 540 --sub 1 --out snappy.mp4
  STICKFIGHT_HITSTOP=2.0 python render.py stories/feel_test.py --fps 60 --w 960 --h 540 --sub 1 --out heavy.mp4

The camera never moves, the palette stays the same and there are no cuts, so the only thing that changes
between the two renders is how long each impact freezes.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from engine import Story
from choreo import duel, SWORD, HANDS

BEATMAP = os.path.join(os.path.dirname(HERE), "samples", "sample_track.beatmap.json")


def build(fps=30, W=1920, H=1080, vertical=False):
    st = Story(BEATMAP, fps, W, H, seed=3)
    st.hitstop_scale = float(os.environ.get("STICKFIGHT_HITSTOP", "1.0"))
    a = st.actor("left", kind="hero", look="thief", weapon=dict(len=110, kind="katana"), scarf="red", z=2)
    b = st.actor("right", kind="villain", look="rival", weapon=dict(len=110, kind="katana"), scarf="ink", z=1)
    # one hit every two beats, with resets between, so every impact stands on its own
    # eight clean hits: sparks and a local flash on each, no full-screen inverted impact frames (power < 1.4)
    duel(st, a, b, 2, "A.B.A.B.A.B.A.B.", 0, gap=170, step=1, seed=1, a_moves=SWORD + HANDS[:2], b_moves=SWORD,
         power=1.15, setup=True)
    st.env("plain", sky="none", seed=2, rubble=False, far=False, mid=False)
    st.shot(0, 20, "plain", dict(x=85, y=170, zoom=2.0), palette="night")
    return st
