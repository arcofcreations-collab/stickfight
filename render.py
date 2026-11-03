"""render.py - render a stickfight story to video (parallel workers -> x264 segments -> concat).

  python render.py STORY.py --out film.mp4 [--audio song.mp3] [--vertical] [--from S --to S]
                   [--workers 6] [--sub 2] [--fps 30] [--stills 10,20.5,...  --stills-dir DIR]

STORY.py must define build(fps, W, H) -> engine.Story.
"""
import argparse, importlib.util, os, subprocess, sys, time, math
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import engine

def load_story(path, fps, W, H, vertical):
    spec = importlib.util.spec_from_file_location("story_mod", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    st = m.build(fps=fps, W=W, H=H, vertical=vertical)
    st.finalize(); return st

def dims(a):
    return (1080, 1920) if a.vertical else (a.w, a.h)

def worker(a):
    W, H = dims(a)
    st = load_story(a.story, a.fps, W, H, a.vertical)
    R = engine.Renderer(st, W, H, vertical=a.vertical)
    f0, f1 = a.chunk
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(a.fps),
           "-i", "-", "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-g", str(a.fps * 2),
           "-threads", "2", "-x264-params", "rc-lookahead=12:sync-lookahead=0", a.seg]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for fi in range(f0, f1):
        buf = R.frame(fi / a.fps, sub=a.sub)
        pr.stdin.write(buf.tobytes())
        if (fi - f0) % 150 == 0:
            print(f"[w{a.wid}] {fi - f0}/{f1 - f0} {time.time() - t0:.0f}s", flush=True)
    pr.stdin.close(); pr.wait()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story"); ap.add_argument("--out"); ap.add_argument("--audio")
    ap.add_argument("--vertical", action="store_true"); ap.add_argument("--w", type=int, default=1920); ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30); ap.add_argument("--sub", type=int, default=2)
    ap.add_argument("--from", dest="t0", type=float, default=0.0); ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--workers", type=int, default=6); ap.add_argument("--crf", type=int, default=17); ap.add_argument("--preset", default="medium")
    ap.add_argument("--stills"); ap.add_argument("--stills-dir", default=os.path.join(HERE, "work", "stills"))
    ap.add_argument("--resume", action="store_true", help="keep finished segments from an earlier run with the same settings")
    ap.add_argument("--chunk", type=int, nargs=2); ap.add_argument("--seg"); ap.add_argument("--wid", type=int, default=0)
    a = ap.parse_args()
    if a.chunk:
        return worker(a)
    W, H = dims(a)
    if a.stills:
        import numpy as np
        from PIL import Image
        st = load_story(a.story, a.fps, W, H, a.vertical)
        R = engine.Renderer(st, W, H, vertical=a.vertical)
        os.makedirs(a.stills_dir, exist_ok=True)
        for s in a.stills.split(","):
            t = float(s); buf = R.frame(t, sub=a.sub)
            Image.fromarray(buf[:, :, :3].copy()).save(os.path.join(a.stills_dir, f"still_{t:07.2f}.png"))
            print("still", t)
        return
    st = load_story(a.story, a.fps, W, H, a.vertical)
    t1 = a.t1 if a.t1 is not None else st.duration
    F0, F1 = int(round(a.t0 * a.fps)), int(math.ceil(t1 * a.fps))
    n = max(1, a.workers); per = math.ceil((F1 - F0) / n)
    work = os.path.join(HERE, "work", "segs_" + os.path.splitext(os.path.basename(a.out))[0].replace(" ", "_"))
    os.makedirs(work, exist_ok=True)
    procs, segs = [], []
    t0 = time.time()
    def frames_in(path):
        if not os.path.exists(path): return -1
        r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", path], capture_output=True, text=True)
        try: return int(r.stdout.strip())
        except ValueError: return -1
    for i in range(n):
        f0, f1 = F0 + i * per, min(F1, F0 + (i + 1) * per)
        if f0 >= f1: break
        seg = os.path.join(work, f"seg{i:02d}.mp4"); segs.append(seg)
        if a.resume and frames_in(seg) == f1 - f0:
            print(f"seg{i:02d} already complete, keeping it"); continue
        cmd = [sys.executable, os.path.abspath(__file__), a.story, "--chunk", str(f0), str(f1), "--seg", seg, "--wid", str(i),
               "--fps", str(a.fps), "--sub", str(a.sub), "--crf", str(a.crf), "--preset", a.preset, "--w", str(a.w), "--h", str(a.h)]
        if a.vertical: cmd.append("--vertical")
        procs.append(subprocess.Popen(cmd))
    rc = [p.wait() for p in procs]
    if any(rc): sys.exit(f"worker failed {rc}")
    lst = os.path.join(work, "list.txt")
    with open(lst, "w") as f:
        for s in segs: f.write(f"file '{s.replace(os.sep, '/')}'\n")
    out = a.out
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst]
    if a.audio:
        cmd += ["-ss", str(a.t0), "-t", str((F1 - F0) / a.fps), "-i", a.audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "256k"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    print(f"done {out} frames={F1 - F0} in {time.time() - t0:.0f}s")

if __name__ == "__main__":
    main()
