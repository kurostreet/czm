import importlib.util
import io
import pathlib
import shutil
import tarfile
import tempfile
import unittest
import zipfile

SOURCE = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('czm_installer', SOURCE / 'installer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        for filename in ['server.ini', 'packages.json']:
            shutil.copy2(SOURCE / filename, self.root / filename)
        self.kit = installer.ServerKit(self.root)

    def test_rejects_archive_escape_and_windows_drive_paths(self):
        for name in ['../outside', '/outside', 'C:/outside', '..\\outside', 'folder/../../outside']:
            archive = self.root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr(name, b'bad')
            with self.assertRaises(ValueError):
                installer.extract(archive, self.root / 'unpacked')

    def test_tar_source_strips_enclosing_directory_and_ignores_links(self):
        archive = self.root / 'source.tar'
        with tarfile.open(archive, 'w') as package:
            file = tarfile.TarInfo('source/addons/test.txt')
            file.size = 2
            package.addfile(file, io.BytesIO(b'ok'))
            link = tarfile.TarInfo('source/escape')
            link.type, link.linkname = tarfile.SYMTYPE, '../../outside'
            package.addfile(link)
        installer.extract(archive, self.root / 'source', 1)
        self.assertEqual((self.root / 'source/addons/test.txt').read_bytes(), b'ok')
        self.assertFalse((self.root / 'source/escape').exists())

    def test_config_rejects_engine_command_injection_and_invalid_ports(self):
        original = (self.root / 'server.ini').read_text()
        for before, after in [('name = CZM Zombie Server', 'name = x";quit'),
                              ('port = 27015', 'port = 65536'),
                              ('players = 16', 'players = 1'),
                              ('fastdl_url =', 'fastdl_url = https://user:password@example.com/')]:
            (self.root / 'server.ini').write_text(original.replace(before, after))
            with self.assertRaises(ValueError):
                installer.settings(self.root)

    def test_configure_preserves_custom_config_disables_remote_rcon_and_has_no_admins(self):
        self.kit.binary.parent.mkdir()
        self.kit.binary.touch()
        self.kit.cs.mkdir()
        custom = self.kit.cs / 'custom.cfg'
        custom.write_text('mp_roundtime 3\n')
        self.kit.configure()
        self.assertEqual(custom.read_text(), 'mp_roundtime 3\n')
        generated = (self.kit.cs / 'server.cfg').read_text()
        self.assertIn('rcon_password ""', generated)
        self.assertIn('sv_rcon_condebug 0', generated)
        self.assertIn('exec custom.cfg', generated)

    def test_fastdl_exports_resources_without_configs_or_binary_modules(self):
        for relative, data in [('maps/test.bsp', b'map'), ('models/test.mdl', b'model'),
                               ('server.cfg', b'secret'), ('addons/plugin.dll', b'executable'),
                               ('maps/private.cfg', b'secret')]:
            file = self.kit.cs / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        self.assertEqual(self.kit.export_fastdl(), 2)
        self.assertEqual({str(p.relative_to(self.root / 'fastdl')) for p in (self.root / 'fastdl').rglob('*') if p.is_file()},
                         {'maps/test.bsp', 'models/test.mdl'})

    def test_bad_download_hash_cannot_be_used_from_cache(self):
        self.kit.cache.mkdir()
        (self.kit.cache / 'test').write_bytes(b'wrong')
        with self.assertRaises(ValueError):
            installer.download({'url': 'http://example.com/', 'sha256': 'a' * 64}, self.kit.cache, 'test')

    def test_admin_assignment_only_accepts_unique_player_ids(self):
        for invalid in ['*', 'loopback', 'STEAM_ID_LAN', '127.0.0.1', 'STEAM_0:1:1";quit']:
            with self.assertRaises(ValueError):
                self.kit.admin(invalid)


if __name__ == '__main__':
    unittest.main()
