#!/usr/bin/env python3
"""Build Counter Zombie Mobile spray logos (player sprays).

Output: 3rdparty/czm_project/logos/czm_*.png (96x96 RGBA, transparent background).
The engine turns the chosen PNG into tempdecal.wad for GoldSrc servers
(cl_spray.c), 96x96 already fits its size limit. Photo sprays come from the
owner's art in assets/branding/, the others are drawn here.
Also writes a preview strip of all sprays to the path given with --preview.
"""
import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "assets/branding"
OUTPUT = ROOT / "3rdparty/czm_project/logos"
FONTS = ROOT / "3rdparty/czm_project/gfx/fonts/czm"
SIZE = 96
SS = 4  # supersampling
S = SIZE * SS

RED = (230, 30, 30, 255)
DARK = (14, 14, 18, 255)
WHITE = (255, 255, 255, 255)
TOXIC = (164, 230, 30, 255)


def finish(big):
    return big.resize((SIZE, SIZE), Image.LANCZOS)


def circle_mask(size, inset=0):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse([inset, inset, size - 1 - inset, size - 1 - inset], fill=255)
    return m


def sticker(image, ring=WHITE):
    """Round photo sticker with a light ring and a thin dark edge."""
    big = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    edge = int(S * 0.035)
    ring_w = int(S * 0.055)
    d = ImageDraw.Draw(big)
    d.ellipse([0, 0, S - 1, S - 1], fill=DARK)
    d.ellipse([edge, edge, S - 1 - edge, S - 1 - edge], fill=ring)
    inner = edge + ring_w
    photo = image.convert("RGBA").resize((S - inner * 2, S - inner * 2), Image.LANCZOS)
    big.paste(photo, (inner, inner), circle_mask(S - inner * 2))
    return finish(big)


def photo(name, cx, cy, r, ring=WHITE):
    art = Image.open(SOURCES / name).convert("RGB")
    return sticker(art.crop((cx - r, cy - r, cx + r, cy + r)), ring)


def logo():
    art = Image.open(SOURCES / "counter-zombie-mobile-original.jpg").convert("RGB")
    return sticker(art, RED)


def outlined(shape_mask, fill, outline=DARK, width=0.045):
    """Fill a mask with a colour and put a dark outline around it."""
    w = max(1, int(S * width))
    grown = shape_mask.filter(ImageFilter.MaxFilter(w * 2 + 1))
    big = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    big.paste(outline, (0, 0), grown)
    big.paste(fill, (0, 0), shape_mask)
    return big


def biohazard():
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    c = S / 2
    z = 1.2  # symbol scale
    for k in range(3):
        a = math.radians(-90 + k * 120)
        ox, oy = c + math.cos(a) * S * 0.17 * z, c + math.sin(a) * S * 0.17 * z
        r = S * 0.215 * z
        d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=255)
    for k in range(3):
        # hollow of every crescent
        a = math.radians(-90 + k * 120)
        ox, oy = c + math.cos(a) * S * 0.235 * z, c + math.sin(a) * S * 0.235 * z
        r = S * 0.15 * z
        d.ellipse([ox - r, oy - r, ox + r, oy + r], fill=0)
    # ring through the middle
    r1, r2 = S * 0.19 * z, S * 0.145 * z
    d.ellipse([c - r1, c - r1, c + r1, c + r1], outline=255, width=int(r1 - r2))
    # gaps of the ring and the centre hole
    for k in range(3):
        a = math.radians(-90 + k * 120)
        x2, y2 = c + math.cos(a) * S * 0.30 * z, c + math.sin(a) * S * 0.30 * z
        d.line([c, c, x2, y2], fill=0, width=int(S * 0.035 * z))
    r = S * 0.06 * z
    d.ellipse([c - r, c - r, c + r, c + r], fill=0)
    return finish(outlined(m, TOXIC))


def skull():
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    d.ellipse([S * .16, S * .08, S * .84, S * .70], fill=255)
    d.rounded_rectangle([S * .30, S * .52, S * .70, S * .88], radius=S * .08, fill=255)
    holes = Image.new("L", (S, S), 0)
    h = ImageDraw.Draw(holes)
    h.ellipse([S * .26, S * .34, S * .46, S * .54], fill=255)
    h.ellipse([S * .54, S * .34, S * .74, S * .54], fill=255)
    h.polygon([(S * .50, S * .56), (S * .44, S * .67), (S * .56, S * .67)], fill=255)
    for x in (0.40, 0.50, 0.60):
        h.line([S * x, S * .74, S * x, S * .88], fill=255, width=int(S * .03))
    shape = Image.composite(Image.new("L", (S, S), 0), m, holes)
    big = outlined(shape, (236, 232, 222, 255))
    # glowing red eyes
    eyes = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    e = ImageDraw.Draw(eyes)
    for x0 in (0.31, 0.59):
        e.ellipse([S * x0, S * .39, S * (x0 + .10), S * .49], fill=RED)
    big.alpha_composite(eyes.filter(ImageFilter.GaussianBlur(S * 0.01)))
    return finish(big)


def claws():
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    for k in range(3):
        x = S * (0.24 + k * 0.20)
        top, bottom = S * 0.10, S * 0.90
        # slanted slash, thick in the middle and sharp at both ends
        pts = []
        for i in range(21):
            t = i / 20
            w = S * 0.075 * math.sin(math.pi * t)
            px = x + (t - 0.5) * S * 0.22
            py = top + (bottom - top) * t
            pts.append((px - w, py))
        for i in range(20, -1, -1):
            t = i / 20
            w = S * 0.075 * math.sin(math.pi * t)
            px = x + (t - 0.5) * S * 0.22
            py = top + (bottom - top) * t
            pts.append((px + w, py))
        d.polygon(pts, fill=255)
    return finish(outlined(m, RED))


def text_spray(text, font_file, fill, size=0.62, drip=False):
    font = ImageFont.truetype(str(FONTS / font_file), int(S * size))
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    x, y = (S - w) / 2 - box[0], (S - h) / 2 - box[1] - (S * 0.05 if drip else 0)
    d.text((x, y), text, font=font, fill=255)
    if drip:
        # paint drips under the letters
        for fx, length in ((0.24, 0.20), (0.43, 0.30), (0.62, 0.16), (0.78, 0.26)):
            px = S * fx
            top = y + box[3] - S * 0.04
            d.rounded_rectangle([px - S * 0.025, top, px + S * 0.025, top + S * length], radius=S * 0.025, fill=255)
            d.ellipse([px - S * 0.04, top + S * length - S * 0.05, px + S * 0.04, top + S * length + S * 0.03], fill=255)
    return finish(outlined(m, fill, width=0.05))


SPRAYS = {
    "czm_logo": logo,
    "czm_zombie": lambda: photo("menu-background.png", 956, 680, 150),
    "czm_hunter": lambda: photo("menu-background.png", 170, 565, 115),
    "czm_soldier": lambda: photo("menu-background.png", 865, 205, 125),
    "czm_biohazard": biohazard,
    "czm_skull": skull,
    "czm_claws": claws,
    "czm_gg": lambda: text_spray("GG", "InterDisplay-BlackItalic.otf", RED),
    "czm_zm": lambda: text_spray("ZM", "InterDisplay-Black.otf", (40, 200, 60, 255), 0.56, drip=True),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    images = []
    for name, make in SPRAYS.items():
        image = make()
        path = OUTPUT / f"{name}.png"
        image.save(path, "PNG", optimize=True)
        images.append(image)
        print(path.relative_to(ROOT), image.size, path.stat().st_size, "bytes")
    if args.preview:
        strip = Image.new("RGBA", (len(images) * (SIZE * 2 + 8), SIZE * 2 + 8), (70, 74, 82, 255))
        for i, image in enumerate(images):
            strip.alpha_composite(image.resize((SIZE * 2, SIZE * 2), Image.NEAREST), (i * (SIZE * 2 + 8) + 4, 4))
        strip.save(args.preview)


if __name__ == "__main__":
    main()
