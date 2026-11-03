#!/usr/bin/env python3
"""Puts the Survival maps, their files and the Kontra sounds on the game server and its FastDL.

Runs as root on the game host:

    python3 -I install_content.py SRC_DIR GAME_DIR FASTDL_DIR

SRC_DIR holds kontra-content.zip (the owner's maps and sounds) and gb/ with the original map
archives from GameBanana (wads, skies, models the maps need). Only our own files are written:
none of them shares a name with a stock file. Each map that needs a file the game does not ship gets a
maps/<map>.res, so players download it with the map.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bsp_entities  # noqa: E402
import prepare_content  # noqa: E402

# (archive file, member path regex, target path; \1 is the member's file name)
EXTRAS = [
    ("87996_*", r"cstrike/gfx/env/(zp_riverside\w+\.tga)$", r"gfx/env/\1"),
    ("87996_*", r"cstrike/sprites/(light\.spr)$", r"sprites/\1"),
    ("88165_*", r"gfx/env/(mixarena\w+\.tga)$", r"gfx/env/\1"),
    ("88204_*", r"cstrike/(zm_deko2\.wad)$", r"\1"),
    ("88717_*", r"gfx/env/(skybox15_\w+\.tga)$", r"gfx/env/\1"),
    ("88717_*", r"models/zm_mnx_summer/(palm\.mdl)$", r"models/zm_mnx_summer/\1"),
    ("88777_*", r"zm_ntc_water_fall/(headshot\.wad)$", r"\1"),
    ("88943_*", r"mariozombs/(?i:silezn\.wad)$", r"silezn.wad"),
    ("88943_*", r"Sound/sLn_sound/(\w+\.wav)$", r"sound/sLn_sound/\1"),
    ("99178_*", r"models/zm_dust_world/((?:TV_plasma|Vending_machine|re_deadguy_1|re_deadguy_3)\.mdl)$",
     r"models/zm_dust_world/\1"),
]

# Decorations whose files were never published with the map, and skies nobody has: the map is
# loaded without them (the server refuses a map whose model is missing).
MAP_EDITS = {
    "zm_dust_world_summer_f.bsp": {"drop": ["models/otherworld/", "sprites/otherworld/"], "sky": "night"},
    "zm_zombust.bsp": {"drop": [], "sky": "desert"},
}

SIDES = ("bk", "dn", "ft", "lf", "rt", "up")
RES = {
    "zm_battleground_extreme": ["sky:zp_riverside"],
    "zm_bhzrd_base_rmk": ["sky:mixarena"],
    "zm_cubeworld_mini": ["sky:mixarena"],
    "zm_mnx_summer": ["sky:skybox15_"],
    "zm_defense": ["sky:DrkG"],
    "zm_deko2": ["zm_deko2.wad"],
    "zm_ntc_water_fall": ["headshot.wad"],
    "zm_sln_mariozomb": ["silezn.wad"],
}

MAPS = ["zm_3rooms", "zm_ark_bhzrdbase_v2", "zm_ark_deko2_v1", "zm_battleground_extreme", "zm_bhzrd_base_rmk",
        "zm_biohazard_base_mx", "zm_chatoyant", "zm_cubeworld_mini", "zm_defense", "zm_deko2",
        "zm_dust_world_summer_f", "zm_ground_sg", "zm_mini_re", "zm_mnx_summer", "zm_ntc_water_fall",
        "zm_sln_mariozomb", "zm_tc_death", "zm_zombust"]


def place(src, rel, game, fastdl, owner):
    """Copies one of our files into the game and FastDL (a newer copy replaces an older one)."""
    for root in (game, fastdl):
        dst = os.path.join(root, rel)
        if os.path.exists(dst) and os.path.samefile(src, dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst + ".part")
        os.chmod(dst + ".part", 0o644)
        if owner:
            os.chown(dst + ".part", *owner)
        os.replace(dst + ".part", dst)
    return rel


def main(src, game, fastdl):
    cstrike = os.path.join(game, "cstrike")
    st = os.stat(cstrike)
    owner = (st.st_uid, st.st_gid)
    placed = []
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out")
        prepare_content.main(os.path.join(src, "kontra-content.zip"), out)

        for name, edit in MAP_EDITS.items():
            path = os.path.join(out, "maps", name)
            data, lumps = bsp_entities.read(path)
            off, length = lumps[0]
            text = data[off:off + length].rstrip(b"\0").decode("latin1")
            text, removed = bsp_entities.edit(text, edit["drop"], edit["sky"])
            bsp_entities.write(path, data, lumps, text.encode("latin1") + b"\0")
            print(f"{name}: removed {removed} entities, sky {edit['sky']}")

        for name in sorted(os.listdir(os.path.join(out, "maps"))):
            problem = bsp_entities.check(open(os.path.join(out, "maps", name), "rb").read())
            if problem:
                raise SystemExit(f"{name} would not load on the server: {problem}")

        for root, _, files in os.walk(out):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), out)
                if rel == "survival_sounds.json":
                    continue
                placed.append(place(os.path.join(root, f), rel, cstrike, fastdl, owner))

        configs = os.path.join(cstrike, "addons", "amxmodx", "configs", "survival_sounds.json")
        shutil.copyfile(os.path.join(out, "survival_sounds.json"), configs)
        os.chown(configs, *owner)
        os.chmod(configs, 0o644)

        gb = os.path.join(src, "gb")
        for archive in sorted(os.listdir(gb)):
            rules = [r for r in EXTRAS if re.fullmatch(r[0].replace("*", ".*"), archive)]
            if not rules:
                continue
            unpack = os.path.join(tmp, "gb-" + archive)
            os.makedirs(unpack)
            subprocess.run(["bsdtar", "-xf", os.path.join(gb, archive), "-C", unpack], check=True)
            for root, _, files in os.walk(unpack):
                for f in files:
                    member = os.path.relpath(os.path.join(root, f), unpack).replace(os.sep, "/")
                    for _, pattern, target in rules:
                        m = re.search(pattern, member)
                        if m:
                            placed.append(place(os.path.join(root, f), m.expand(target), cstrike, fastdl, owner))

    for name, items in RES.items():
        lines = []
        for item in items:
            if item.startswith("sky:"):
                lines += [f"gfx/env/{item[4:]}{side}.tga" for side in SIDES]
            else:
                lines.append(item)
        for line in lines:
            # a sky the game ships elsewhere (DrkG lives in cstrike already) still goes to FastDL
            have = os.path.join(cstrike, line)
            if os.path.exists(have) and not os.path.exists(os.path.join(fastdl, line)):
                place(have, line, cstrike, fastdl, owner)
        body = "// Files players download with this map\n" + "\n".join(lines) + "\n"
        for root in (cstrike, fastdl):
            path = os.path.join(root, "maps", name + ".res")
            with open(path, "w") as fh:
                fh.write(body)
            os.chown(path, *owner)

    missing = [m for m in MAPS if not os.path.exists(os.path.join(cstrike, "maps", m + ".bsp"))]
    print(f"placed {len(placed)} files; maps missing: {missing or 'none'}")
    print(json.dumps({"maps": MAPS}))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
