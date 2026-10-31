#!/usr/bin/env python3
"""Build Counter Zombie Mobile menu and loading-screen textures.

Sources live in assets/branding/ (owner-supplied art) and the Inter fonts
shipped in 3rdparty/czm_project/gfx/fonts/czm/. The generated files are
committed to 3rdparty/czm_project/gfx/czm/, so the Android build does not
need Pillow. Re-run this script after replacing any source picture.
"""
import argparse
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "assets/branding"
EXTRAS = ROOT / "3rdparty/czm_project"
FONTS = EXTRAS / "gfx/fonts/czm"
OUTPUT = EXTRAS / "gfx/czm"

BACKGROUNDS = {
    "menu_bg.png": "menu-background.png",
    "loading_1.png": "loading-1.png",
    "loading_2.png": "loading-2.png",
    "loading_3.png": "loading-3.png",
    "loading_4.png": "loading-4.png",
    "loading_5.png": "loading-5.png",
}


def engine_compatible_png(path):
    """8-bit RGB/RGBA, non-interlaced PNG can be used by the engine without re-encoding."""
    data = path.read_bytes()[:33]
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return False
    bit_depth, color_type, interlace = data[24], data[25], data[28]
    return bit_depth == 8 and color_type in (2, 6) and interlace == 0


def save_png(image, path):
    # Plain 8-bit, non-interlaced PNG: the engine image loader supports exactly this.
    image.save(path, "PNG", optimize=True)
    print(path.relative_to(ROOT), image.size, path.stat().st_size, "bytes")


def tracked_text(draw, xy, text, font, fill, tracking):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x


def tracked_width(draw, text, font, tracking):
    return sum(draw.textlength(ch, font=font) + tracking for ch in text) - tracking


def make_title(path):
    black = ImageFont.truetype(str(FONTS / "InterDisplay-Black.otf"), 170)
    bold = ImageFont.truetype(str(FONTS / "InterDisplay-Bold.otf"), 64)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    word1, word2 = "COUNTER ", "ZOMBIE"
    line2 = "MOBILE · 32 PLAYERS"
    w1 = probe.textlength(word1, font=black)
    w2 = probe.textlength(word2, font=black)
    tracking2 = 15
    wl2 = tracked_width(probe, line2, bold, tracking2)
    pad = 40
    width = int(max(w1 + w2, wl2) + pad * 2)
    height = 330
    y1, y2 = pad - 20, pad + 178

    # glyph layers
    white = Image.new("L", (width, height), 0)
    red = Image.new("L", (width, height), 0)
    gold = Image.new("L", (width, height), 0)
    ImageDraw.Draw(white).text((pad, y1), word1, font=black, fill=255)
    ImageDraw.Draw(red).text((pad + w1, y1), word2, font=black, fill=255)
    tracked_text(ImageDraw.Draw(gold), (pad + 4, y2), line2, bold, 255, tracking2)

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    # soft shadow for readability over busy art
    alpha = Image.new("L", (width, height), 0)
    for layer in (white, red, gold):
        alpha = Image.composite(Image.new("L", (width, height), 255), alpha, layer)
    shadow = alpha.filter(ImageFilter.GaussianBlur(14)).point(lambda v: min(255, int(v * 1.6)))
    shadow_rgba = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_rgba.putalpha(shadow.point(lambda v: int(v * 0.75)))
    canvas = Image.alpha_composite(canvas, shadow_rgba)

    def fill(layer, top, bottom):
        grad = Image.new("RGBA", (width, height))
        px = grad.load()
        for y in range(height):
            t = y / (height - 1)
            c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
            for x in range(width):
                px[x, y] = c
        grad.putalpha(layer)
        return grad

    canvas = Image.alpha_composite(canvas, fill(white, (255, 255, 255), (205, 210, 216)))
    canvas = Image.alpha_composite(canvas, fill(red, (255, 70, 46), (176, 14, 20)))
    canvas = Image.alpha_composite(canvas, fill(gold, (255, 214, 92), (255, 168, 38)))
    save_png(canvas.crop(canvas.getbbox()), path)


def make_gradient(path, size, horizontal):
    w, h = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    px = image.load()
    for y in range(h):
        for x in range(w):
            if horizontal:  # opaque on the left, transparent on the right
                t = x / (w - 1)
                a = 1.0 - (t * t * (3 - 2 * t))
            else:  # transparent at the top, opaque at the bottom
                t = y / (h - 1)
                a = t * t * (3 - 2 * t)
            px[x, y] = (0, 0, 0, int(255 * a))
    save_png(image, path)


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for target, source in BACKGROUNDS.items():
        if engine_compatible_png(SOURCES / source):
            # keep the owner's original bytes (git stores the identical file only once)
            shutil.copyfile(SOURCES / source, OUTPUT / target)
            print((OUTPUT / target).relative_to(ROOT), "copied as is")
        else:
            save_png(Image.open(SOURCES / source).convert("RGB"), OUTPUT / target)
    make_title(OUTPUT / "title.png")
    make_gradient(OUTPUT / "fade_left.png", (256, 4), horizontal=True)
    make_gradient(OUTPUT / "fade_bottom.png", (4, 256), horizontal=False)


if __name__ == "__main__":
    main()
