#!/usr/bin/env python3
"""Puts the Survival maps, their files and the Kontra sounds on the game server and its FastDL.

Runs as root on the game host:

    python3 -I install_content.py SRC_DIR GAME_DIR FASTDL_DIR

SRC_DIR holds kontra-content.zip (the owner's maps and sounds) and gb/ with the original map
archives from GameBanana (wads, skies, models the maps need). Only our own files are written:
none of them shares a name with a stock file. Each map that needs a file the game does not ship gets a
maps/<map>.res, so players download it with the map. Then render_models.py draws the panel's pictures
of the skins and knives into FASTDL_DIR/czm-art/ (served as /zm-test-files/czm-art/).
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

# Knives and human skins of the LVL MOD shop (GameBanana, see CREDITS.md). Knives go under
# models/czm_survival/, skins under models/player/czm_<skin>/ (with the <name>T.mdl texture file when
# the model has one), so none of them replaces a stock model for other servers' players.
def _skin(name):
    return f"models/player/czm_{name}/czm_{name}.mdl", f"models/player/czm_{name}/czm_{name}T.mdl"


MODELS = [
    ("221799_*", r"models/v_knife\.mdl$", "models/czm_survival/v_katana.mdl"),
    ("221665_*", r"Texture/Gold/models/v_knife\.mdl$", "models/czm_survival/v_axe.mdl"),
    ("221665_*", r"Texture/Gold/models/p_knife\.mdl$", "models/czm_survival/p_axe.mdl"),
    ("440810_*", r"models/v_knife\.mdl$", "models/czm_survival/v_glass.mdl"),
    ("221794_*", r"^v_knife\.mdl$", "models/czm_survival/v_sickle.mdl"),
    ("227488_*", r"(?:^|/)gsg9\.mdl$", _skin("gsg9_admin")[0]),
    ("228591_*v1-1*", r"models/sas/sas\.mdl$", _skin("sas_custom")[0]),
    ("224534_*", r"models/leet/leet\.mdl$", _skin("leet_pirate")[0]),
    ("224534_*", r"models/leet/leetT\.mdl$", _skin("leet_pirate")[1]),
    ("225588_cs_16_*", r"Professionals/leet/leet\.mdl$", _skin("professional")[0]),  # variant 2: sunglasses
    ("494736_*", r"models/player/urban/urban\.mdl$", _skin("survivor")[0]),
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

# What the team menu shows about a map (maps/<map>.txt, downloaded with the map), Russian then English
MAP_INFO = {
    "zm_3rooms": ("Три комнаты - три рубежа обороны. Держитесь вместе и отступайте по очереди.",
                  "Three rooms, three lines of defence. Stick together and fall back one by one."),
    "zm_ark_bhzrdbase_v2": ("База Biohazard в версии Ark: коридоры, ангары и лестницы наверх.",
                            "Ark's Biohazard base: corridors, hangars and stairs up."),
    "zm_ark_deko2_v1": ("Ночной deko2 в версии Ark: темно, следите за спиной.",
                        "Ark's deko2 at night: it is dark, watch your back."),
    "zm_battleground_extreme": ("Поле боя в тумане: длинные линии огня, лестницы и высоты.",
                                "A battleground in the fog: long lines of fire, stairs and high ground."),
    "zm_bhzrd_base_rmk": ("Ремейк Biohazard Base: колонны, мостки и узкие проходы.",
                          "Biohazard Base remade: pillars, walkways and narrow passages."),
    "zm_biohazard_base_mx": ("Biohazard Base: тесные коридоры и комнаты для обороны.",
                             "Biohazard Base: tight corridors and rooms to hold."),
    "zm_chatoyant": ("Открытая карта с бункерами под пасмурным небом.",
                     "An open map with bunkers under a grey sky."),
    "zm_cubeworld_mini": ("Маленький кубический мир: всё рядом, бой с первых секунд.",
                          "A small cube world: everything is close, the fight starts at once."),
    "zm_defense": ("Двор с ящиками и баррикадами: занимайте углы и держите оборону.",
                   "A yard of crates and barricades: take the corners and hold."),
    "zm_deko2": ("Песчаный городок deko2: улицы, дома и крыши.",
                 "The sandy town of deko2: streets, houses and roofs."),
    "zm_dust_world_summer_f": ("Летний Dust World: мосты над улицами и высокие точки.",
                               "Dust World in summer: bridges over the streets and high spots."),
    "zm_ground_sg": ("Площадки и стеклянные стены вокруг центрального блока.",
                     "Platforms and glass walls around a central block."),
    "zm_mini_re": ("Маленькая деревня с домиками и деревьями.",
                   "A small village of huts and trees."),
    "zm_mnx_summer": ("Летняя карта с пальмами, мостками и водой.",
                      "A summer map of palms, walkways and water."),
    "zm_ntc_water_fall": ("Водопад под космическим небом: уступы и деревянные мостки.",
                          "A waterfall under a space sky: ledges and wooden walkways."),
    "zm_sln_mariozomb": ("Карта в стиле Марио: трубы, кирпичи и платформы.",
                         "A Mario-style map: pipes, bricks and platforms."),
    "zm_tc_death": ("Бетонная арена в тумане: центральная площадка и проходы вокруг.",
                    "A concrete arena in the fog: a central platform and passages around it."),
    "zm_zombust": ("Песчаный Dust для зомби: ящики, арки и узкие улицы.",
                   "A sandy Dust for zombies: crates, arches and narrow streets."),
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

        models = os.path.join(src, "models", "gb")
        for archive in sorted(os.listdir(models)) if os.path.isdir(models) else []:
            rules = [r for r in MODELS if re.fullmatch(r[0].replace("*", ".*"), archive)]
            if not rules:
                continue
            unpack = os.path.join(tmp, "model-" + archive)
            os.makedirs(unpack)
            subprocess.run(["bsdtar", "-xf", os.path.join(models, archive), "-C", unpack], check=True)
            for root, _, files in os.walk(unpack):
                for f in files:
                    member = os.path.relpath(os.path.join(root, f), unpack).replace(os.sep, "/")
                    for _, pattern, target in rules:
                        if re.search(pattern, member):
                            placed.append(place(os.path.join(root, f), target, cstrike, fastdl, owner))

    for name in MAPS:
        ru, en = MAP_INFO[name]
        info = (f"{name}\n\n{ru}\nmenu - меню сервера, lvl - уровень и магазин.\n\n"
                f"{en}\nmenu - server menu, lvl - level and shop.\n")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            fh.write(info)
        placed.append(place(fh.name, f"maps/{name}.txt", cstrike, fastdl, owner))
        os.unlink(fh.name)

    for name in MAPS:
        items = RES.get(name, [])
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
        lines.append(f"maps/{name}.txt")
        body = "// Files players download with this map\n" + "\n".join(lines) + "\n"
        for root in (cstrike, fastdl):
            path = os.path.join(root, "maps", name + ".res")
            with open(path, "w") as fh:
                fh.write(body)
            os.chown(path, *owner)

    # the panel's pictures of the skins and knives, drawn from these models at the lowest priority
    art = os.path.join(fastdl, "czm-art")
    subprocess.run(["nice", "-n", "19", sys.executable, "-I", os.path.join(HERE, "render_models.py"), cstrike, art],
                   check=False)
    for root, dirs, files in os.walk(art):
        for f in dirs + files:
            os.chown(os.path.join(root, f), *owner)

    missing = [m for m in MAPS if not os.path.exists(os.path.join(cstrike, "maps", m + ".bsp"))]
    print(f"placed {len(placed)} files; maps missing: {missing or 'none'}")
    print(json.dumps({"maps": MAPS}))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
