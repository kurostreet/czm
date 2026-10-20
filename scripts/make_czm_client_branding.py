#!/usr/bin/env python3
"""Replace the client's legacy BMP artwork using the existing CZM art and fonts."""
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "3rdparty/cs16client-extras"
FONT = ART / "gfx/fonts/czm/Inter-SemiBold.otf"
LABELS = (
    "New game", "Resume", "Training", "Settings", "Load game", "Save / load",
    "Game guide", "Quit", "Multiplayer", "Easy", "Medium", "Difficult",
    "Save game", "Load game", "Cancel", "Game options", "Video", "Audio",
    "Controls", "Done", "Quick start", "Defaults", "OK", "Video options",
    "Video modes", "Advanced", "Game website", "Delete", "Play online",
    "Chat rooms", "Play on LAN", "Customize", "Skip", "Exit", "Connect",
    "Refresh", "Filter", "Filter", "Create", "Create game", "Chat rooms",
    "List rooms", "Search", "Servers", "Join", "Find", "Create room",
    "Join game", "Search games", "Find game", "Start game", "Server info",
    "Check updates", "Add server", "Disconnect", "Console", "Content controls",
    "Check updates", "Game website", "Game guide", "Advanced", "Renderer info",
    "Custom game", "Activate", "Install", "Visit website", "Refresh list",
    "Deactivate", "Advanced", "Spectate game", "Spectate games",
)


def text(image, label, box, color, size):
    font = ImageFont.truetype(str(FONT), size)
    draw = ImageDraw.Draw(image)
    while draw.textlength(label, font=font) > box[2] - box[0] - 8:
        size -= 1
        font = ImageFont.truetype(str(FONT), size)
    draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), label,
              font=font, fill=color, anchor="mm")


def main():
    # The engine consumes three 26px states per button in the Btns.h order.
    header = (ROOT / "3rdparty/mainui_cpp/Btns.h").read_text()
    enum = header.split("enum EDefaultBtns", 1)[1].split("PC_BUTTONCOUNT", 1)[0]
    assert len(re.findall(r"\bPC_[A-Z0-9_]+\b", enum)) == len(LABELS) == 71
    buttons = Image.new("RGB", (156, len(LABELS) * 78))
    for index, label in enumerate(LABELS):
        for state, color in enumerate(((222, 229, 239), (255, 86, 96), (163, 176, 194))):
            y = index * 78 + state * 26
            text(buttons, label, (0, y, 156, y + 26), color, 16)
    buttons.save(ART / "gfx/shell/btns_main.bmp")

    multiplayer = Image.new("RGB", (460, 80))
    text(multiplayer, "Multiplayer", (0, 0, 460, 76), (232, 237, 246), 44)
    ImageDraw.Draw(multiplayer).line((80, 76, 380, 76), fill=(232, 62, 76), width=2)
    multiplayer.save(ART / "gfx/shell/head_multi.bmp")

    background = Image.open(ART / "gfx/czm/loading_3.png").convert("RGB")
    splash = ImageOps.fit(background, (640, 480), method=Image.Resampling.LANCZOS)
    title = ImageOps.contain(Image.open(ART / "gfx/czm/title.png").convert("RGBA"), (550, 110))
    splash.paste(title, ((640 - title.width) // 2, 20), title)
    splash.save(ART / "gfx/shell/splash.bmp")
    print("Client splash, multiplayer heading and 71 button labels use CZM artwork")


if __name__ == "__main__":
    main()
