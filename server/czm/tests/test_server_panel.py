import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from czm.server_panel import Config, PREFIX, create_app
from czm.server_panel_auth import COOKIE, LocalAuth, Sessions
from czm.server_panel_storage import FileStore, PanelError, digest
from czm import server_panel_agent as agent


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "game"; self.root.mkdir()
        self.fastdl = Path(self.temp.name) / "fastdl"; self.fastdl.mkdir()
        self.state = Path(self.temp.name) / "state"; self.state.mkdir()
        for path in ["maps", "sound", "models", "addons/amxmodx/configs", "addons/amxmodx/plugins"]:
            (self.root / path).mkdir(parents=True, exist_ok=True)
        self.secret = "private-test-rcon-value"
        (self.root / "server.cfg").write_text('hostname "Example"\nrcon_password "'+self.secret+'"\nsv_downloadurl "https://example.com/files/"\nsv_rcon_condebug 0\n')
        (self.root / "addons/amxmodx/configs/users.ini").write_text("; admins\n")
        self.files = FileStore(self.root, self.state, self.fastdl)


class StorageTests(Fixture):
    def test_public_listing_has_only_allowed_game_files(self):
        (self.root / "reunion.cfg").write_text("private")
        (self.root / "dlls").mkdir()
        (self.root / "maps/unsafe.so").write_bytes(b"binary")
        self.assertNotIn("reunion.cfg", [x["name"] for x in self.files.list()["entries"]])
        self.assertNotIn("dlls", [x["name"] for x in self.files.list()["entries"]])
        self.assertEqual(self.files.list("maps")["entries"], [])

    def test_editor_preserves_and_hides_management_parameters(self):
        doc = self.files.read("server.cfg")
        self.assertNotIn(self.secret, doc["text"])
        self.assertNotIn("sv_downloadurl", doc["text"])
        self.files.write("server.cfg", b'hostname "Changed"\n', doc["revision"], True)
        text = (self.root / "server.cfg").read_text()
        self.assertIn(self.secret, text); self.assertIn('hostname "Changed"', text)
        self.assertIn("https://example.com/files/", text)
        with self.assertRaises(PanelError):
            self.files.write("server.cfg", b"rcon_password changed", digest(text.encode()), True)

    def test_conflicting_edit_does_not_overwrite_new_content(self):
        doc = self.files.read("server.cfg")
        self.files.write("server.cfg", b"hostname first", doc["revision"], True)
        with self.assertRaises(PanelError) as caught:
            self.files.write("server.cfg", b"hostname second", doc["revision"], True)
        self.assertEqual(caught.exception.status, 409)
        self.assertIn("first", (self.root / "server.cfg").read_text())

    def test_backup_restore_keeps_current_management_secret(self):
        doc = self.files.read("server.cfg")
        self.files.write("server.cfg", b"hostname second", doc["revision"], True)
        backup = self.files.history("server.cfg")[0]["id"]
        current = (self.root / "server.cfg").read_text().replace(self.secret, "rotated-private-value")
        (self.root / "server.cfg").write_text(current)
        self.files.restore("server.cfg", backup, digest(current.encode()))
        restored = (self.root / "server.cfg").read_text()
        self.assertIn("rotated-private-value", restored)
        self.assertNotIn(self.secret, restored)
        self.assertIn("Example", restored)

    def test_new_resource_upload_sync_and_delete(self):
        self.assertEqual(self.files.metadata("sound/music.wav")["revision"], "new")
        self.files.write("sound/music.wav", b"wave-content", "new")
        self.assertEqual((self.fastdl / "sound/music.wav").read_bytes(), b"wave-content")
        self.files.delete("sound/music.wav", digest(b"wave-content"))
        self.assertFalse((self.root / "sound/music.wav").exists())
        self.assertFalse((self.fastdl / "sound/music.wav").exists())

    def test_configs_are_never_exported(self):
        self.files.write("addons/amxmodx/configs/new.cfg", b"private config", "new", True)
        self.assertFalse((self.fastdl / "addons").exists())

    def test_cp1251_round_trip_and_utf8_conversion(self):
        path = self.root / "addons/amxmodx/configs/test.ini"
        path.write_bytes("; Привет\n".encode("cp1251"))
        doc = self.files.read("addons/amxmodx/configs/test.ini")
        self.assertEqual(doc["encoding"], "cp1251")
        self.files.write(doc["path"], "; Изменено\n".encode(), doc["revision"], True, "cp1251")
        self.assertEqual(path.read_bytes().decode("cp1251"), "; Изменено\n")

    def test_traversal_symlink_hardlink_and_fifo_are_rejected(self):
        outside = Path(self.temp.name) / "private"; outside.write_text("private")
        (self.root / "maps/link.txt").symlink_to(outside)
        (self.root / "maps/linkdir").symlink_to(Path(self.temp.name), target_is_directory=True)
        os.link(outside, self.root / "maps/hard.txt")
        os.mkfifo(self.root / "maps/pipe.txt")
        for path in ["../private", "/etc/passwd", "maps/../../private", "maps//x.txt", "maps/link.txt", "maps/hard.txt", "maps/pipe.txt", "maps/linkdir/private"]:
            with self.subTest(path=path), self.assertRaises((PanelError, OSError)):
                self.files.read(path)
        self.assertEqual(outside.read_text(), "private")
        self.assertEqual(self.files.list("maps")["entries"], [])

    def test_symlink_parent_cannot_be_used_for_write(self):
        (self.root / "maps/out").symlink_to(Path(self.temp.name), target_is_directory=True)
        with self.assertRaises((PanelError, OSError)):
            self.files.write("maps/out/file.txt", b"bad", "new", True)
        self.assertFalse((Path(self.temp.name) / "file.txt").exists())

    def test_native_binaries_and_server_cfg_binary_upload_are_rejected(self):
        for path in ["addons/amxmodx/modules/module.so", "addons/metamod/plugins.ini", "maps/file.so", "reunion.cfg"]:
            with self.subTest(path=path), self.assertRaises(PanelError):
                self.files.write(path, b"data", "new")
        with self.assertRaises(PanelError):
            self.files.write("server.cfg", b"bad", self.files.metadata("server.cfg")["revision"])


class FakeAuth:
    def __init__(self, owner=1): self.owner = owner
    async def action(self, action, body, ip): return {"profile": {"id": self.owner, "nick": "Operator"}}


class ApiTests(Fixture):
    def setUp(self):
        super().setUp()
        self.calls = []
        def control(action, **values):
            self.calls.append((action, values))
            if action == "status":
                return {"state": "active", "memory": 120000, "memory_limit": 320000000, "cpu_ns": 1, "cpu_limit": 35, "uptime": 90, "game": None}
            return {"ok": True, "text": "game output"}
        self.cfg = Config(root=str(self.root), state=str(self.state), fastdl=str(self.fastdl), owners=(1,))
        self.app = create_app(self.cfg, FakeAuth(), control)
        self.client = TestClient(self.app, base_url="https://counter-zombie.ru"); self.addCleanup(self.client.close)

    def login(self):
        r = self.client.post(PREFIX + "/login", json={"nick": "Operator", "password": "test-password"}, headers={"Origin": self.cfg.origin})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("HttpOnly", r.headers["set-cookie"]); self.assertIn("Secure", r.headers["set-cookie"])
        self.assertIn("SameSite=strict", r.headers["set-cookie"])
        token = self.client.get(PREFIX + "/session").json()["csrf"]
        return {"Origin": self.cfg.origin, "X-CZM-CSRF": token}

    def test_every_private_read_needs_session(self):
        for path in ["session", "status", "console", "files", "file?path=server.cfg", "metadata?path=server.cfg", "history?path=server.cfg", "download?path=server.cfg"]:
            self.assertEqual(self.client.get(PREFIX + "/" + path).status_code, 401, path)
        self.assertEqual(self.calls, [])

    def test_mutations_require_origin_and_csrf(self):
        headers = self.login()
        for sent in [{}, {"Origin": self.cfg.origin}, {**headers, "Origin": "https://evil.example"}]:
            r = self.client.post(PREFIX + "/power", json={"action": "restart"}, headers=sent)
            self.assertEqual(r.status_code, 403)
        self.assertEqual(self.calls, [])

    def test_only_allowlisted_account_can_sign_in(self):
        app = create_app(self.cfg, FakeAuth(2))
        with TestClient(app, base_url=self.cfg.origin) as client:
            r = client.post(PREFIX + "/login", json={"nick": "other", "password": "other"}, headers={"Origin": self.cfg.origin})
            self.assertEqual(r.status_code, 403)
            self.assertNotIn("set-cookie", r.headers)

    def test_logout_invalidates_session(self):
        headers = self.login()
        cookie = self.client.cookies.get(COOKIE)
        self.assertEqual(self.client.post(PREFIX + "/logout", headers=headers).status_code, 200)
        self.client.cookies.set(COOKIE, cookie)
        self.assertEqual(self.client.get(PREFIX + "/session").status_code, 401)

    def test_power_accepts_only_fixed_verbs(self):
        headers = self.login()
        for action in ["restart ssh", "stop;id", "reload", ""]:
            self.assertEqual(self.client.post(PREFIX + "/power", json={"action": action}, headers=headers).status_code, 400)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.client.post(PREFIX + "/power", json={"action": "start"}, headers=headers).status_code, 200)
        self.assertEqual(self.calls, [("power", {"verb": "start"})])

    def test_edit_upload_download_and_history(self):
        headers = self.login()
        doc = self.client.get(PREFIX + "/file?path=server.cfg").json()
        self.assertNotIn(self.secret, json.dumps(doc))
        r = self.client.post(PREFIX + "/file", json={"path": "server.cfg", "text": "hostname api", "revision": doc["revision"]}, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.get(PREFIX + "/download?path=server.cfg").status_code, 403)
        upload = self.client.put(PREFIX + "/upload?path=maps/new.bsp", content=b"test-map", headers={**headers, "If-Match": "new"})
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(self.client.get(PREFIX + "/download?path=maps/new.bsp").content, b"test-map")
        self.assertEqual((self.fastdl / "maps/new.bsp").read_bytes(), b"test-map")
        history = self.client.get(PREFIX + "/history?path=server.cfg").json()
        self.assertEqual(len(history["entries"]), 1)
        self.assertNotIn(self.secret, json.dumps(history))

    def test_session_expiry_and_persistent_login_limits(self):
        token = self.app.state.sessions.issue(1, "Owner")
        with patch("czm.server_panel_auth.time.time", return_value=10**12):
            with self.assertRaises(PanelError): self.app.state.sessions.get(token)
        for _ in range(8): self.app.state.sessions.rate("test-ip")
        with self.assertRaises(PanelError) as caught: Sessions(self.state).rate("test-ip")
        self.assertEqual(caught.exception.status, 429)


class CredentialTests(unittest.IsolatedAsyncioTestCase):
    async def test_scrypt_login_rejects_wrong_password_and_unicode_login(self):
        with tempfile.TemporaryDirectory() as folder:
            salt = os.urandom(16)
            record = {"login": "Operator", "salt": salt.hex(), "hash": hashlib.scrypt(b"private-test-password", salt=salt, n=16384, r=8, p=1).hex()}
            path = Path(folder) / "credentials.json"; path.write_text(json.dumps(record))
            auth = LocalAuth(path)
            result = await auth.action("login", {"nick": "Operator", "password": "private-test-password"}, "local")
            self.assertEqual(result["profile"]["id"], 1)
            for nick, password in [("Operator", "wrong"), ("Чужой", "private-test-password")]:
                with self.assertRaises(PanelError): await auth.action("login", {"nick": nick, "password": password}, "local")


class AgentTests(unittest.TestCase):
    def test_agent_cannot_target_another_unit_or_execute_shell(self):
        with patch.object(agent, "system") as system:
            for body in [{"action": "shell", "command": "id"}, {"action": "power", "verb": "stop ssh.service"}]:
                with self.assertRaises(ValueError): agent.dispatch(body)
            system.assert_not_called()
        with patch.object(agent, "system", return_value=""), patch.object(agent, "status", return_value={"state": "active"}) as status:
            self.assertTrue(agent.dispatch({"action": "power", "verb": "start", "unit": "ssh.service"})["ok"])
            status.assert_called_once()

    def test_console_rejects_management_secret_commands(self):
        for text in ["rcon_password secret", "sv_rcon_condebug 1", "rcon_users 0.0.0.0", "status\nquit"]:
            with self.assertRaises(ValueError): agent.rcon(text)

    def test_scrubber_removes_current_secret_and_credential_log_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rcon"; path.write_text("do-not-leak-this")
            with patch.object(agent, "RCON", str(path)):
                text = agent.scrub('cvar value do-not-leak-this\nrcon_password old-secret\nRcon from 127.0.0.1 old-value\nnormal game log')
            self.assertNotIn("do-not-leak-this", text); self.assertNotIn("old-secret", text); self.assertNotIn("old-value", text)
            self.assertIn("normal game log", text)


if __name__ == "__main__":
    unittest.main()
