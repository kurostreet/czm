#!/usr/bin/env python3
"""Render the small crossed-tools community badge as a white UI mask."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
im = Image.new("RGBA", (256, 256))
draw = ImageDraw.Draw(im)
draw.line([(52, 210), (183, 79)], fill="white", width=23)
draw.polygon([(129, 45), (156, 18), (230, 92), (203, 119)], fill="white")
draw.line([(207, 207), (77, 77)], fill="white", width=22)
draw.arc((23, 23, 128, 128), 145, 360, fill="white", width=21)
im = im.resize((128, 128), Image.Resampling.LANCZOS)
im.save(root / "3rdparty/cs16client-extras/gfx/czm/ui/icon_tools.png", optimize=True)
