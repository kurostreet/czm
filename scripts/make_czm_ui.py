#!/usr/bin/env python3
"""Build Counter Zombie Mobile main menu UI textures: mode tiles, icons, chips and buttons.

Output goes to 3rdparty/cs16client-extras/gfx/czm/ui/ and is committed, so the Android
build does not need Pillow. Re-run after changing the owner's art or the design.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "assets/branding"
OUTPUT = ROOT / "3rdparty/cs16client-extras/gfx/czm/ui"
SS = 4  # supersampling factor for smooth edges

TILE_W, TILE_H = 1110, 300  # 3.7:1, the menu keeps this aspect
TILES = {
    # name: (source art, crop focus x/y, accent colour)
    "tile_attack.png": ("loading-4.png", (0.62, 0.55), (255, 59, 47)),
    "tile_escape.png": ("loading-5.png", (0.75, 0.45), (34, 211, 238)),
    "tile_boss.png": ("loading-3.png", (0.62, 0.30), (168, 85, 247)),
}


def save(image, name):
    path = OUTPUT / name
    image.save(path, "PNG", optimize=True)
    print(path.relative_to(ROOT), image.size, path.stat().st_size, "bytes")


def cover(img, w, h, cx, cy):
    s = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x = int((img.width - w) * cx)
    y = int((img.height - h) * cy)
    return img.crop((x, y, x + w, y + h))


def hgrad(w, h, left, right):
    g = Image.new("L", (w, 1))
    for x in range(w):
        t = x / max(1, w - 1)
        t = t * t * (3 - 2 * t)
        g.putpixel((x, 0), int(left + (right - left) * t))
    return g.resize((w, h))


def vgrad(w, h, top, bottom):
    g = Image.new("L", (1, h))
    for y in range(h):
        g.putpixel((0, y), int(top + (bottom - top) * y / max(1, h - 1)))
    return g.resize((w, h))


def smooth_polygon_mask(w, h, points):
    big = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(big).polygon([(x * SS, y * SS) for x, y in points], fill=255)
    return big.resize((w, h), Image.LANCZOS)


def make_tile(name, art, focus, accent):
    w, h = TILE_W, TILE_H
    skew = int(h * 0.30)
    base = cover(Image.open(SOURCES / art).convert("RGBA"), w, h, *focus)
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    shade.putalpha(hgrad(w, h, 215, 30))
    base = Image.alpha_composite(base, shade)
    glow = Image.new("RGBA", (w, h), accent + (255,))
    glow.putalpha(vgrad(w, h, 0, 90))
    base = Image.alpha_composite(base, glow)

    # play button baked on the right side
    bs = int(h * 0.36)
    bx, by = w - bs - int(h * 0.14), (h - bs) // 2
    big = Image.new("RGBA", (bs * SS, bs * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.ellipse([0, 0, bs * SS - 1, bs * SS - 1], fill=accent + (255,))
    d.ellipse([0, 0, bs * SS - 1, bs * SS - 1], outline=(255, 255, 255, 210), width=3 * SS)
    S = bs * SS
    d.polygon([(S * .40, S * .30), (S * .40, S * .70), (S * .72, S * .50)], fill=(255, 255, 255, 255))
    base.alpha_composite(big.resize((bs, bs), Image.LANCZOS), (bx, by))

    base.putalpha(smooth_polygon_mask(w, h, [(skew, 0), (w, 0), (w, h), (0, h)]))
    outline = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    ImageDraw.Draw(outline).line([(skew * SS, 2 * SS), ((w - 2) * SS, 2 * SS), ((w - 2) * SS, (h - 2) * SS),
                                  (2 * SS, (h - 2) * SS), (skew * SS, 2 * SS)], fill=accent + (235,), width=4 * SS)
    base = Image.alpha_composite(base, outline.resize((w, h), Image.LANCZOS))
    save(base, name)


def make_tile_shadow(name):
    # soft shadow under a tile, drawn 10% of the tile height larger on every side
    w, h = TILE_W // 2, TILE_H // 2
    m = h // 10
    skew = int(h * 0.30)
    shadow = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    mask = Image.new("L", shadow.size, 0)
    ImageDraw.Draw(mask).polygon([(m + skew, m), (m + w, m), (m + w, m + h), (m, m + h)], fill=175)
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(m * 0.45)))
    save(shadow, name)


def make_dot(name, size=64):
    big = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse([0, 0, size * SS - 1, size * SS - 1], fill=(255, 255, 255, 255))
    save(big.resize((size, size), Image.LANCZOS), name)


def make_ripple(name, size=256):
    ripple = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    px = ripple.load()
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            # a ring at 94% of the radius, 4% wide, with soft edges
            a = max(0.0, 1.0 - abs(d - 0.94) / 0.04)
            px[x, y] = (255, 255, 255, int(255 * a * a * (3 - 2 * a)))
    save(ripple, name)


def make_touch_wheel(path, size=256):
    """The touch button of the weapon wheel in the style of the other touch buttons: their dark
    disc and light ring (taken from the "last weapon" button), a wheel of five parts on it."""
    base = Image.open(OUTPUT.parent / "touch/lastinv.png").convert("RGBA").resize((size, size), Image.LANCZOS)
    px = base.load()
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            t = math.hypot(x - c, y - c) / c
            if t < 0.85:  # the disc without the old picture, its colour from the centre to the ring
                k = t / 0.85
                px[x, y] = (round(35 - 15 * k), round(39 - 16 * k), round(47 - 18 * k), 168)
    S = size * SS
    glyph = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(glyph)
    white = (255, 255, 255, 255)
    outer, inner = S * .27, S * .12
    d.ellipse([S / 2 - outer, S / 2 - outer, S / 2 + outer, S / 2 + outer], fill=white)
    d.ellipse([S / 2 - inner, S / 2 - inner, S / 2 + inner, S / 2 + inner], fill=(0, 0, 0, 0))
    for i in range(5):
        a = math.radians(-90 + 36 + i * 72)
        d.line([S / 2, S / 2, S / 2 + math.cos(a) * S * .32, S / 2 + math.sin(a) * S * .32], fill=(0, 0, 0, 0), width=int(S * .03))
    d.ellipse([S / 2 - S * .055, S / 2 - S * .055, S / 2 + S * .055, S / 2 + S * .055], fill=white)
    base.alpha_composite(glyph.resize((size, size), Image.LANCZOS))
    base.save(path, "PNG", optimize=True)
    print(path.relative_to(ROOT), base.size, path.stat().st_size, "bytes")


def make_glow(name, size=96):
    # soft light for sparks: white, alpha falls off like a gaussian, no hard edge
    import math
    glow = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    px = glow.load()
    c = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            a = 0 if d >= 1 else int(255 * math.exp(-d * d * 4.2) * (1 - d) ** 0.5)
            px[x, y] = (255, 255, 255, a)
    save(glow, name)


def icon(kind, size=128, color=(255, 255, 255, 255)):
    S = size * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = int(S * 0.085)
    c = color
    clear = (0, 0, 0, 0)
    if kind == "bell":
        d.rounded_rectangle([S * .22, S * .22, S * .78, S * .74], radius=S * .26, outline=c, width=lw)
        d.rectangle([S * .22 + lw, S * .52, S * .78 - lw, S * .74 - lw / 2], fill=clear)
        d.rectangle([S * .22, S * .50, S * .22 + lw, S * .72], fill=c)
        d.rectangle([S * .78 - lw, S * .50, S * .78, S * .72], fill=c)
        d.rounded_rectangle([S * .10, S * .70, S * .90, S * .70 + lw], radius=lw / 2, fill=c)
        d.ellipse([S * .40, S * .78, S * .60, S * .95], fill=c)
        d.rounded_rectangle([S * .46, S * .06, S * .54, S * .22], radius=lw / 2, fill=c)
    elif kind == "user":
        d.ellipse([S * .31, S * .08, S * .69, S * .46], outline=c, width=lw)
        d.arc([S * .12, S * .54, S * .88, S * 1.30], 180, 360, fill=c, width=lw)
    elif kind == "stick":
        d.ellipse([S * .08, S * .08, S * .92, S * .92], outline=c, width=lw)
        d.ellipse([S * .34, S * .20, S * .70, S * .56], fill=c)
    elif kind == "gear":
        cx = cy = S / 2
        for i in range(8):
            a = i * math.pi / 4
            x, y = cx + math.cos(a) * S * .37, cy + math.sin(a) * S * .37
            d.ellipse([x - S * .095, y - S * .095, x + S * .095, y + S * .095], fill=c)
        d.ellipse([S * .19, S * .19, S * .81, S * .81], fill=c)
        d.ellipse([S * .37, S * .37, S * .63, S * .63], fill=clear)
    elif kind == "info":
        d.ellipse([S * .07, S * .07, S * .93, S * .93], outline=c, width=lw)
        d.ellipse([S * .43, S * .22, S * .57, S * .36], fill=c)
        d.rounded_rectangle([S * .44, S * .42, S * .56, S * .76], radius=lw / 3, fill=c)
    elif kind == "pencil":
        d.polygon([(S * .18, S * .82), (S * .24, S * .60), (S * .68, S * .16), (S * .84, S * .32), (S * .40, S * .76)],
                  outline=c, width=lw)
    elif kind == "back":
        d.line([S * .70, S * .50, S * .26, S * .50], fill=c, width=lw)
        d.line([S * .48, S * .26, S * .24, S * .50], fill=c, width=lw)
        d.line([S * .48, S * .74, S * .24, S * .50], fill=c, width=lw)
        r = lw / 2
        for x, y in ((S * .24, S * .50), (S * .48, S * .26), (S * .48, S * .74), (S * .70, S * .50)):
            d.ellipse([x - r, y - r, x + r, y + r], fill=c)
    elif kind == "display":
        d.rounded_rectangle([S * .08, S * .16, S * .92, S * .70], radius=S * .06, outline=c, width=lw)
        d.rectangle([S * .44, S * .70, S * .56, S * .82], fill=c)
        d.rounded_rectangle([S * .28, S * .80, S * .72, S * .80 + lw], radius=lw / 2, fill=c)
    elif kind == "sound":
        d.polygon([(S * .10, S * .38), (S * .28, S * .38), (S * .50, S * .18), (S * .50, S * .82), (S * .28, S * .62),
                   (S * .10, S * .62)], fill=c)
        d.arc([S * .44, S * .30, S * .74, S * .70], -55, 55, fill=c, width=lw)
        d.arc([S * .44, S * .14, S * .92, S * .86], -55, 55, fill=c, width=lw)
    elif kind == "target":
        d.ellipse([S * .16, S * .16, S * .84, S * .84], outline=c, width=lw)
        for a, b in (((.50, .04), (.50, .30)), ((.50, .70), (.50, .96)), ((.04, .50), (.30, .50)), ((.70, .50), (.96, .50))):
            d.line([S * a[0], S * a[1], S * b[0], S * b[1]], fill=c, width=lw)
        d.ellipse([S * .44, S * .44, S * .56, S * .56], fill=c)
    elif kind == "check":
        d.line([S * .18, S * .52, S * .42, S * .76], fill=c, width=int(lw * 1.4))
        d.line([S * .40, S * .76, S * .84, S * .28], fill=c, width=int(lw * 1.4))
    elif kind == "close":
        d.line([S * .22, S * .22, S * .78, S * .78], fill=c, width=lw)
        d.line([S * .78, S * .22, S * .22, S * .78], fill=c, width=lw)
    elif kind == "chat":
        d.rounded_rectangle([S * .08, S * .14, S * .92, S * .72], radius=S * .18, outline=c, width=lw)
        d.polygon([(S * .24, S * .66), (S * .44, S * .66), (S * .22, S * .90)], fill=c)
        for x in (.32, .50, .68):
            d.ellipse([S * (x - .055), S * .38, S * (x + .055), S * .49], fill=c)
    elif kind == "globe":
        d.ellipse([S * .08, S * .08, S * .92, S * .92], outline=c, width=lw)
        d.ellipse([S * .31, S * .08, S * .69, S * .92], outline=c, width=int(lw * .8))
        d.line([S * .10, S * .50, S * .90, S * .50], fill=c, width=int(lw * .8))
        d.arc([S * .14, S * .02, S * .86, S * .40], 25, 155, fill=c, width=int(lw * .7))
        d.arc([S * .14, S * .60, S * .86, S * .98], 205, 335, fill=c, width=int(lw * .7))
    elif kind == "search":
        d.ellipse([S * .10, S * .10, S * .66, S * .66], outline=c, width=lw)
        d.line([S * .60, S * .60, S * .88, S * .88], fill=c, width=int(lw * 1.3))
        r = lw * .65
        d.ellipse([S * .88 - r, S * .88 - r, S * .88 + r, S * .88 + r], fill=c)
    elif kind == "spray":
        # a spray can, a cloud of paint leaving the nozzle
        d.rounded_rectangle([S * .14, S * .34, S * .58, S * .95], radius=S * .1, outline=c, width=lw)
        d.rounded_rectangle([S * .23, S * .17, S * .49, S * .34], radius=S * .04, fill=c)
        d.rounded_rectangle([S * .49, S * .20, S * .62, S * .28], radius=S * .02, fill=c)
        d.line([S * .14 + lw, S * .56, S * .58 - lw, S * .56], fill=c, width=int(lw * .7))
        for x, y, r in ((.76, .16, .055), (.90, .10, .045), (.80, .32, .05), (.94, .26, .04)):
            d.ellipse([S * (x - r), S * (y - r), S * (x + r), S * (y + r)], fill=c)
    elif kind == "knife":
        # a combat knife, the blade up and to the right
        blade = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        b = ImageDraw.Draw(blade)
        b.polygon([(S * .43, S * .64), (S * .43, S * .20), (S * .52, S * .04), (S * .59, S * .18), (S * .57, S * .64)], fill=c)
        b.rounded_rectangle([S * .33, S * .63, S * .67, S * .69], radius=S * .02, fill=c)
        b.rounded_rectangle([S * .44, S * .69, S * .56, S * .95], radius=S * .04, fill=c)
        im.alpha_composite(blade.rotate(-42, resample=Image.BICUBIC, center=(S / 2, S / 2)))
    elif kind == "cart":
        d.line([(S * .06, S * .20), (S * .20, S * .20), (S * .32, S * .64), (S * .80, S * .64)], fill=c, width=lw, joint="curve")
        d.polygon([(S * .24, S * .30), (S * .92, S * .30), (S * .82, S * .56), (S * .31, S * .56)], fill=c)
        for x in (.38, .74):
            d.ellipse([S * (x - .075), S * .74, S * (x + .075), S * .89], fill=c)
    elif kind == "go":
        # two chevrons up: forward
        for top in (.16, .44):
            d.line([(S * .20, S * (top + .30)), (S * .50, S * top), (S * .80, S * (top + .30))], fill=c, width=lw, joint="curve")
            r = lw / 2
            for x, y in ((.20, top + .30), (.50, top), (.80, top + .30)):
                d.ellipse([S * x - r, S * y - r, S * x + r, S * y + r], fill=c)
    elif kind == "bomb":
        # a round bomb, its fuse burning
        d.ellipse([S * .10, S * .30, S * .76, S * .96], outline=c, width=lw)
        d.polygon([(S * .52, S * .30), (S * .66, S * .22), (S * .76, S * .38), (S * .64, S * .44)], fill=c)
        d.arc([S * .68, S * .06, S * .96, S * .40], 190, 280, fill=c, width=int(lw * .8))
        for a in range(0, 360, 60):
            x, y = .86 + .07 * math.cos(math.radians(a)), .10 + .07 * math.sin(math.radians(a))
            d.line([S * .86, S * .10, S * x, S * y], fill=c, width=int(lw * .5))
        d.arc([S * .22, S * .46, S * .50, S * .74], 190, 260, fill=c, width=int(lw * .7))
    elif kind == "skull":
        # enemy down
        d.ellipse([S * .16, S * .06, S * .84, S * .70], fill=c)
        d.rounded_rectangle([S * .30, S * .52, S * .70, S * .90], radius=S * .06, fill=c)
        d.ellipse([S * .28, S * .30, S * .46, S * .48], fill=clear)
        d.ellipse([S * .54, S * .30, S * .72, S * .48], fill=clear)
        d.polygon([(S * .50, S * .50), (S * .45, S * .60), (S * .55, S * .60)], fill=clear)
        for x in (.43, .57):
            d.rectangle([S * x - lw * .3, S * .70, S * x + lw * .3, S * .90], fill=clear)
    elif kind in ("star", "star_on"):
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = .46 if i % 2 == 0 else .20
            pts.append((S * (.5 + math.cos(a) * rr), S * (.53 + math.sin(a) * rr)))
        if kind == "star_on":
            d.polygon(pts, fill=c)
        else:
            d.line(pts + [pts[0], pts[1]], fill=c, width=int(lw * .8), joint="curve")
    elif kind == "refresh":
        d.arc([S * .14, S * .14, S * .86, S * .86], 300, 250, fill=c, width=lw)
        a = math.radians(250)
        tip = (S * (.5 + math.cos(a) * .36), S * (.5 + math.sin(a) * .36))
        d.polygon([(tip[0] + S * .02, tip[1] - S * .17), (tip[0] + S * .02, tip[1] + S * .17), (tip[0] + S * .22, tip[1])], fill=c)
    elif kind == "plus":
        d.rounded_rectangle([S * .44, S * .14, S * .56, S * .86], radius=lw / 2, fill=c)
        d.rounded_rectangle([S * .14, S * .44, S * .86, S * .56], radius=lw / 2, fill=c)
    elif kind == "lock":
        d.rounded_rectangle([S * .16, S * .44, S * .84, S * .92], radius=S * .10, fill=c)
        d.arc([S * .28, S * .08, S * .72, S * .60], 180, 360, fill=c, width=lw)
        d.rectangle([S * .28, S * .32, S * .28 + lw, S * .46], fill=c)
        d.rectangle([S * .72 - lw, S * .32, S * .72, S * .46], fill=c)
        d.ellipse([S * .44, S * .58, S * .56, S * .70], fill=clear)
    elif kind == "users":
        d.ellipse([S * .14, S * .16, S * .46, S * .48], fill=c)
        d.pieslice([S * .02, S * .54, S * .58, S * 1.10], 180, 360, fill=c)
        d.ellipse([S * .56, S * .22, S * .82, S * .48], outline=c, width=int(lw * .8))
        d.arc([S * .50, S * .58, S * .98, S * 1.06], 200, 340, fill=c, width=int(lw * .8))
    elif kind == "clock":
        d.ellipse([S * .08, S * .08, S * .92, S * .92], outline=c, width=lw)
        d.line([S * .50, S * .24, S * .50, S * .52], fill=c, width=lw)
        d.line([S * .48, S * .52, S * .68, S * .64], fill=c, width=lw)
    elif kind == "send":
        d.polygon([(S * .06, S * .46), (S * .92, S * .10), (S * .74, S * .88), (S * .50, S * .66), (S * .38, S * .86),
                   (S * .36, S * .60)], fill=c)
        d.line([S * .36, S * .60, S * .80, S * .24], fill=clear, width=int(lw * .5))
    elif kind == "code":
        d.line([S * .30, S * .26, S * .08, S * .50], fill=c, width=lw)
        d.line([S * .08, S * .50, S * .30, S * .74], fill=c, width=lw)
        d.line([S * .70, S * .26, S * .92, S * .50], fill=c, width=lw)
        d.line([S * .92, S * .50, S * .70, S * .74], fill=c, width=lw)
        d.line([S * .58, S * .14, S * .42, S * .86], fill=c, width=lw)
    elif kind == "calendar":
        d.rounded_rectangle([S * .10, S * .16, S * .90, S * .90], radius=S * .10, outline=c, width=lw)
        d.rectangle([S * .10, S * .30, S * .90, S * .40], fill=c)
        d.rounded_rectangle([S * .28, S * .06, S * .28 + lw, S * .26], radius=lw / 2, fill=c)
        d.rounded_rectangle([S * .72 - lw, S * .06, S * .72, S * .26], radius=lw / 2, fill=c)
        for x, y in ((.32, .56), (.50, .56), (.68, .56), (.32, .74), (.50, .74)):
            d.rectangle([S * (x - .05), S * (y - .05), S * (x + .05), S * (y + .05)], fill=c)
    elif kind == "chevron":
        d.line([S * .38, S * .20, S * .66, S * .50], fill=c, width=lw)
        d.line([S * .66, S * .50, S * .38, S * .80], fill=c, width=lw)
    elif kind == "sort":
        d.line([S * .30, S * .14, S * .30, S * .84], fill=c, width=lw)
        d.polygon([(S * .12, S * .66), (S * .48, S * .66), (S * .30, S * .90)], fill=c)
        d.line([S * .70, S * .86, S * .70, S * .16], fill=c, width=lw)
        d.polygon([(S * .52, S * .34), (S * .88, S * .34), (S * .70, S * .10)], fill=c)
    elif kind == "tag":
        d.polygon([(S * .10, S * .14), (S * .52, S * .14), (S * .90, S * .52), (S * .52, S * .90), (S * .10, S * .52)],
                  outline=c, width=lw)
        d.ellipse([S * .26, S * .30, S * .38, S * .42], fill=c)
    elif kind in ("heart", "heart_on"):
        pts = []
        for i in range(72):
            t = math.pi * 2 * i / 72
            hx = 16 * math.sin(t) ** 3
            hy = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            pts.append((S * (.5 + hx / 36.0), S * (.44 - hy / 34.0)))
        if kind == "heart_on":
            d.polygon(pts, fill=c)
        else:
            d.line(pts + [pts[0]], fill=c, width=int(lw * .95), joint="curve")
    elif kind == "play":
        d.polygon([(S * .32, S * .20), (S * .32, S * .80), (S * .82, S * .50)], fill=c)
    elif kind == "shield":
        # SUPPORT: a solid heater shield with a check cut out of it
        right = [(S * .50, S * .07), (S * .66, S * .13), (S * .85, S * .16), (S * .85, S * .50)]
        for i in range(1, 21):                       # the right side bends into the point
            t = i / 20.0
            right.append((S * (.85 - .35 * t * t), S * (.50 + .44 * t)))
        left = [(S - x, y) for x, y in reversed(right[1:-1])]
        d.polygon(right + left, fill=c)
        d.line([(S * .32, S * .47), (S * .45, S * .60), (S * .69, S * .35)], fill=clear, width=int(lw * 1.1), joint="curve")
    elif kind == "copy":
        # two sheets: the back one is only an outline peeking out
        d.rounded_rectangle([S * .12, S * .12, S * .62, S * .62], radius=S * .09, outline=c, width=lw)
        d.rounded_rectangle([S * .34, S * .34, S * .90, S * .90], radius=S * .10, fill=c)
        d.rounded_rectangle([S * .34 + lw * 1.4, S * .34 + lw * 1.4, S * .90 - lw * 1.4, S * .90 - lw * 1.4],
                            radius=S * .05, fill=clear)
    elif kind == "more":
        for x in (.20, .50, .80):
            d.ellipse([S * (x - .09), S * .41, S * (x + .09), S * .59], fill=c)
    elif kind == "ring":
        # the frame around a profile picture, tinted in the game
        d.ellipse([S * .03, S * .03, S * .97, S * .97], outline=c, width=int(S * .045))
    elif kind == "flag":
        d.rounded_rectangle([S * .18, S * .08, S * .18 + lw, S * .94], radius=lw / 2, fill=c)
        d.polygon([(S * .24, S * .12), (S * .84, S * .12), (S * .70, S * .32), (S * .84, S * .52), (S * .24, S * .52)], fill=c)
    elif kind == "block":
        d.ellipse([S * .10, S * .10, S * .90, S * .90], outline=c, width=lw)
        d.line([S * .24, S * .76, S * .76, S * .24], fill=c, width=lw)
    elif kind == "crown_royal":
        # the first three places: five points with pearls, a band with a jewel
        peaks = ((.12, .32), (.31, .26), (.50, .16), (.69, .26), (.88, .32))
        outline = [(S * .12, S * .80)]
        for k, (x, y) in enumerate(peaks):
            outline.append((S * x, S * y))
            if k < len(peaks) - 1:
                outline.append((S * (x + peaks[k + 1][0]) / 2, S * .56))
        outline.append((S * .88, S * .80))
        d.polygon(outline, fill=c)
        for x, y in peaks:
            d.ellipse([S * (x - .065), S * (y - .10), S * (x + .065), S * (y + .03)], fill=c)
        d.rounded_rectangle([S * .10, S * .83, S * .90, S * .95], radius=S * .04, fill=c)
        d.rectangle([S * .16, S * .66, S * .84, S * .71], fill=clear)
        d.ellipse([S * .42, S * .60, S * .58, S * .76], fill=clear)
        d.ellipse([S * .455, S * .635, S * .545, S * .725], fill=c)
    elif kind == "crown":
        d.polygon([(S * .10, S * .78), (S * .10, S * .28), (S * .32, S * .50), (S * .50, S * .20), (S * .68, S * .50),
                   (S * .90, S * .28), (S * .90, S * .78)], fill=c)
        d.rounded_rectangle([S * .10, S * .82, S * .90, S * .94], radius=S * .04, fill=c)
    elif kind == "person_add":
        d.ellipse([S * .14, S * .12, S * .50, S * .48], fill=c)
        d.pieslice([S * .02, S * .54, S * .62, S * 1.14], 180, 360, fill=c)
        d.rectangle([S * .70, S * .36, S * .70 + lw, S * .76], fill=c)
        d.rectangle([S * .50 + lw / 2, S * .56 - lw / 2, S * .90 + lw / 2, S * .56 + lw / 2], fill=c)
    return im.resize((size, size), Image.LANCZOS)


def rounded(w, h, radius, fill, outline=None, width=0):
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=fill,
                                          outline=outline, width=width * SS)
    return big.resize((w, h), Image.LANCZOS)


def make_avatar(name, size=256):
    logo = Image.open(SOURCES / "counter-zombie-mobile-original.jpg").convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * SS - 1, size * SS - 1], fill=255)
    logo.putalpha(mask.resize((size, size), Image.LANCZOS))
    ring = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([2 * SS, 2 * SS, (size - 2) * SS, (size - 2) * SS], outline=(255, 59, 47, 255), width=10 * SS)
    logo = Image.alpha_composite(logo, ring.resize((size, size), Image.LANCZOS))
    save(logo, name)


NEW_ICONS = ("chat", "globe", "search", "star", "star_on", "refresh", "plus", "lock", "users", "clock", "send", "code",
             "calendar", "chevron", "sort", "tag", "heart", "heart_on", "play")


def main():
    import sys
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if "--support" in sys.argv:
        save(icon("shield"), "icon_shield.png")
        return
    if "--wheels" in sys.argv:
        # the touch wheels: knife and shop slots, the weapon wheel button
        save(icon("knife"), "icon_knife.png")
        save(icon("cart"), "icon_cart.png")
        make_touch_wheel(OUTPUT.parent / "touch/wheel.png")
        return
    if "--touchfx" in sys.argv:
        # the press animation of the touch buttons: a thin soft ring that runs out of a pressed button
        make_ripple("touch_ripple.png")
        return
    if "--radio" in sys.argv:
        # the radio wheel: the spray slot
        save(icon("spray"), "icon_spray.png")
        return
    if "--radio-menus" in sys.argv:
        # the wheels of the three radio menus: go, it's gonna blow, enemy down
        for kind in ("go", "bomb", "skull"):
            save(icon(kind), f"icon_{kind}.png")
        return
    if "--top" in sys.argv:
        # Top 100: the crowns of the first three and of the rest
        save(icon("crown_royal"), "icon_crown_royal.png")
        save(icon("crown"), "icon_crown_top.png")
        return
    if "--profile" in sys.argv:
        # the profile card: copy the ID, the ⋯ menu, the avatar frame, report, block, add a friend
        for kind in ("copy", "more", "ring", "flag", "block", "person_add"):
            save(icon(kind, 256 if kind == "ring" else 128), f"icon_{kind}.png")
        return
    if "--servers" in sys.argv:
        # server list and new navigation: only the new pictures, the rest stays as committed
        for kind in NEW_ICONS:
            save(icon(kind), f"icon_{kind}.png")
        save(Image.new("RGBA", (8, 8), (255, 255, 255, 255)), "white.png")
        make_glow("glow.png")
        return
    for name, (art, focus, accent) in TILES.items():
        make_tile(name, art, focus, accent)
    make_tile_shadow("tile_shadow.png")
    make_dot("dot.png")
    make_glow("glow.png")
    for kind in ("bell", "user", "stick", "gear", "info", "pencil", "close", "back", "display", "sound", "target", "check", "shield"):
        save(icon(kind), f"icon_{kind}.png")
    for kind in NEW_ICONS:
        save(icon(kind), f"icon_{kind}.png")
    save(Image.new("RGBA", (8, 8), (255, 255, 255, 255)), "white.png")
    make_avatar("avatar.png")
    # header chips and buttons, drawn at their real aspect by the menu
    save(rounded(128, 128, 64, (10, 12, 16, 160), (255, 255, 255, 64), 2), "chip_round.png")
    save(rounded(272, 128, 64, (10, 12, 16, 160), (255, 255, 255, 64), 2), "chip_lang.png")
    save(rounded(128, 112, 56, (220, 38, 38, 255)), "pill_lang_on.png")
    save(rounded(640, 120, 60, (220, 38, 38, 255)), "button_primary.png")
    save(rounded(640, 120, 60, (35, 39, 48, 255), (255, 255, 255, 64), 3), "button_secondary.png")
    save(rounded(640, 120, 60, (35, 39, 48, 255), (248, 113, 113, 170), 3), "button_danger.png")
    save(rounded(800, 680, 36, (12, 14, 19, 240), (255, 255, 255, 52), 2), "panel.png")
    # settings: cards for sprays and fields, active tab
    save(rounded(160, 160, 28, (24, 27, 34, 230), (255, 255, 255, 46), 2), "card.png")
    save(rounded(160, 160, 28, (40, 16, 18, 235), (239, 68, 68, 255), 5), "card_on.png")
    tab = rounded(400, 120, 30, (220, 38, 38, 255))
    shine = Image.new("RGBA", tab.size, (255, 255, 255, 0))
    shine.putalpha(vgrad(tab.width, tab.height, 60, 0))
    tab = Image.alpha_composite(tab, Image.composite(shine, Image.new("RGBA", tab.size, (0, 0, 0, 0)), tab.getchannel("A")))
    save(tab, "tab_on.png")
    # header fade: opaque at the top, transparent at the bottom
    fade = Image.new("RGBA", (4, 256), (0, 0, 0, 0))
    fade.putalpha(vgrad(4, 256, 255, 0))
    save(fade, "fade_top.png")


if __name__ == "__main__":
    main()
