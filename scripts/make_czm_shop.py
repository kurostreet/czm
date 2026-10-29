#!/usr/bin/env python3
"""Build the images of the Counter Zombie Mobile shop wheel.

For every number of sectors N (1..9): wheelN.png is the whole wheel (dark sectors,
thin borders, outer ring and the hub), wheelN_I.png is sector I highlighted
(transparent elsewhere, drawn over the wheel). Sector 0 is centred at the top,
the others follow clockwise. Geometry, shared with czm/menu/CzmShop.cpp:
canvas 640 x 640, centre 320, outer radius 300, sectors start at radius 88,
the hub circle has radius 80.

usage: make_czm_shop.py [N ...]   (only these numbers of sectors; needs Playwright with Chromium;
       the output is committed)
"""
import math
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "3rdparty/cs16client-extras/gfx/czm/shop"
SIZE, C, R, R_IN, HUB = 640, 320, 300, 88, 80


def sector_path(n, i):
    if n == 1:
        # a full ring: two half arcs outside, two inside (even-odd fill)
        return (f"M{C - R} {C} A{R} {R} 0 1 1 {C + R} {C} A{R} {R} 0 1 1 {C - R} {C}Z "
                f"M{C - R_IN} {C} A{R_IN} {R_IN} 0 1 0 {C + R_IN} {C} A{R_IN} {R_IN} 0 1 0 {C - R_IN} {C}Z")
    a0 = math.radians(-90 - 180 / n + i * 360 / n)
    a1 = math.radians(-90 + 180 / n + i * 360 / n)
    big = 1 if 360 / n > 180 else 0
    p0 = (C + R * math.cos(a0), C + R * math.sin(a0))
    p1 = (C + R * math.cos(a1), C + R * math.sin(a1))
    h0 = (C + R_IN * math.cos(a0), C + R_IN * math.sin(a0))
    h1 = (C + R_IN * math.cos(a1), C + R_IN * math.sin(a1))
    return (f"M{h0[0]:.2f} {h0[1]:.2f} L{p0[0]:.2f} {p0[1]:.2f} A{R} {R} 0 {big} 1 {p1[0]:.2f} {p1[1]:.2f} "
            f"L{h1[0]:.2f} {h1[1]:.2f} A{R_IN} {R_IN} 0 {big} 0 {h0[0]:.2f} {h0[1]:.2f}Z")


DEFS = '''<defs><radialGradient id="sel" gradientUnits="userSpaceOnUse" cx="320" cy="320" r="300">
  <stop offset=".25" stop-color="#7f1d1d" stop-opacity=".96"/><stop offset=".75" stop-color="#dc2626" stop-opacity=".96"/>
  <stop offset="1" stop-color="#ef4444" stop-opacity=".98"/></radialGradient>
  <radialGradient id="base" gradientUnits="userSpaceOnUse" cx="320" cy="320" r="300">
  <stop offset=".3" stop-color="#0a0c10" stop-opacity=".93"/><stop offset="1" stop-color="#161a22" stop-opacity=".90"/></radialGradient></defs>'''


def svg(body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">'
            f'{DEFS}{body}</svg>')


def wheel(n):
    sectors = "".join(f'<path d="{sector_path(n, i)}" fill="url(#base)" fill-rule="evenodd" '
                      f'stroke="rgba(255,255,255,.16)" stroke-width="3"/>' for i in range(n))
    return svg(f'''<circle cx="{C}" cy="{C}" r="{R + 12}" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="3"/>
        {sectors}<circle cx="{C}" cy="{C}" r="{HUB}" fill="rgba(18,21,28,.96)" stroke="rgba(255,255,255,.32)" stroke-width="3"/>''')


def highlight(n, i):
    return svg(f'<path d="{sector_path(n, i)}" fill="url(#sel)" fill-rule="evenodd" '
               f'stroke="rgba(255,255,255,.6)" stroke-width="3"/>')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    for n in [int(a) for a in sys.argv[1:]] or range(1, 10):
        jobs.append((f"wheel{n}.png", wheel(n)))
        for i in range(n):
            jobs.append((f"wheel{n}_{i}.png", highlight(n, i)))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": SIZE, "height": SIZE})
        for name, content in jobs:
            page.set_content(f'<html><body style="margin:0;background:transparent">{content}</body></html>')
            page.screenshot(path=str(OUT / name), omit_background=True, clip={"x": 0, "y": 0, "width": SIZE, "height": SIZE})
        browser.close()

    from PIL import Image
    total = 0
    for name, _ in jobs:
        path = OUT / name
        Image.open(path).convert("RGBA").save(path, "PNG", optimize=True)
        total += path.stat().st_size
    print(len(jobs), "images,", total // 1024, "KB in", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
