#!/usr/bin/env python3
"""Build the player avatars of Counter Zombie Mobile from the kontra project art.

gfx/czm/avatars/avatar_NN.png: round, 192 px, a red ring like the game logo avatar,
256 colours with transparency to keep the APK small. The player's own photo gets
the same look on the phone (AvatarPickerActivity.java).

usage: make_czm_avatars.py <kontra checkout>   (needs Pillow; the output is committed)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "3rdparty/czm_project/gfx/czm/avatars"
SIZE, SS = 192, 4
RING = (255, 59, 47, 255)


def make(src, dst):
    big = SIZE * SS
    img = Image.open(src).convert("RGBA").resize((big, big), Image.LANCZOS)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, big - 1, big - 1], fill=255)
    img.putalpha(mask)
    ring = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    width = 7 * SS
    ImageDraw.Draw(ring).ellipse([width // 2, width // 2, big - 1 - width // 2, big - 1 - width // 2], outline=RING, width=width)
    img = Image.alpha_composite(img, ring).resize((SIZE, SIZE), Image.LANCZOS)
    img.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(dst, "PNG", optimize=True)
    return dst.stat().st_size


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1]) / "assets/avatars"
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for i in range(1, 11):
        total += make(src / f"avatar-{i:02d}.webp", OUT / f"avatar_{i:02d}.png")
    print("10 avatars,", total // 1024, "KB in", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
