"""qa_cuts.py - find hard cuts in a rendered video and measure how far each sits from the beat grid.
  python qa_cuts.py film.mp4 beatmap.json [--thresh 0.25] [--offset 0]
--offset: seconds into the song where the video starts (for a Short cut from the middle).
"""
import sys, re, json, subprocess, argparse
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("beatmap")
ap.add_argument("--thresh", type=float, default=0.25); ap.add_argument("--offset", type=float, default=0.0)
a = ap.parse_args()
bm = json.load(open(a.beatmap)); beats = np.array(bm["beats"]); per = bm["beat_period"]
r = subprocess.run(["ffmpeg", "-nostdin", "-i", a.video, "-vf", f"scale=480:-1,select='gt(scene,{a.thresh})',showinfo", "-an", "-f", "null", "-"],
                   capture_output=True, text=True)
ts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
fps = 30.0
offs = []
for t in ts:
    st = t + a.offset
    i = int(np.argmin(np.abs(beats - st))); d = st - beats[i]
    # also allow half-beat grid (flurries)
    offs.append(d)
offs = np.array(offs)
print(f"cuts found: {len(ts)}")
if len(ts):
    fr = np.abs(offs) * fps
    print(f"distance to nearest beat: median {np.median(np.abs(offs))*1000:.0f} ms, 90% {np.percentile(np.abs(offs),90)*1000:.0f} ms, max {np.abs(offs).max()*1000:.0f} ms")
    print(f"within 1 frame: {np.mean(fr <= 1.01)*100:.0f}%   within 2 frames: {np.mean(fr <= 2.01)*100:.0f}%")
    bad = [(round(t, 2), round(d * 1000)) for t, d in zip(ts, offs) if abs(d) * fps > 2.01]
    if bad: print("off-beat cuts (t, ms):", bad[:40])
