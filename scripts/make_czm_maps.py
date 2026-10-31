#!/usr/bin/env python3
"""Build map pictures for the Counter Zombie Mobile server list.

gfx/czm/maps/<map>.png    previews of zombie maps (from the kontra project art)
gfx/czm/maps/_<mode>.png  pictures for maps without a preview: zombie, escape, classic, other

Standard maps use their overview from the game data at runtime, nothing is stored for them.
The previews carry a "MOD" mark in the top right corner, the right edge is cut off.
Pictures are 256-colour PNGs to keep the APK small.

usage: make_czm_maps.py <kontra checkout>   (needs Pillow; the output is committed)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "assets/branding"
OUT = ROOT / "3rdparty/czm_project/gfx/czm/maps"
W, H = 400, 182  # 2.2:1, the menu crops to its own boxes


def save(img, name):
    img = img.convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    path = OUT / name
    img.save(path, "PNG", optimize=True)
    return path.stat().st_size


def cover(img, w, h, cx=0.5, cy=0.5):
    s = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x = int((img.width - w) * cx)
    y = int((img.height - h) * cy)
    return img.crop((x, y, x + w, y + h))


def pattern(top, bottom, stripe):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    for x in range(-H, W, 22):
        d.line([(x, H), (x + H, 0)], fill=stripe, width=6)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    maps = Path(sys.argv[1]) / "assets/maps"
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    names = []
    for src in sorted(maps.glob("*.webp")):
        img = Image.open(src).convert("RGB")
        img = img.crop((0, 0, int(img.width * 0.85), img.height))
        total += save(cover(img, W, H), src.stem.lower() + ".png")
        names.append(src.stem.lower())
    total += save(cover(Image.open(ART / "loading-4.png").convert("RGB"), W, H, 0.62, 0.55), "_zombie.png")
    total += save(cover(Image.open(ART / "loading-5.png").convert("RGB"), W, H, 0.75, 0.45), "_escape.png")
    total += save(pattern((32, 44, 66), (10, 14, 22), (40, 54, 80)), "_classic.png")
    total += save(pattern((46, 30, 66), (12, 10, 20), (58, 40, 82)), "_other.png")
    print(len(names) + 4, "pictures,", total // 1024, "KB in", OUT.relative_to(ROOT))
    print("maps with previews (keep czm/menu/CzmServers.cpp in sync):")
    print(", ".join(f'"{n}"' for n in names))


if __name__ == "__main__":
    main()
