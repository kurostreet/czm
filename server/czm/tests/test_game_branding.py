"""Release resources replace legacy UI art without changing maps, models or fonts."""
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from czm.game_branding import DATA, META, OVERLAY, WAD_ENTRY, game_resources, replace_wad_logos


def zipped(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, contents in entries.items():
            archive.writestr(name, contents)
    return stream.getvalue()


def wad(entries):
    body, directory = bytearray(), bytearray()
    for name, contents in entries.items():
        directory.extend(WAD_ENTRY.pack(12 + len(body), len(contents), len(contents), 66, 0, 0, 0, name.encode()))
        body.extend(contents)
    return struct.pack("<4sii", b"WAD3", len(entries), 12 + len(body)) + body + directory


def wad_lumps(data):
    _, count, directory = struct.unpack_from("<4sii", data)
    result = {}
    for i in range(count):
        offset, size, _, _, _, _, _, raw = WAD_ENTRY.unpack_from(data, directory + i * WAD_ENTRY.size)
        result[raw.split(b"\0", 1)[0].decode()] = data[offset:offset + size]
    return result


class GameBrandingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.art = {f"{g}/{n}": b"our background" for g in ("valve", "cstrike")
                    for n in ("cached.wad", "gfx/conback.lmp")}
        self.art.update({"valve/gfx/lambda.lmp": b"our logo", "cstrike/gfx/vgui/CS_logo.tga": b"our title"})
        self.game = {"cstrike/maps/de_test.bsp": b"map bytes", "cstrike/models/p_test.mdl": b"model bytes",
                     "valve/cached.wad": b"old UI", "cstrike/cached.wad": b"old UI",
                     "valve/gfx/conback.lmp": b"old UI", "cstrike/gfx/vgui/CS_logo.tga": b"old UI",
                     "valve/gfx.wad": wad({"LAMBDA": b"old UI", "CONCHARS": b"original font"}),
                     "cstrike/liblist.gam": b'game "Counter-Strike"\ngamedll "dlls/test.so"\n'}
        self.pack = zipped(self.game)
        self.meta = {"format": 1, "sha256": hashlib.sha256(self.pack).hexdigest(), "files": len(self.game),
                     "unpacked_bytes": sum(map(len, self.game.values())),
                     "required": [{"path": "cstrike/maps/de_test.bsp", "bytes": len(b"map bytes")}]}
        self.data = zipped({DATA: self.pack, META: json.dumps(self.meta).encode()})

    def resources(self, prefix="assets/", art=None):
        return zipfile.ZipFile(io.BytesIO(zipped({prefix + OVERLAY: zipped(self.art if art is None else art)})))

    def converted(self, prefix="assets/"):
        with zipfile.ZipFile(io.BytesIO(self.data)) as data, self.resources(prefix) as core:
            with game_resources(data, core, self.root, prefix) as entries:
                return {name: path.read_bytes() for name, path, _ in entries}

    def test_art_is_replaced_and_gameplay_fonts_integrity_metadata_are_preserved(self):
        converted = self.converted()
        meta = json.loads(converted[META])
        with zipfile.ZipFile(io.BytesIO(converted[DATA])) as game:
            self.assertEqual(game.testzip(), None)
            self.assertEqual(game.read("cstrike/maps/de_test.bsp"), b"map bytes")
            self.assertEqual(game.read("cstrike/models/p_test.mdl"), b"model bytes")
            self.assertEqual(game.read("valve/gfx/conback.lmp"), b"our background")
            self.assertEqual(game.read("cstrike/gfx/vgui/cs_logo.tga"), b"our title")
            self.assertNotIn("cstrike/gfx/vgui/CS_logo.tga", game.namelist())
            self.assertEqual(wad_lumps(game.read("valve/gfx.wad")), {"LAMBDA": b"our logo", "CONCHARS": b"original font"})
            self.assertIn(b'game "Counter Zombie Mobile"', game.read("cstrike/liblist.gam"))
            self.assertIn(b'gamedll "dlls/test.so"', game.read("cstrike/liblist.gam"))
            self.assertEqual(meta["files"], len(game.namelist()))
            self.assertEqual(meta["unpacked_bytes"], sum(i.file_size for i in game.infolist()))
        self.assertEqual(meta["sha256"], hashlib.sha256(converted[DATA]).hexdigest())
        self.assertEqual(meta["required"], self.meta["required"])
        self.assertFalse(list(self.root.iterdir()))

    def test_site_and_play_resources_match_and_repeated_packaging_reuses_the_clean_pack(self):
        site, play = self.converted(), self.converted("base/assets/")
        self.assertEqual(site, play)
        clean = zipped(site)
        with zipfile.ZipFile(io.BytesIO(clean)) as data, self.resources() as core:
            with game_resources(data, core, self.root) as entries:
                self.assertTrue(all(path is None for _, path, _ in entries))
        self.assertFalse(list(self.root.iterdir()))

    def test_older_cores_can_still_be_repackaged(self):
        with zipfile.ZipFile(io.BytesIO(self.data)) as data, zipfile.ZipFile(io.BytesIO(zipped({}))) as core:
            with game_resources(data, core, self.root) as entries:
                self.assertEqual(entries, [(DATA, None, len(self.pack)), (META, None, len(json.dumps(self.meta).encode()))])

    def test_invalid_overlay_or_wad_stops_packaging(self):
        for entries in ({"../escape": b"no"}, {"valve/gfx/conback.lmp": b"incomplete"}):
            with zipfile.ZipFile(io.BytesIO(self.data)) as data, self.resources(art=entries) as core:
                with self.assertRaises(ValueError), game_resources(data, core, self.root):
                    pass
        for contents in (b"", b"WAD3" + b"\xff" * 8, wad({"LAMBDA": b"logo"})[:-1]):
            with self.assertRaises(ValueError):
                replace_wad_logos(contents, self.art, "valve")

    def test_both_signed_package_inputs_get_clean_resources(self):
        # Integration needs the service dependencies; the same test runs on the server and in CI.
        try:
            from czm import assemble, play
        except ModuleNotFoundError as error:
            self.skipTest(str(error))
        data = self.root / "old.apk"
        data.write_bytes(self.data)
        overlay = zipped(self.art)
        for kind in ("apk", "aab"):
            core = self.root / ("core." + kind)
            out = self.root / ("out." + kind)
            if kind == "apk":
                core.write_bytes(zipped({"AndroidManifest.xml": b"base", "assets/" + OVERLAY: overlay}))
                assemble.combine(core, data, out)
                prefix = ""
            else:
                core.write_bytes(zipped({"BundleConfig.pb": b"cfg", play.PACK_MANIFEST: b"pack",
                                         "gamedata/assets.pb": b"assets/bundled", "base/assets/" + OVERLAY: overlay}))
                play.combine(core, data, out)
                prefix = "gamedata/"
            with zipfile.ZipFile(out) as archive:
                meta = json.loads(archive.read(prefix + META))
                pack = archive.read(prefix + DATA)
                self.assertEqual(meta["sha256"], hashlib.sha256(pack).hexdigest())
                with zipfile.ZipFile(io.BytesIO(pack)) as game:
                    self.assertEqual(game.read("valve/gfx/conback.lmp"), b"our background")
                    self.assertEqual(game.read("cstrike/models/p_test.mdl"), b"model bytes")


if __name__ == "__main__":
    unittest.main()
