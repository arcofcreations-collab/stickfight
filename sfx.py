"""sfx.py - build a sound-effects stem for a stickfight story from its recorded cues.

  python sfx.py STORY.py out.wav [--from S --to S] [--lib DIR]
  python sfx.py --check [--lib DIR]          (show which cue kinds have sounds)

Every hit, clash, whoosh, slam and power-up in a story logs a cue (st.sfx). This places one sound file
for each cue, picked from YOUR sound library. Cue times are mapped through the story's slow-motion and
hit-stop warp, so each sound lands on the frame where the hit is seen.

No sounds ship with this repo. Point it at a folder you have the rights to use:

  sfx_library/                 (default; or set STICKFIGHT_SFX_LIB, or pass --lib)
    whoosh/   *.wav *.ogg *.flac *.mp3
    hit/      punch/   clash/   clash_big/   thud/   boom/   scrape/   draw/
    dodge/    rumble/  power/   roar/   crackle/   bell/   screams/   swoosh_big/
    ambience/wind/  ambience/storm/  ambience/bells/  ambience/night/  ambience/darkwind/  ambience/rumble/

Any folder can be missing: cues of that kind are skipped. Good free sources with licences that allow use in
videos include Kenney's CC0 packs and the yearly Sonniss GDC bundle (check each pack's licence; most do not
allow you to re-share the files themselves). `python tools/make_sample_audio.py` writes a small synthetic
starter set into sfx_library/ so the pipeline runs end to end before you add real recordings.
"""
import argparse, glob, os, sys, subprocess, hashlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
SR = 48000
EXTS = (".wav", ".ogg", ".flac", ".mp3", ".aif", ".aiff")

# kind -> (base gain dB, playback rate, max seconds). Files come from <lib>/<kind>/.
BANK = {
    "whoosh": (-13, 1.0, 0.55), "hit": (-9, 1.0, 0.9), "punch": (-9, 1.0, 0.8), "clash": (-10, 1.0, 1.0),
    "clash_big": (-7, 1.0, 1.8), "thud": (-9, 1.0, 1.0), "boom": (-5, 0.72, 2.5), "scrape": (-11, 1.0, 1.2),
    "draw": (-9, 1.0, 1.4), "dodge": (-12, 1.0, 0.6), "rumble": (-10, 0.6, 3.2), "power": (-8, 0.85, 2.5),
    "roar": (-9, 0.8, 3.0), "crackle": (-12, 0.8, 1.5), "bell": (-12, 1.0, 5.0), "screams": (-20, 1.0, 3.0),
    "swoosh_big": (-9, 0.8, 1.2),
}
# ambient beds, looped under the song: kind -> (base gain dB, playback rate). Files come from <lib>/ambience/<kind>/.
AMB = {"wind": (-15, 1.0), "storm": (-15, 1.0), "bells": (-20, 1.0), "night": (-18, 1.0), "darkwind": (-14, 0.85),
       "rumble": (-12, 0.6)}

_cache = {}


def library(lib=None):
    return os.path.abspath(lib or os.environ.get("STICKFIGHT_SFX_LIB") or os.path.join(HERE, "sfx_library"))


def files_for(lib, sub):
    d = os.path.join(lib, *sub.split("/"))
    return sorted(f for f in glob.glob(os.path.join(d, "*")) if f.lower().endswith(EXTS))


def load(path, rate=1.0):
    key = (path, rate)
    if key in _cache: return _cache[key]
    cdir = os.path.join(HERE, "work", "sfxcache"); os.makedirs(cdir, exist_ok=True)
    st = os.stat(path)
    h = hashlib.md5(f"{path}|{st.st_size}|{st.st_mtime}|{rate}".encode()).hexdigest()[:16]
    npy = os.path.join(cdir, h + ".npy")
    if os.path.exists(npy):
        a = np.load(npy)
    else:
        sr_in = int(SR * rate)   # decode at SR*rate, play back at SR -> pitch/speed down by `rate`
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "2", "-ar", str(sr_in), "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        a = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
        pk = np.abs(a).max() or 1.0
        a = a / pk * 0.9                      # peak-normalise each recording, gains are set per kind
        np.save(npy, a)
    _cache[key] = a
    return a


def build(story, t0=0.0, t1=None, out=None, lib=None):
    lib = library(lib)
    t1 = story.duration if t1 is None else t1
    n = int((t1 - t0) * SR) + SR
    stem = np.zeros((n, 2), np.float32)
    last = {}
    used = 0
    missing = set()
    for (tc, kind, gain) in story.cues:
        if kind not in BANK: continue
        ts = story.song_time(tc)
        if ts < t0 - 0.05 or ts > t1: continue
        if kind in ("whoosh", "dodge") and ts - last.get(kind, -9) < 0.09: continue   # thin out machine-gun whooshes
        last[kind] = ts
        files = files_for(lib, kind)
        if not files:
            missing.add(kind); continue
        base, rate, mx = BANK[kind]
        f = files[int(hashlib.md5(f"{tc:.3f}{kind}".encode()).hexdigest(), 16) % len(files)]
        a = load(f, rate)[: int(mx * SR)]
        fade = min(len(a), int(0.08 * SR))
        if fade > 1:
            a = a.copy(); a[-fade:] *= np.linspace(1, 0, fade)[:, None]
        g = 10 ** ((base + gain) / 20)
        i = int((ts - t0) * SR)
        if i < 0: a = a[-i:]; i = 0
        j = min(n, i + len(a))
        stem[i:j] += a[: j - i] * g
        used += 1
    # ambient beds, looped with fades
    for (a0, a1, kind, gain) in getattr(story, "ambs", []):
        if kind not in AMB: continue
        files = files_for(lib, "ambience/" + kind)
        if not files:
            missing.add("ambience/" + kind); continue
        base, rate = AMB[kind]
        s0, s1 = max(t0, story.song_time(a0)), min(t1, story.song_time(a1))
        if s1 <= s0: continue
        loop = load(files[0], rate)
        L = int((s1 - s0) * SR)
        reps = int(np.ceil(L / len(loop))) + 1
        off = int(hashlib.md5(f"{a0:.2f}{kind}".encode()).hexdigest(), 16) % len(loop)
        seg = np.concatenate([loop] * reps)[off: off + L].copy()
        fd = min(L // 2, int(1.2 * SR))
        if fd > 1:
            seg[:fd] *= np.linspace(0, 1, fd)[:, None]; seg[-fd:] *= np.linspace(1, 0, fd)[:, None]
        i = int((s0 - t0) * SR)
        j = min(n, i + L)
        stem[i:j] += seg[: j - i] * 10 ** ((base + gain) / 20)
    # gentle bus limiter so stacked hits never clip
    stem = np.tanh(stem * 1.1) / 1.1
    if out:
        raw = (np.clip(stem, -1, 1) * 32767).astype(np.int16).tobytes()
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-", out],
                       input=raw, check=True)
    print(f"sfx: {used} cues placed from {lib}")
    if missing:
        print("sfx: no files for: " + ", ".join(sorted(missing)) + " (those cues were skipped)")
    return stem


def check(lib=None):
    lib = library(lib)
    print("sound library:", lib)
    for kind in list(BANK) + ["ambience/" + k for k in AMB]:
        n = len(files_for(lib, kind))
        print(f"  {kind:<20} {n} file(s)" if n else f"  {kind:<20} -- none")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("story", nargs="?"); ap.add_argument("out", nargs="?")
    ap.add_argument("--from", dest="t0", type=float, default=0.0); ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--lib", default=None, help="sound library folder (default: $STICKFIGHT_SFX_LIB or ./sfx_library)")
    ap.add_argument("--check", action="store_true", help="list which cue kinds have sound files, then exit")
    a = ap.parse_args()
    if a.check or not a.story:
        check(a.lib); sys.exit(0)
    if not a.out:
        ap.error("give an output .wav path")
    import render
    st = render.load_story(a.story, 30, 1920, 1080, False)
    build(st, a.t0, a.t1, a.out, a.lib)
