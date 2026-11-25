"""Turns one still image into a 9:16 reel: slow camera move, weather
particles, glow, text and music. Pure Python + ffmpeg, free.
"""
import glob
import math
import os
import random
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FPS = 30
SECONDS = 10
N = FPS * SECONDS
HANDLE = os.environ.get("IG_HANDLE", "@funtoonia.official")


def _font(size, bold=True):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


class Particles:
    def __init__(self, kind):
        self.kind = kind
        n = {"rain": 260, "snow": 140, "petals": 45, "sparkles": 60,
             "fireflies": 40}.get(kind, 0)
        self.p = [[random.uniform(0, W), random.uniform(0, H),
                   random.uniform(0.6, 1.4), random.uniform(0, 6.28)]
                  for _ in range(n)]

    def draw(self, layer: Image.Image, t: int):
        d = ImageDraw.Draw(layer)
        for q in self.p:
            x, y, s, ph = q
            if self.kind == "rain":
                q[1] = (y + 42 * s) % H
                q[0] = (x - 6 * s) % W
                d.line([(x, y), (x - 7 * s, y + 38 * s)],
                       fill=(210, 225, 255, int(70 * s)), width=2)
            elif self.kind == "snow":
                q[1] = (y + 3 * s) % H
                q[0] = (x + math.sin(t / 20 + ph) * 1.5) % W
                r = 3 * s + 1
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 200))
            elif self.kind == "petals":
                q[1] = (y + 2.5 * s) % H
                q[0] = (x + 1.8 * s + math.sin(t / 15 + ph) * 2) % W
                r = 7 * s
                d.ellipse([x - r, y - r / 2, x + r, y + r / 2],
                          fill=(255, 183, 213, 210))
            elif self.kind in ("sparkles", "fireflies"):
                a = (math.sin(t / 9 + ph) + 1) / 2
                q[1] = (y - 0.6 * s) % H
                q[0] = (x + math.sin(t / 25 + ph) * 0.8) % W
                col = (255, 236, 150) if self.kind == "fireflies" else (255, 255, 255)
                r = 3 * s + 2 * a
                d.ellipse([x - r, y - r, x + r, y + r], fill=col + (int(220 * a),))


def _wrap_box(img, text, font, top, label=None, label_color=(255, 196, 64)):
    d = ImageDraw.Draw(img)
    lines = textwrap.wrap(text, width=24)
    lh = font.size + 14
    box_h = lh * len(lines) + 60 + (70 if label else 0)
    x0, x1 = 70, W - 70
    d.rounded_rectangle([x0, top, x1, top + box_h], radius=36,
                        fill=(10, 18, 38, 200))
    y = top + 30
    if label:
        lf = _font(38)
        d.text((x0 + 40, y), label, font=lf, fill=label_color)
        y += 70
    for ln in lines:
        wtxt = d.textlength(ln, font=font)
        d.text(((W - wtxt) / 2, y), ln, font=font, fill=(255, 255, 255))
        y += lh


def _overlay(content, t):
    """Text layer for frame t (RGBA)."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mode, text = content["mode"], (content.get("overlay_text") or "").strip()
    fade = min(1.0, max(0.0, (t - 12) / 15))  # text fades in after ~0.4s
    if text and fade > 0:
        if mode == "funny":
            _wrap_box(layer, text, _font(62), 260)
        elif mode == "news":
            _wrap_box(layer, text, _font(56), 240, label="TODAY IN THE WORLD")
        else:
            f = _font(56)
            d = ImageDraw.Draw(layer)
            lines = textwrap.wrap(text, width=26)
            y = 1300
            for ln in lines:
                wtxt = d.textlength(ln, font=f)
                d.text(((W - wtxt) / 2 + 3, y + 3), ln, font=f, fill=(0, 0, 0, 160))
                d.text(((W - wtxt) / 2, y), ln, font=f, fill=(255, 255, 255, 255))
                y += 72
        if fade < 1:
            a = layer.getchannel("A").point(lambda v: int(v * fade))
            layer.putalpha(a)
    d = ImageDraw.Draw(layer)
    if mode == "news" and content.get("source"):
        sf = _font(34, bold=False)
        d.text((80, 1540), f"Source: {content['source']}", font=sf,
               fill=(255, 255, 255, 220))
    hf = _font(32)
    d.text((W - 80 - d.textlength(HANDLE, font=hf), 1590), HANDLE, font=hf,
           fill=(255, 255, 255, 170))
    return layer


def _vignette():
    v = Image.new("L", (W, H), 0)
    ImageDraw.Draw(v).ellipse([-300, -200, W + 300, H + 200], fill=255)
    v = v.filter(ImageFilter.GaussianBlur(220))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 150))
    dark.putalpha(v.point(lambda p: 150 - int(p * 150 / 255)))
    return dark


def _audio(mode, weather, out):
    tracks = glob.glob(f"music/{mode}/*.mp3") + glob.glob(f"music/{mode}/*.m4a")
    if tracks:
        src = random.choice(tracks)
        try:  # start somewhere in the catchy middle, not the quiet intro
            dur = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", src], capture_output=True, text=True).stdout)
            start = random.uniform(min(8, dur / 4), max(min(8, dur / 4), dur - SECONDS - 8))
        except ValueError:
            start = 0
        print(f"music: {src} from {start:.0f}s")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}",
                        "-i", src, "-t",
                        str(SECONDS), "-af",
                        f"afade=in:d=1,afade=out:st={SECONDS-1.5}:d=1.5,volume=0.8",
                        "-ac", "2", "-ar", "44100", out], check=True)
        return out
    # no music files added: compose an original, copyright-free track
    from music import compose
    wav = out + ".wav"
    compose(mode, SECONDS, wav, weather)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                    "-ac", "2", "-ar", "44100", out], check=True)
    os.remove(wav)
    return out


def render(image_path, content, out_path):
    base = Image.open(image_path).convert("RGB")
    # cover-fit to 12% larger than the frame so the camera can move
    scale = max(W * 1.12 / base.width, H * 1.12 / base.height)
    big = base.resize((int(base.width * scale), int(base.height * scale)),
                      Image.LANCZOS)
    weather = content.get("weather", "none")
    parts = Particles(weather)
    vig = _vignette()
    pan = random.choice([(-1, 0), (1, 0), (0, -1), (0, 1)])
    silent = out_path + ".video.mp4"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", silent],
        stdin=subprocess.PIPE)
    for t in range(N):
        k = t / (N - 1)
        ease = 0.5 - 0.5 * math.cos(math.pi * k)
        zoom = 1.0 + 0.07 * ease
        cw, ch = W * 1.12 / zoom, H * 1.12 / zoom
        cx = big.width / 2 + pan[0] * 40 * ease
        cy = big.height / 2 + pan[1] * 60 * ease
        x0 = min(max(0.0, cx - cw / 2), big.width - cw)
        y0 = min(max(0.0, cy - ch / 2), big.height - ch)
        box = (max(0.0, x0), max(0.0, y0), min(big.width, x0 + cw), min(big.height, y0 + ch))
        frame = big.resize((W, H), Image.BILINEAR, box=box).convert("RGBA")
        # gentle "breathing" warm light
        glow = 0.04 * math.sin(t / 22)
        if glow:
            frame = Image.blend(frame, Image.new("RGBA", (W, H), (255, 200, 120, 255)),
                                max(0.0, glow))
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        parts.draw(fx, t)
        frame = Image.alpha_composite(frame, fx)
        frame = Image.alpha_composite(frame, vig)
        frame = Image.alpha_composite(frame, _overlay(content, t))
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    audio = _audio(content["mode"], weather, out_path + ".m4a")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", audio,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                    "-movflags", "+faststart", out_path], check=True)
    for f in (silent, audio):
        os.remove(f)
    return out_path
