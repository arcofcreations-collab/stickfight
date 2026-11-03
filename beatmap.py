"""beatmap.py - fast numpy-only beat grid + section map for a song.

Usage: python beatmap.py song.(mp3|wav) out.json [--survey]
Decodes with ffmpeg, computes spectral-flux onset envelope, global tempo
(autocorrelation), a fixed beat grid phased to the onsets, downbeats (bar
phase from low-end onsets), per-bar energy and a novelty curve for sections.
Most produced songs keep a steady tempo, so a fixed grid is tighter than a
tracked one and makes cuts land exactly.
"""
import sys, json, subprocess, numpy as np

SR = 22050; N = 2048; HOP = 256

def decode(path):
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0

def stft_mag(y):
    nfr = 1 + (len(y) - N) // HOP
    idx = np.arange(N)[None, :] + HOP * np.arange(nfr)[:, None]
    win = np.hanning(N).astype(np.float32)
    out = np.empty((nfr, N // 2 + 1), np.float32)
    for s in range(0, nfr, 4000):
        out[s:s + 4000] = np.abs(np.fft.rfft(y[idx[s:s + 4000]] * win, axis=1))
    return out

def bands(mag):
    f = np.fft.rfftfreq(N, 1 / SR)
    ei = np.unique(np.round(np.geomspace(3, len(f) - 1, 48)).astype(int))[:41]
    B = np.stack([mag[:, a:b].mean(1) for a, b in zip(ei[:-1], ei[1:])], 1)
    return np.log1p(100 * B), f

def analyse(path):
    y = decode(path)
    mag = stft_mag(y)
    L, f = bands(mag)
    flux = np.maximum(0, np.diff(L, axis=0, prepend=L[:1]))
    onset = flux.sum(1); low = flux[:, :10].sum(1)            # kick region (<~120 Hz)
    def norm(x):
        x = x - np.convolve(x, np.ones(64) / 64, "same"); x = np.maximum(x, 0); return x / (x.max() + 1e-9)
    onset, low = norm(onset), norm(low)
    fps = SR / HOP
    # tempo via autocorrelation, 70-180 bpm, prefer 90-160
    ac = np.correlate(onset, onset, "full")[len(onset) - 1:]
    lags = np.arange(len(ac)); bpm = 60 * fps / np.maximum(lags, 1)
    m = (bpm > 70) & (bpm < 180)
    w = np.exp(-0.5 * (np.log2(bpm / 125) / 0.6) ** 2)
    best = lags[m][np.argmax((ac * w)[m])]
    # refine period with fine search
    cands = np.linspace(best - 1.5, best + 1.5, 301)
    t = np.arange(len(onset))
    def score(P, ph): 
        k = np.arange(ph, len(onset) - 1, P); return np.interp(k, t, onset).sum()
    sc = [max(score(P, ph) for ph in np.linspace(0, P, 24, endpoint=False)) for P in cands]
    P = cands[int(np.argmax(sc))]
    phs = np.linspace(0, P, 96, endpoint=False)
    ph = phs[int(np.argmax([score(P, p) for p in phs]))]
    beats = np.arange(ph, len(onset) - 1, P) / fps
    # downbeat phase: which of 4 offsets carries most kick
    bf = (beats * fps).astype(int)
    kick = np.array([low[max(0, b - 2):b + 3].max() for b in bf])
    en_rms = np.sqrt(np.convolve(y ** 2, np.ones(HOP) / HOP, "same")[::HOP])
    loud = np.array([en_rms[b:b + int(P)].mean() for b in bf])
    off = int(np.argmax([kick[o::4].mean() for o in range(4)]))
    downs = beats[off::4]
    # per-bar features
    bars = []
    for i, t0 in enumerate(downs):
        t1 = downs[i + 1] if i + 1 < len(downs) else len(y) / SR
        a, b = int(t0 * fps), int(t1 * fps)
        if b <= a: continue
        bars.append(dict(t=round(float(t0), 4), rms=float(en_rms[a:b].mean()), onset=float(onset[a:b].mean()),
                         kick=float(low[a:b].mean()), bright=float((L[a:b, 28:].mean())),
                         timbre=L[a:b].mean(0).round(3).tolist()))
    # novelty between consecutive 4-bar blocks of timbre
    T = np.array([b["timbre"] for b in bars]); nov = [0.0]
    for i in range(1, len(T)):
        A = T[max(0, i - 4):i].mean(0); Bm = T[i:i + 4].mean(0)
        nov.append(float(np.linalg.norm(A - Bm)))
    for b, n in zip(bars, nov): b["novelty"] = round(n, 3); b.pop("timbre")
    # strong onsets (hits) for accents
    pk = [i for i in range(2, len(onset) - 2) if onset[i] > 0.35 and onset[i] == onset[i - 2:i + 3].max()]
    return dict(path=path, duration=len(y) / SR, bpm=60 * fps / P, beat_period=P / fps, beats=beats.round(4).tolist(),
                downbeats=downs.round(4).tolist(), downbeat_offset=off, bars=bars,
                hits=[round(i / fps, 4) for i in pk], beat_loud=loud.round(4).tolist())

if __name__ == "__main__":
    r = analyse(sys.argv[1])
    if "--survey" in sys.argv:
        rm = np.array([b["rms"] for b in r["bars"]]); mx = rm.max()
        prof = "".join(" .:-=+*#%@"[min(9, int(9 * v / mx))] for v in rm)
        on = np.mean([b["onset"] for b in r["bars"]])
        print(f"bpm={r['bpm']:6.1f} dur={r['duration']:5.1f} onset={on:.3f} rms={rm.mean():.3f} top25%={np.mean(rm>0.75*mx):.2f} |{prof}|")
    else:
        json.dump(r, open(sys.argv[2], "w"), indent=0)
        print("bpm", round(r["bpm"], 2), "beats", len(r["beats"]), "bars", len(r["bars"]))
