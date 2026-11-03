"""make_sample_audio.py - write a self-made sample track and a starter sound-effects set. Pure numpy, no downloads.

  python tools/make_sample_audio.py            -> samples/sample_track.wav  (120 bpm, 48 s)
                                                  sfx_library/<kind>/synth_*.wav  (starter SFX)
  python tools/make_sample_audio.py --track-only | --sfx-only

Everything here is synthesised from scratch by this script, so you can use the output however you like (MIT,
like the rest of the repo). It is a placeholder: the engine looks far better cut to a real song, and the SFX
stem sounds better with real recordings (see the README, "Sound").
"""
import argparse, os, wave
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 44100
rng = np.random.default_rng(7)


def write_wav(path, x):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.asarray(x, np.float32)
    if x.ndim == 1: x = np.stack([x, x], 1)
    pk = np.abs(x).max() or 1.0
    x = x / pk * 0.89
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def env(n, a=0.002, d=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)


def lowpass(x, k):
    k = max(1, int(k)); return np.convolve(x, np.ones(k) / k, "same")


def kick(n=int(0.45 * SR)):
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t / 0.03)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.16)


def snare(n=int(0.3 * SR)):
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 190 * t) * env(n, 0.001, 0.05)
    noise = (rng.standard_normal(n) - lowpass(rng.standard_normal(n), 8)) * env(n, 0.001, 0.09)
    return 0.6 * body + 0.8 * noise


def hat(n=int(0.06 * SR)):
    x = rng.standard_normal(n); x = x - lowpass(x, 3)
    return x * env(n, 0.0005, 0.018) * 0.35


def track(bpm=120, bars=24):
    beat = 60 / bpm; n = int((bars * 4 * beat + 2) * SR)
    out = np.zeros(n)
    def put(sig, t, g=1.0):
        i = int(t * SR); j = min(n, i + len(sig)); out[i:j] += sig[: j - i] * g
    roots = [55.0, 55.0, 43.65, 49.0]          # A, A, F, G (bass, Hz)
    for bar in range(bars):
        sec = "intro" if bar < 4 else "build" if bar < 12 else "drop" if bar < 20 else "outro"
        root = roots[bar % 4]
        for b in range(4):
            t = (bar * 4 + b) * beat
            if sec in ("build", "drop") or (sec == "outro" and b == 0): put(kick(), t, 1.0)
            if sec == "drop" and b in (1, 3): put(snare(), t, 0.7)
            if sec == "build" and bar >= 8 and b == 3: put(snare(), t, 0.4)
            for h in range(2 if sec != "drop" else 4):
                put(hat(), t + h * beat / (2 if sec != "drop" else 4), 0.5 if sec != "intro" else 0.3)
            if sec in ("build", "drop"):                     # bass on every beat, octave pop on the off-beat
                m = int(beat * 0.9 * SR); tt = np.arange(m) / SR
                saw = 2 * ((tt * root) % 1) - 1
                put(lowpass(saw, 6) * env(m, 0.005, 0.25), t, 0.45)
                if sec == "drop":
                    put(np.sin(2 * np.pi * root * 2 * tt[: m // 2]) * env(m // 2, 0.003, 0.08), t + beat / 2, 0.3)
        # pad: a slow chord swell each bar
        m = int(4 * beat * SR); tt = np.arange(m) / SR
        chord = sum(np.sin(2 * np.pi * root * 4 * r * tt + k) for k, r in enumerate((1, 1.26, 1.5)))
        sw = np.sin(np.pi * np.arange(m) / m) ** 2
        put(chord * sw * (0.06 if sec != "drop" else 0.04), bar * 4 * beat)
    fade = int(2 * SR); out[-fade:] *= np.linspace(1, 0, fade)
    return out


def noise_sweep(dur, f0, f1, d):
    n = int(dur * SR); x = rng.standard_normal(n)
    k = np.linspace(SR / f0, SR / f1, n).astype(int)
    y = np.array([x[max(0, i - k[i]):i + 1].mean() for i in range(0, n)]) if n < 20000 else lowpass(x, (SR / f0 + SR / f1) / 2)
    return y * np.sin(np.pi * np.arange(n) / n) ** d


def metal(dur, base, decay):
    n = int(dur * SR); t = np.arange(n) / SR
    parts = [1, 2.76, 5.40, 8.93, 13.3]
    x = sum(np.sin(2 * np.pi * base * p * t + i) / (i + 1) for i, p in enumerate(parts))
    click = rng.standard_normal(n) * env(n, 0.0005, 0.01)
    return (x * env(n, 0.001, decay) + click) * 0.6


def thump(dur, f0, f1, decay):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.04)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, decay)


def sfx_set():
    out = {}
    for i in range(3):
        out[f"whoosh/synth_whoosh_{i}.wav"] = noise_sweep(0.35 + 0.05 * i, 900 + 300 * i, 3000, 2)
    out["swoosh_big/synth_swoosh_big.wav"] = noise_sweep(0.9, 300, 2500, 1.5)
    out["dodge/synth_dodge.wav"] = noise_sweep(0.3, 1500, 4000, 3) * 0.6
    for i in range(3):
        n = int(0.4 * SR)
        out[f"hit/synth_hit_{i}.wav"] = thump(0.4, 220, 70 + 10 * i, 0.09) + rng.standard_normal(n) * env(n, 0.0005, 0.04) * 0.7
        out[f"punch/synth_punch_{i}.wav"] = thump(0.3, 180, 60, 0.07) + rng.standard_normal(int(0.3 * SR)) * env(int(0.3 * SR), 0.0005, 0.02) * 0.5
    for i in range(3):
        out[f"clash/synth_clash_{i}.wav"] = metal(0.9, 520 + 60 * i, 0.25)
    out["clash_big/synth_clash_big.wav"] = metal(1.8, 330, 0.7) + thump(1.8, 120, 40, 0.3)
    out["thud/synth_thud.wav"] = thump(0.6, 120, 40, 0.15)
    out["boom/synth_boom.wav"] = thump(2.0, 90, 28, 0.6) + lowpass(rng.standard_normal(int(2 * SR)), 40) * env(int(2 * SR), 0.01, 0.5) * 3
    out["draw/synth_draw.wav"] = metal(1.0, 1400, 0.4) * 0.4 + noise_sweep(1.0, 2000, 6000, 1) * 0.5
    out["scrape/synth_scrape.wav"] = noise_sweep(1.0, 2500, 5000, 0.5) * (1 + 0.5 * np.sin(np.arange(SR) / SR * 2 * np.pi * 30))
    out["rumble/synth_rumble.wav"] = lowpass(rng.standard_normal(int(3 * SR)), 120) * np.sin(np.pi * np.arange(int(3 * SR)) / (3 * SR))
    out["power/synth_power.wav"] = noise_sweep(2.0, 200, 1200, 0.5) + thump(2.0, 60, 40, 1.0) * 0.5
    out["bell/synth_bell.wav"] = metal(4.0, 220, 1.6)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--track-only", action="store_true"); ap.add_argument("--sfx-only", action="store_true")
    a = ap.parse_args()
    if not a.sfx_only:
        p = os.path.join(ROOT, "samples", "sample_track.wav"); write_wav(p, track()); print("wrote", p)
    if not a.track_only:
        sounds = sfx_set()
        for rel, x in sounds.items():
            write_wav(os.path.join(ROOT, "sfx_library", *rel.split("/")), x)
        print("wrote", len(sounds), "starter sounds to", os.path.join(ROOT, "sfx_library"))
