#!/usr/bin/env python3
"""Inspect or export UI replacements using the same artwork builder as the server."""
import argparse
import importlib.util
from pathlib import Path
import zipfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "3rdparty/czm_project"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="Optional ZIP for a local artwork inspection")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("czm_ui_art", ROOT / "server/czm/czm/ui_art.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    images = {"background": Image.open(ART / "gfx/czm/loading_3.png").convert("RGB"),
              "title": Image.open(ART / "gfx/czm/title.png").convert("RGBA"),
              "logo": Image.open(ART / "logos/czm_logo.png").convert("RGBA")}
    entries = module.make_entries(**images)
    if args.output:
        with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, contents in sorted(entries.items()):
                archive.writestr(name, contents)
    print(len(entries), "original UI replacements")

if __name__ == "__main__":
    main()
