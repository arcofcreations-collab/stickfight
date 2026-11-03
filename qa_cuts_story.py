"""qa_cuts_story.py - check every detected cut in a render against the story's beat-locked shot starts.
Detections that are not shot cuts must be explained by in-shot flashes (impact frames, bursts, fades) or blinks.
  python qa_cuts_story.py STORY.py film.mp4 [--offset S] [--vertical]
"""
import sys, re, subprocess, argparse, os
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import render
ap = argparse.ArgumentParser(); ap.add_argument("story"); ap.add_argument("video"); ap.add_argument("--offset", type=float, default=0.0)
ap.add_argument("--thresh", type=float, default=0.3)
a = ap.parse_args()
st = render.load_story(a.story, 30, 1920, 1080, False)
starts = [s["t0"] for s in st.shots if s["t0"] > 0.1]
flashes = [st.song_time(e["t"]) for e in st.events if e["kind"] in ("impact", "burst", "fade", "hold", "slashline", "skysplit")
           or (e["kind"] == "flash" and e.get("size", 0) >= 100)]
for ac in st.actors.values():
    flashes += [st.song_time(k["t"]) for k in ac.track.keys if k.get("ease") == "step"]
r = subprocess.run(["ffmpeg", "-nostdin", "-i", a.video, "-vf", f"scale=480:-1,select='gt(scene,{a.thresh})',showinfo", "-an", "-f", "null", "-"],
                   capture_output=True, text=True)
ts = [float(m) + a.offset for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
on = [t for t in ts if min(abs(t - s) for s in starts) <= 0.034]
other = [t for t in ts if t not in on]
expl = [t for t in other if min(abs(t - f) for f in flashes) <= 0.25]
bad = [round(t, 2) for t in other if t not in expl]
win = [s for s in starts if a.offset <= s <= a.offset + 1e9]
print(f"detected {len(ts)}: {len(on)} are shot cuts within 1 frame of their beat, {len(expl)} are in-shot impact flashes/blinks,"
      f" unexplained: {bad}")
off = [min(abs(s - b) for b in st.beats) for s in starts]
print(f"story shot starts: {len(starts)}, max distance from the beat grid {max(off)*1000:.1f} ms")
