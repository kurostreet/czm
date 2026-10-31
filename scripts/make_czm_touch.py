#!/usr/bin/env python3
"""Build Counter Zombie Mobile touch buttons: icon textures, layout presets and the editor background.

Icons: most glyphs come from game-icons.net (CC BY 3.0, authors listed in
3rdparty/czm_project/gfx/czm/touch/CREDITS.txt), a few are drawn here.
Every glyph is put on the same round button (dark translucent circle, light
ring; the fire button has a red ring) and rendered with headless Chromium.

usage: make_czm_touch.py --game-icons /path/to/game-icons/icons [--screenshot editor_bg.jpg] [--only fire,jump]
Needs Playwright with Chromium. The output is committed, the Android build does not run this.
"""
import argparse
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRAS = ROOT / "3rdparty/czm_project"
ICON_DIR = EXTRAS / "gfx/czm/touch"
PRESET_DIR = EXTRAS / "touch_presets"
FONT = EXTRAS / "gfx/fonts/czm/InterDisplay-Black.otf"
SIZE = 256

STROKE = 'fill="none" stroke="#fff" stroke-linecap="round" stroke-linejoin="round"'


def svg(body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{body}</svg>'


def chevrons(rotate):
    return svg(f'''<g transform="rotate({rotate} 256 256)"><g {STROKE} stroke-width="56">
        <path d="M136 300l120-120 120 120"/><path d="M136 420l120-120 120 120"/></g>
        <path d="M136 180l120-120 120 120" {STROKE} stroke-width="56" opacity=".45"/></g>''')


DUCK = '''<circle cx="320" cy="126" r="54" fill="#fff"/>
    <g {s} stroke-width="62">
    <path d="M304 214l-70 120"/><path d="M234 334l124 20 6 116"/><path d="M234 334l-68 92H64"/>
    <path d="M298 250l112 18"/></g>
    <path d="M372 252l120-14" {s} stroke-width="36"/>'''.format(s=STROKE)

CUSTOM = {
    # a single cartridge, tilted
    "fire": svg('''<g transform="rotate(40 256 256)" fill="#fff">
        <path d="M256 40c38 40 58 92 58 150H198c0-58 20-110 58-150z"/>
        <rect x="198" y="204" width="116" height="178" rx="10"/>
        <rect x="186" y="394" width="140" height="30" rx="8"/>
        <rect x="198" y="434" width="116" height="40" rx="8"/></g>'''),
    "duck": svg(DUCK),
    "duck_toggle": svg(f'''<g transform="translate(-26 26) scale(.9)">{DUCK}</g>
        <g {STROKE} stroke-width="30"><path d="M372 70a92 92 0 1 1-76 40"/></g>
        <path d="M262 74l58 6-26 52z" fill="#fff"/>'''),
    "forward": chevrons(0),
    "back": chevrons(180),
    "left": chevrons(-90),
    "right": chevrons(90),
    "more": svg('<g fill="#fff"><circle cx="116" cy="256" r="52"/><circle cx="256" cy="256" r="52"/><circle cx="396" cy="256" r="52"/></g>'),
    # break free: four arrows out of the centre
    "unstuck": svg(f'''<g {STROKE} stroke-width="44">
        <path d="M256 196V60"/><path d="M196 120l60-60 60 60"/>
        <path d="M256 316v136"/><path d="M196 392l60 60 60-60"/>
        <path d="M196 256H60"/><path d="M120 196l-60 60 60 60"/>
        <path d="M316 256h136"/><path d="M392 196l60 60-60 60"/></g>
        <circle cx="256" cy="256" r="34" fill="#fff"/>'''),
    # double duck: a crouching figure and a swipe up and down
    "ddrun": svg(f'''<g transform="translate(-40 40) scale(.84)">{DUCK}</g>
        <g {STROKE} stroke-width="34"><path d="M440 92v328"/><path d="M396 136l44-44 44 44"/>
        <path d="M396 376l44 44 44-44"/></g>'''),
}

GAME_ICONS = {
    "scope": "delapouite/crosshair.svg",
    "reload": "delapouite/machine-gun-magazine.svg",
    "use": "skoll/open-palm.svg",
    "rifle": "skoll/ak47.svg",
    "pistol": "skoll/desert-eagle.svg",
    "knife": "skoll/bowie-knife.svg",
    "grenade": "lorc/grenade.svg",
    "lastinv": "delapouite/card-exchange.svg",
    "invnext": "delapouite/clockwise-rotation.svg",
    "invprev": "delapouite/anticlockwise-rotation.svg",
    "drop": "skoll/drop-weapon.svg",
    "flashlight": "delapouite/flashlight.svg",
    "nightvision": "delapouite/steampunk-goggles.svg",
    "spray": "lorc/spray.svg",
    "walk": "skoll/footsteps.svg",
    "autorun": "lorc/run.svg",
    "buy": "delapouite/shopping-cart.svg",
    "ammo1": "sbed/ammo-box.svg",
    "ammo2": "lorc/bullets.svg",
    "autobuy": "delapouite/shopping-bag.svg",
    "rebuy": "lorc/cycle.svg",
    "armor": "skoll/kevlar-vest.svg",
    "chat": "delapouite/chat-bubble.svg",
    "teamchat": "lorc/conversation.svg",
    "voice": "delapouite/microphone.svg",
    "radio": "delapouite/walkie-talkie.svg",
    "score": "delapouite/podium.svg",
    "zpmenu": "delapouite/shambling-zombie.svg",
    "servermenu": "delapouite/hamburger-menu.svg",
    "rs": "lorc/recycle.svg",
    "rtv": "delapouite/vote.svg",
    "top": "delapouite/trophy-cup.svg",
    "rank": "skoll/rank-3.svg",
    "vip": "delapouite/imperial-crown.svg",
    "timeleft": "lorc/hourglass.svg",
    "nextmap": "lorc/treasure-map.svg",
    "cancel": "delapouite/exit-door.svg",
    "team": "delapouite/team-upgrade.svg",
    "screenshot": "delapouite/photo-camera.svg",
    "edit": "lorc/cog.svg",
    "custom": "skoll/click.svg",
    "kill": "lorc/skull-crossed-bones.svg",
}

# glyph from a game icon with a small number badge (radio menus)
BADGED = {"radio1": ("delapouite/walkie-talkie.svg", "1"), "radio2": ("delapouite/walkie-talkie.svg", "2"),
          "radio3": ("delapouite/walkie-talkie.svg", "3")}

# text buttons: menu digits
TEXT = {f"num{d}": str(d) for d in range(10)}
TEXT["numbers"] = "123"


def game_icon(root, name, keep_subpath=None):
    data = (root / name).read_text()
    data = data.replace('<path d="M0 0h512v512H0z"/>', "")
    return data


def jump_icon(root):
    """Leaping figure from game-icons jump-across without the two blocks under it."""
    data = (root / "delapouite/jump-across.svg").read_text()
    d = re.findall(r'<path fill="#fff" d="([^"]+)"', data)[0]
    runner = re.findall(r"[Mm][^Mm]*", d)[0]
    return svg(f'''<g transform="translate(-6 54)"><path fill="#fff" d="{runner}"/></g>
        <path d="M120 470h272" {STROKE} stroke-width="26" opacity=".55"/>''')


def duckjump_icon(root):
    data = jump_icon(root)
    # jump figure with a small crouch chevron under it
    return data.replace("</svg>", f'<path d="M360 360l56 48 56-48" {STROKE} stroke-width="40"/></svg>')


CSS = f'''
@font-face {{ font-family: CzmBlack; src: url("data:font/otf;base64,{{font}}"); }}
* {{ box-sizing: border-box; margin: 0; }}
body {{ background: transparent; }}
.cell {{ position: absolute; width: {SIZE}px; height: {SIZE}px; }}
.btn {{ position: absolute; left: 10px; top: 10px; width: {SIZE - 20}px; height: {SIZE - 20}px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: radial-gradient(circle at 50% 40%, rgba(40,44,52,.66), rgba(10,12,16,.66));
  border: 6px solid rgba(255,255,255,.40); }}
.btn svg {{ width: 56%; height: 56%; filter: drop-shadow(0 4px 4px rgba(0,0,0,.45)); }}
.fire {{ left: 18px; top: 18px; width: {SIZE - 36}px; height: {SIZE - 36}px; border-color: rgba(239,68,68,.97);
  box-shadow: 0 0 22px rgba(239,68,68,.55);
  background: radial-gradient(circle at 50% 40%, rgba(96,24,24,.68), rgba(30,8,8,.68)); }}
.fire svg {{ width: 60%; height: 60%; }}
.txt {{ font-family: CzmBlack; color: #fff; font-size: 104px; letter-spacing: -2px; text-shadow: 0 4px 6px rgba(0,0,0,.45); }}
.txt.small {{ font-size: 70px; }}
.badge {{ position: absolute; right: 30px; bottom: 30px; width: 74px; height: 74px; border-radius: 50%;
  background: #dc2626; border: 4px solid rgba(255,255,255,.9); color: #fff; font-family: CzmBlack; font-size: 46px;
  display: flex; align-items: center; justify-content: center; }}
'''


def build_icons(root, only=None):
    from playwright.sync_api import sync_playwright

    glyphs = dict(CUSTOM)
    glyphs["jump"] = jump_icon(root)
    glyphs["duckjump"] = duckjump_icon(root)
    for key, name in GAME_ICONS.items():
        glyphs[key] = game_icon(root, name)

    cells = []
    names = []
    for key, content in glyphs.items():
        cls = "btn fire" if key == "fire" else "btn"
        cells.append((key, f'<div class="{cls}">{content}</div>'))
    for key, (name, number) in BADGED.items():
        cells.append((key, f'<div class="btn">{game_icon(root, name)}</div><div class="badge">{number}</div>'))
    for key, text in TEXT.items():
        small = " small" if len(text) > 1 else ""
        cells.append((key, f'<div class="btn"><span class="txt{small}">{text}</span></div>'))

    # --only: render just these icons, the others stay as committed
    if only:
        cells = [cell for cell in cells if cell[0] in only]

    html = []
    columns = 8
    for i, (key, inner) in enumerate(cells):
        x, y = ( i % columns ) * SIZE, ( i // columns ) * SIZE
        html.append(f'<div class="cell" id="c_{key}" style="left:{x}px;top:{y}px">{inner}</div>')
        names.append(key)

    font = base64.b64encode(FONT.read_bytes()).decode()
    page_html = f'<html><head><style>{CSS.replace("{font}", font)}</style></head><body>{"".join(html)}</body></html>'
    rows = ( len(cells) + columns - 1 ) // columns

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": columns * SIZE, "height": rows * SIZE})
        page.set_content(page_html)
        page.wait_for_timeout(200)
        for key in names:
            page.locator(f"#c_{key}").screenshot(path=str(ICON_DIR / f"{key}.png"), omit_background=True)
        browser.close()

    # Chromium writes big files, recompress them
    from PIL import Image
    for key in names:
        path = ICON_DIR / f"{key}.png"
        Image.open(path).convert("RGBA").save(path, "PNG", optimize=True)
    print(len(names), "icons in", ICON_DIR.relative_to(ROOT))
    return names


"""
Layout presets. Positions are centres and diameters in a 2000 x 932 reference
screen (the owner's screenshot). Round buttons keep their shape on any phone:
touch_addbutton gets aspect 1, the engine recomputes the height.
"""
REF_W, REF_H = 2000.0, 932.0
# hidden, and saved hidden even after "More" showed them in the match
HIDE = 1 | 64

# name, icon, command, centre x, centre y, diameter, flags
COMMON_HIDDEN = [
    ("more_teamchat", "teamchat", "messagemode2", 520, 110, 72),
    ("more_radio", "radio", "showvguimenu 38", 610, 110, 72),
    ("more_nightvision", "nightvision", "nightvision", 700, 110, 72),
    ("more_drop", "drop", "drop", 790, 110, 72),
    ("more_team", "team", "chooseteam", 880, 110, 72),
    ("more_numbers", "numbers", "exec touch_default/numbers.cfg", 970, 110, 72),
    ("more_edit", "edit", "menu_czmtouch", 1060, 110, 72),
    ("more_cancel", "cancel", "cancelselect", 1150, 110, 72),
]

LAYOUTS = {
    # 1: classic, the layout shown to the owner
    1: [
        ("fire_left", "fire", "+attack", 150, 420, 120),
        ("fire", "fire", "+attack", 1700, 620, 180),
        ("scope", "scope", "+attack2", 1540, 455, 110),
        ("jump", "jump", "+jump", 1880, 470, 112),
        ("duck", "duck", "+duck", 1880, 790, 112),
        ("reload", "reload", "+reload", 1530, 790, 104),
        ("use", "use", "+use", 1380, 640, 96),
        ("w1", "rifle", "slot1", 1890, 250, 92),
        ("w2", "pistol", "slot2", 1780, 250, 92),
        ("w3", "knife", "slot3", 1670, 250, 92),
        ("w4", "grenade", "slot4", 1560, 250, 92),
        ("more", "more", "czm_more", 160, 110, 72),
        ("score", "score", "+showscores", 250, 110, 72),
        ("chat", "chat", "messagemode", 340, 110, 72),
        ("voice", "voice", "+voicerecord", 430, 110, 72),
        ("flashlight", "flashlight", "impulse 100", 70, 300, 76),
        ("buy", "buy", "buy", 1240, 820, 84),
        ("spray", "spray", "impulse 201", 1110, 840, 72),
        ("autorun", "autorun", "czm_autorun", 420, 470, 84),
    ],
    # 2: PUBG-like: big left fire, weapons at the bottom centre
    2: [
        ("fire_left", "fire", "+attack", 190, 360, 150),
        ("fire", "fire", "+attack", 1650, 560, 170),
        ("scope", "scope", "+attack2", 1860, 330, 112),
        ("jump", "jump", "+jump", 1860, 560, 112),
        ("duck", "duck_toggle", "crouchtoggle", 1870, 800, 112),
        ("reload", "reload", "+reload", 1680, 800, 100),
        ("use", "use", "+use", 1440, 520, 96),
        ("w1", "rifle", "slot1", 800, 860, 92),
        ("w2", "pistol", "slot2", 910, 860, 92),
        ("w3", "knife", "slot3", 1020, 860, 92),
        ("w4", "grenade", "slot4", 1130, 860, 92),
        ("more", "more", "czm_more", 160, 110, 72),
        ("score", "score", "+showscores", 250, 110, 72),
        ("chat", "chat", "messagemode", 340, 110, 72),
        ("voice", "voice", "+voicerecord", 430, 110, 72),
        ("flashlight", "flashlight", "impulse 100", 1890, 110, 76),
        ("buy", "buy", "buy", 1790, 110, 76),
        ("spray", "spray", "impulse 201", 1690, 110, 72),
        ("lastinv", "lastinv", "lastinv", 1250, 860, 84),
        ("walk", "walk", "+speed", 400, 600, 84),
    ],
    # 3: minimum for zombie modes
    3: [
        ("fire", "fire", "+attack", 1690, 600, 190),
        ("scope", "scope", "+attack2", 1520, 430, 110),
        ("jump", "jump", "+jump", 1880, 440, 116),
        ("duck", "duck", "+duck", 1880, 790, 116),
        ("reload", "reload", "+reload", 1500, 790, 104),
        ("use", "use", "+use", 1360, 620, 96),
        ("lastinv", "lastinv", "lastinv", 1840, 250, 92),
        ("more", "more", "czm_more", 160, 110, 72),
        ("score", "score", "+showscores", 250, 110, 72),
        ("flashlight", "flashlight", "impulse 100", 70, 300, 76),
        ("buy", "buy", "buy", 1240, 820, 84),
    ],
}


def button_line(name, icon, command, cx, cy, d, flags=0, alpha=255):
    x1, x2 = ( cx - d / 2 ) / REF_W, ( cx + d / 2 ) / REF_W
    y1, y2 = ( cy - d / 2 ) / REF_H, ( cy + d / 2 ) / REF_H
    return (f'touch_addbutton "{name}" "gfx/czm/touch/{icon}" "{command}" '
            f'{x1:.6f} {y1:.6f} {x2:.6f} {y2:.6f} 255 255 255 {alpha} {flags} 1\n')


# A layout made in the game and shared with "Share my layout" becomes the default of its scheme:
# scripts/layouts/scheme<N>.json. Round buttons get the aspect 1, so the engine keeps them round
# on any screen; the positions stay shares of the screen. The HUD part is the default in
# common/czm_hud_layout.h (tests/test_default_layout.py keeps both in step).
LAYOUT_FILES = ROOT / "scripts/layouts"


def owner_preset(number):
    import json

    path = LAYOUT_FILES / f"scheme{number}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    lines = [
        "// Counter Zombie Mobile touch layout, scheme %d (made in the game, scripts/layouts/scheme%d.json)\n" % (number, number),
        "touch_set_stroke 0 0 0 0 0\n",
        "touch_highlight_r \"1\"\ntouch_highlight_g \"0.4\"\ntouch_highlight_b \"0.4\"\ntouch_highlight_a \"1\"\n",
        "touch_setclientonly 0\n",
        "touch_removeall\n",
    ]
    for name, texture, command, x1, y1, x2, y2, r, g, b, a, flags in data["layouts"][str(number)]:
        round_button = texture and not texture.startswith("#")
        lines.append(f'touch_addbutton "{name}" "{texture}" "{command}" {x1:.6f} {y1:.6f} {x2:.6f} {y2:.6f} '
                     f'{r} {g} {b} {a} {flags}' + (" 1\n" if round_button else "\n"))
    return lines


def build_presets():
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    for number, buttons in LAYOUTS.items():
        owner = owner_preset(number)
        if owner:
            path = PRESET_DIR / f"czm_scheme{number}.cfg"
            path.write_text("".join(owner))
            print(path.relative_to(ROOT), len(owner) - 5, "buttons from", LAYOUT_FILES.name)
            continue
        lines = [
            "// Counter Zombie Mobile touch layout, scheme %d (generated by scripts/make_czm_touch.py)\n" % number,
            "touch_set_stroke 0 0 0 0 0\n",
            "touch_highlight_r \"1\"\ntouch_highlight_g \"0.4\"\ntouch_highlight_b \"0.4\"\ntouch_highlight_a \"1\"\n",
            "touch_setclientonly 0\n",
            "touch_removeall\n",
            # movement and look zones: left and right half of the screen
            'touch_addbutton "move" "" "_move" 0.000000 0.000000 0.500000 1.000000 255 255 255 255 0\n',
            'touch_addbutton "look" "" "_look" 0.500000 0.000000 1.000000 1.000000 255 255 255 255 0\n',
        ]
        for name, icon, command, cx, cy, d in buttons:
            lines.append(button_line(name, icon, command, cx, cy, d))
        for name, icon, command, cx, cy, d in COMMON_HIDDEN:
            lines.append(button_line(name, icon, command, cx, cy, d, HIDE))
        path = PRESET_DIR / f"czm_scheme{number}.cfg"
        path.write_text("".join(lines))
        print(path.relative_to(ROOT), len(buttons) + len(COMMON_HIDDEN), "buttons")


# The stock HUD, chat lines and radar of the screenshot, as shares of the picture (x1, y1, x2, y2).
# The editor draws our own HUD blocks over it, old numbers under them would only confuse.
STOCK_HUD = [(0, 0, .075, .105), (0, 0, .09, .02), (0, .455, .02, .505), (0, .86, .215, .945), (0, .955, .04, .995),
             (.19, .955, .235, .995), (.935, .935, 1, 1), (.475, .96, .53, 1), (.97, 0, 1, .04)]


def build_background(screenshot):
    import cv2
    import numpy
    from PIL import Image

    image = Image.open(screenshot).convert("RGB")
    image = image.resize((1600, round(1600 * image.height / image.width)), Image.LANCZOS)
    pixels = numpy.array(image)
    mask = numpy.zeros(pixels.shape[:2], numpy.uint8)
    h, w = mask.shape
    for x1, y1, x2, y2 in STOCK_HUD:
        mask[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)] = 255
    image = Image.fromarray(cv2.inpaint(pixels, mask, 9, cv2.INPAINT_TELEA))
    path = EXTRAS / "gfx/czm/ui/editor_bg.png"
    image.save(path, "PNG", optimize=True)
    print(path.relative_to(ROOT), image.size, path.stat().st_size, "bytes")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-icons", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--only", help="comma-separated icon names to render")
    args = parser.parse_args()
    build_icons(args.game_icons, set(args.only.split(",")) if args.only else None)
    build_presets()
    if args.screenshot:
        build_background(args.screenshot)


if __name__ == "__main__":
    main()
