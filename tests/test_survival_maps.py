"""Map edits for the Survival server keep every entity the server reads, braces in values included."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server/zm/tools"))
import bsp_entities  # noqa: E402

ENTITIES = (
    '{\n"classname" "worldspawn"\n"skyname" "cl_desert"\n}\n'
    '{\n"texture" "{bloodhand2"\n"classname" "infodecal"\n}\n'
    '{\n"model" "models/otherworld/table.mdl"\n"classname" "cycler_sprite"\n}\n'
    '{\n"model" "models/zm_dust_world/TV_plasma.mdl"\n"classname" "cycler_sprite"\n}\n'
)


def bsp(entities: str) -> bytes:
    body = entities.encode("latin1") + b"\0"
    other = b"PLANES--"
    header = struct.pack("<i", 30) + struct.pack("<ii", 4 + 8 * 15, len(body))
    pos = 4 + 8 * 15 + len(body) + (-len(body) % 4)
    for _ in range(14):
        header += struct.pack("<ii", pos, len(other))
    return header + body + b"\0" * (-len(body) % 4) + other


class SurvivalMapTests(unittest.TestCase):
    def test_decal_names_with_braces_survive_an_edit(self):
        data = bsp(ENTITIES)
        off, length = struct.unpack_from("<ii", data, 4)
        text = data[off:off + length].rstrip(b"\0").decode("latin1")
        edited, removed = bsp_entities.edit(text, ["models/otherworld/"], "desert")
        self.assertEqual(removed, 1)
        self.assertIn('"texture" "{bloodhand2"', edited)
        self.assertIn('"skyname" "desert"', edited)
        self.assertIn("TV_plasma", edited)
        self.assertEqual(bsp_entities.check(bsp(edited)), "")

    def test_the_server_parser_rejects_a_broken_entity_list(self):
        broken = ENTITIES.replace('{\n"texture" "{bloodhand2"\n', '{bloodhand2"\n')
        self.assertIn("closing brace without data", bsp_entities.check(bsp(broken)))
        self.assertEqual(bsp_entities.check(bsp(ENTITIES)), "")


if __name__ == "__main__":
    unittest.main()
