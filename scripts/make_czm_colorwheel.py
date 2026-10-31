#!/usr/bin/env python3
"""Reproduce the HSV wheel icon without external images or image dependencies."""
import colorsys
import math
from pathlib import Path
import struct
import zlib


def wheel_png(size=192):
    rows = bytearray()
    radius = size / 2 - 1
    for y in range(size):
        rows.append(0)
        for x in range(size):
            dx, dy = x + .5 - size / 2, y + .5 - size / 2
            distance = math.hypot(dx, dy)
            rgb = colorsys.hsv_to_rgb((math.atan2(dy, dx) / (2 * math.pi)) % 1, min(1, distance / radius), 1)
            rows.extend(round(v * 255) for v in rgb)
            rows.append(round(max(0, min(1, radius + .5 - distance)) * 255))
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))


if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1] / '3rdparty/czm_project/gfx/czm/ui/color_wheel.png'
    output.write_bytes(wheel_png())
    print(output)
