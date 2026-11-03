"""Smoke test: load the shipped stories, render a few small frames and build a sound-cue stem.

    python tests/test_smoke.py          (or: python -m pytest tests)

Needs the packages in requirements.txt. ffmpeg is not needed for this test. Runs offline in under a minute.
"""
import os, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import engine, render, sfx  # noqa: E402

STORIES = ["stories/sample_duel.py", "stories/feel_test.py", "stories/pose_gallery.py"]


def test_stories_render():
    for rel in STORIES:
        st = render.load_story(os.path.join(ROOT, rel), 30, 480, 270, False)
        assert st.duration > 10 and st.shots, rel
        R = engine.Renderer(st, 480, 270)
        for t in (2.0, 13.0, 25.0):
            buf = R.frame(t, sub=1)
            assert buf.shape == (270, 480, 4), buf.shape
            assert buf[:, :, :3].std() > 2.0, "%s frame at %.1fs looks blank" % (rel, t)
    print("ok: %d stories load and render" % len(STORIES))


def test_vertical_render():
    st = render.load_story(os.path.join(ROOT, "stories/sample_duel.py"), 30, 270, 480, True)
    buf = engine.Renderer(st, 270, 480, vertical=True).frame(26.0, sub=1)
    assert buf.shape == (480, 270, 4)
    print("ok: vertical 9:16 frame")


def test_sfx_cues():
    st = render.load_story(os.path.join(ROOT, "stories/sample_duel.py"), 30, 1920, 1080, False)
    assert len(st.cues) > 10, "the sample story should log sound cues"
    empty = os.path.join(ROOT, "work", "_empty_sfx_lib")
    os.makedirs(empty, exist_ok=True)
    stem = sfx.build(st, 0.0, 5.0, out=None, lib=empty)      # no sounds: every cue is skipped, nothing breaks
    assert stem.shape[1] == 2 and np.abs(stem).max() == 0.0
    print("ok: %d sound cues, empty library handled" % len(st.cues))


if __name__ == "__main__":
    test_stories_render()
    test_vertical_render()
    test_sfx_cues()
