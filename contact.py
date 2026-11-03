"""contact.py - contact sheet for QA.
  python contact.py DIR_OF_PNGS out.png            (tiles every png, labelled by file name)
  python contact.py VIDEO.mp4 out.png [--n 12] [--times 1,2,3]   (grabs frames with ffmpeg)
"""
import sys, os, glob, subprocess, tempfile, argparse
from PIL import Image, ImageDraw, ImageFont

def tile(items, out, cols=3, w=640):
    ims = []
    for path, label in items:
        im = Image.open(path).convert("RGB"); h = int(im.height * w / im.width); im = im.resize((w, h), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        f = None
        for fp in ("C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
            try: f = ImageFont.truetype(fp, 20); break
            except Exception: pass
        if f is None: f = ImageFont.load_default()
        d.rectangle([0, 0, 150, 28], fill=(0, 0, 0)); d.text((6, 3), label, fill=(255, 255, 0), font=f)
        ims.append(im)
    rows = (len(ims) + cols - 1) // cols
    H = ims[0].height
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 4, rows * H + (rows - 1) * 4), (40, 40, 40))
    for i, im in enumerate(ims):
        r, c = divmod(i, cols); sheet.paste(im, (c * (w + 4), r * (H + 4)))
    sheet.save(out); print("wrote", out, sheet.size)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--n", type=int, default=12); ap.add_argument("--times"); ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--w", type=int, default=640)
    a = ap.parse_args()
    if os.path.isdir(a.src):
        fs = sorted(glob.glob(os.path.join(a.src, "*.png")))
        tile([(f, os.path.splitext(os.path.basename(f))[0].replace("still_", "t=")) for f in fs], a.out, a.cols, a.w)
    else:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.src],
                                   capture_output=True, text=True).stdout)
        ts = [float(x) for x in a.times.split(",")] if a.times else [dur * (i + 0.5) / a.n for i in range(a.n)]
        tmp = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(a.out)))
        items = []
        for i, t in enumerate(ts):
            p = os.path.join(tmp, f"f{i:02d}.png")
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", a.src, "-frames:v", "1", p], check=True)
            items.append((p, f"t={t:.1f}s"))
        tile(items, a.out, a.cols, a.w)
