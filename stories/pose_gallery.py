"""Pose gallery: every pose in rig.POSES side by side (QA for the rig)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from engine import Story
from rig import POSES

def build(fps=30, W=1920, H=1080, vertical=False):
    st = Story(os.path.join(os.path.dirname(HERE), "samples", "sample_track.beatmap.json"), fps, W, H)
    names = list(POSES)
    per = 10
    for i, n in enumerate(names):
        row, col = divmod(i, per)
        kind = "villain" if n in ("summon", "loom") else "hero"
        a = st.actor(n, kind=kind, scale=1.0, weapon=dict(len=96, kind="katana"), scarf="red")
        a.key(0, pose=n, x=col * 230 + row * 2300 * 0, air=0, facing=1)
        a.row = row
    st.env("blank", sky="none", far=False, mid=False, rubble=False)
    rows = (len(names) + per - 1) // per
    for r in range(rows):
        only = [n for i, n in enumerate(names) if i // per == r]
        st.shot(r * 8, r * 8 + 8, "blank", dict(x=1035, y=250, zoom=0.78), palette="paper", only=only)
        st.ev("text", r * 8, dur=8, s="   ".join(only), size=22, y=0.06, color="ink", font="pal")
    return st
