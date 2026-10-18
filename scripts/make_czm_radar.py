#!/usr/bin/env python3
"""Draw the radar plates and marks of Counter Zombie Mobile.

Three plates (classic, tactical, minimal) hold everything that does not move: the frame,
the rings or the grid, the view cone pointing up and the player arrow in the centre.
The game draws the plate, then the marks of the players on top, tinted with their colour.
The menu preview and the editor draw the same pictures.

usage: make_czm_radar.py
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "3rdparty/cs16client-extras/gfx/czm/radar"
SIZE = 512
SS = 3  # supersampling
RED = (224, 37, 50)
BLUE = (120, 200, 255)


def canvas(size):
    return Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))


def finish(image, size):
    return image.resize((size, size), Image.Resampling.LANCZOS)


def layer_over(base, layer):
    return Image.alpha_composite(base, layer)


def cone(size, cx, cy, radius, half_angle, color, alpha):
    """View cone pointing up, fading towards its edge."""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).pieslice((cx - radius, cy - radius, cx + radius, cy + radius),
                                  -90 - half_angle, -90 + half_angle, fill=255)
    fade = Image.radial_gradient("L").resize((radius * 2, radius * 2))  # 0 in the centre, 255 at the edge
    gradient = Image.new("L", (size, size), 255)
    gradient.paste(fade, (cx - radius, cy - radius))
    gradient = gradient.point(lambda v: int(alpha * (1 - v / 255) ** 1.2))
    alpha_mask = ImageChops.multiply(mask, gradient)
    layer = Image.new("RGBA", (size, size), color + (0,))
    layer.putalpha(alpha_mask)
    return layer


def arrow(size, cx, cy, length, color):
    """The player in the centre, looking up, with a dark outline."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w = length * 0.78
    points = [(cx, cy - length * 0.62), (cx - w / 2, cy + length * 0.42), (cx, cy + length * 0.2), (cx + w / 2, cy + length * 0.42)]
    d.polygon(points, fill=(0, 0, 0, 200))
    shadow = layer.filter(ImageFilter.GaussianBlur(length * 0.08))
    d = ImageDraw.Draw(shadow)
    inner = [(cx + (x - cx) * 0.84, cy + (y - cy) * 0.84) for x, y in points]
    d.polygon(inner, fill=color + (255,))
    return shadow


def classic():
    s = SIZE * SS
    c = s // 2
    r = int(s * 0.485)
    img = canvas(SIZE)
    d = ImageDraw.Draw(img)
    d.ellipse((c - r, c - r, c + r, c + r), fill=(10, 14, 22, 190))
    line = max(2, int(s * 0.005))
    for k in (1 / 3, 2 / 3):
        rr = int(r * k)
        d.ellipse((c - rr, c - rr, c + rr, c + rr), outline=(255, 255, 255, 42), width=line)
    d.line((c - r, c, c + r, c), fill=(255, 255, 255, 34), width=line)
    d.line((c, c - r, c, c + r), fill=(255, 255, 255, 34), width=line)
    img = layer_over(img, cone(s, c, c, int(r * 0.97), 45, (255, 255, 255), 70))
    d = ImageDraw.Draw(img)
    rim = int(s * 0.03)
    d.ellipse((c - r, c - r, c + r, c + r), outline=(0, 0, 0, 120), width=rim + line * 2)
    d.ellipse((c - r, c - r, c + r, c + r), outline=RED + (255,), width=rim)
    img = layer_over(img, arrow(s, c, c, int(s * 0.085), (255, 255, 255)))
    return finish(img, SIZE)


def tactical():
    s = SIZE * SS
    c = s // 2
    edge = int(s * 0.012)
    corner = int(s * 0.055)
    img = canvas(SIZE)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((edge, edge, s - edge, s - edge), radius=corner, fill=(10, 14, 22, 215))
    line = max(2, int(s * 0.004))
    inset = int(s * 0.05)
    for k in range(1, 6):
        v = int(edge + (s - edge * 2) * k / 6)
        d.line((inset, v, s - inset, v), fill=BLUE + (30,), width=line)
        d.line((v, inset, v, s - inset), fill=BLUE + (30,), width=line)
    # range ring a little brighter, so distance reads at a glance
    rr = int(s * 0.43 * 0.5)
    d.ellipse((c - rr, c - rr, c + rr, c + rr), outline=BLUE + (46,), width=line)
    img = layer_over(img, cone(s, c, c, int(s * 0.47), 40, BLUE, 70))
    d = ImageDraw.Draw(img)
    border = int(s * 0.012)
    d.rounded_rectangle((edge, edge, s - edge, s - edge), radius=corner, outline=(62, 70, 88, 255), width=border)
    bar = int(s * 0.016)
    d.rectangle((corner + edge, edge, s - corner - edge, edge + bar), fill=RED + (255,))
    img = layer_over(img, arrow(s, c, c, int(s * 0.085), BLUE))
    return finish(img, SIZE)


def minimal():
    s = SIZE * SS
    c = s // 2
    r = int(s * 0.485)
    img = canvas(SIZE)
    d = ImageDraw.Draw(img)
    d.ellipse((c - r, c - r, c + r, c + r), fill=(0, 0, 0, 72))
    img = layer_over(img, cone(s, c, c, int(r * 0.97), 35, (255, 255, 255), 52))
    d = ImageDraw.Draw(img)
    d.ellipse((c - r, c - r, c + r, c + r), outline=(255, 255, 255, 105), width=max(2, int(s * 0.008)))
    img = layer_over(img, arrow(s, c, c, int(s * 0.08), (255, 255, 255)))
    return finish(img, SIZE)


def mark(kind):
    """64 px white marks with a dark outline; the game tints them."""
    size = 64
    s = size * SS
    img = canvas(size)
    d = ImageDraw.Draw(img)
    c = s / 2
    outline = (0, 0, 0, 210)
    if kind == "dot":
        r = s * 0.42
        d.ellipse((c - r, c - r, c + r, c + r), fill=outline)
        r = s * 0.31
        d.ellipse((c - r, c - r, c + r, c + r), fill=(255, 255, 255, 255))
    elif kind in ("up", "down"):
        sign = -1 if kind == "up" else 1
        def tri(scale):
            h = s * 0.40 * scale
            w = s * 0.46 * scale
            return [(c, c + sign * h), (c - w, c - sign * h * 0.8), (c + w, c - sign * h * 0.8)]
        d.polygon(tri(1.0), fill=outline)
        d.polygon(tri(0.66), fill=(255, 255, 255, 255))
    else:  # the planted bomb: a cross
        for width, color in ((s * 0.24, outline), (s * 0.12, (255, 255, 255, 255))):
            a = s * 0.2
            d.line((a, a, s - a, s - a), fill=color, width=int(width))
            d.line((s - a, a, a, s - a), fill=color, width=int(width))
    return finish(img, size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plates = {"classic": classic(), "tactical": tactical(), "minimal": minimal()}
    for name, image in plates.items():
        image.save(OUT / f"radar_{name}.png", optimize=True)
    for name in ("dot", "up", "down", "x"):
        mark(name).save(OUT / f"mark_{name}.png", optimize=True)
    for path in sorted(OUT.iterdir()):
        print(path.relative_to(ROOT), path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
