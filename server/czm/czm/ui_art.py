#!/usr/bin/env python3
"""Build replacements for legacy UI images from the game's existing original artwork.

The server derives UI replacements from the artwork already in the core build.
No original game artwork is stored in this module.
"""
import io
import math
import struct

from PIL import Image, ImageOps

ART_REVISION = 1


def encoded(image, kind):
    out = io.BytesIO()
    image.save(out, kind)
    return out.getvalue()


def contained(image, size):
    result = Image.new("RGBA", size)
    part = ImageOps.contain(image.convert("RGBA"), size, Image.Resampling.LANCZOS)
    result.alpha_composite(part, ((size[0] - part.width) // 2, (size[1] - part.height) // 2))
    return result


def indexed(image, size, transparent=False):
    rgba = contained(image, size) if transparent else ImageOps.fit(image.convert("RGBA"), size)
    quantized = rgba.convert("RGB").quantize(colors=255 if transparent else 256)
    pixels = bytearray(quantized.tobytes())
    palette = bytes(quantized.getpalette()).ljust(768, b"\0")[:768]
    if transparent:
        for i, alpha in enumerate(rgba.getchannel("A").tobytes()):
            if alpha < 128:
                pixels[i] = 255
        palette = palette[:765] + b"\0\0\xff"
    return bytes(pixels), palette


def lmp(image, size):
    pixels, palette = indexed(image, size)
    return struct.pack("<II", *size) + pixels + struct.pack("<H", 256) + palette


def cached_wad(background):
    payload = lmp(background, (320, 200))
    payload += b"\0" * (-len(payload) % 4)
    offset = 12 + 2 * len(payload)
    directory = b"".join(struct.pack("<iiiBBBB16s", 12 + i * len(payload), len(payload), len(payload),
                                     66, 0, 0, 0, name)
                         for i, name in enumerate((b"CONBACK", b"LOADING")))
    return struct.pack("<4sii", b"WAD3", 2, offset) + payload * 2 + directory


def sprite(image, size):
    pixels, palette = indexed(image, size, transparent=True)
    width, height = size
    # GoldSrc sprite v2, view-parallel, alpha-test, one single frame.
    header = struct.pack("<4siiifiiifi", b"IDSP", 2, 2, 2, math.hypot(width, height) / 2,
                         width, height, 1, 0.0, 0)
    frame = struct.pack("<iiiii", 0, -width // 2, height // 2, width, height)
    return header + struct.pack("<H", 256) + palette + frame + pixels


def make_entries(background, title, logo):
    entries = {}
    for game in ("valve", "cstrike"):
        entries[f"{game}/cached.wad"] = cached_wad(background)
        for name in ("conback", "loading"):
            entries[f"{game}/gfx/{name}.lmp"] = lmp(background, (320, 200))
        entries[f"{game}/gfx/lambda.bmp"] = encoded(contained(logo, (64, 64)).convert("RGB"), "BMP")
        for name, size in (("lambda", 64), ("lambda64", 64), ("lambda32", 32)):
            entries[f"{game}/gfx/{name}.lmp"] = lmp(contained(logo, (size, size)), (size, size))
        entries[f"{game}/resource/logo_game.tga"] = encoded(contained(title, (512, 96)), "TGA")
        entries[f"{game}/game.ico"] = encoded(contained(logo, (256, 256)), "ICO")
        entries[f"{game}/gfx/shell/splash.bmp"] = encoded(ImageOps.fit(background, (800, 600)), "BMP")
        tiled = ImageOps.fit(background, (800, 600))
        for row, height in ((1, 256), (2, 256), (3, 88)):
            for col, width in zip("abcd", (256, 256, 256, 32)):
                x, y = "abcd".index(col) * 256, (row - 1) * 256
                entries[f"{game}/resource/background/800_{row}_{col}_loading.tga"] = encoded(
                    tiled.crop((x, y, x + width, y + height)), "TGA")
        for name, size in (("logo", 64), ("640_logo", 64), ("small_logo", 32), ("320_logo", 32)):
            entries[f"{game}/sprites/{name}.spr"] = sprite(logo, (size, size))
        entries[f"{game}/logos/lambda.bmp"] = encoded(contained(logo, (64, 64)).convert("RGB"), "BMP")
    entries["cstrike/gfx/vgui/CS_logo.tga"] = encoded(contained(title, (256, 64)), "TGA")
    for name, size in (("640_banner", (256, 32)), ("640_banner_small", (192, 32))):
        entries[f"valve/gfx/vgui/{name}.tga"] = encoded(contained(title, size), "TGA")
    entries["cstrike/motd.txt"] = (
        '<html><body style="background:#10131b;color:#eee;font-family:sans-serif;text-align:center">'
        '<h1>Counter Zombie Mobile</h1><p>32 players</p>'
        '<p><a href="https://counter-zombie.ru">counter-zombie.ru</a></p></body></html>\n'
    ).encode()
    return entries

