"""Independent owner-panel credentials and short browser sessions."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager
import json

from .server_panel_storage import PanelError

COOKIE = "__Host-czm-panel"
SESSION_SECONDS = 12 * 3600


class Sessions:
    def __init__(self, folder):
        self.path = Path(folder) / "panel.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, owner INTEGER, nick TEXT, expires INTEGER);
              CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, count INTEGER, until INTEGER);
              CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, time INTEGER, owner INTEGER, action TEXT, path TEXT, result TEXT);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def issue(self, owner, nick):
        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))
            conn.execute("INSERT INTO sessions VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), owner, nick, int(time.time()) + SESSION_SECONDS))
        return token

    def get(self, token):
        if not token or len(token) > 128:
            raise PanelError("session", 401)
        with self.connect() as conn:
            row = conn.execute("SELECT owner,nick,expires FROM sessions WHERE hash=? AND expires>?",
                               (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if row is None:
            raise PanelError("session", 401)
        return dict(row)

    def revoke(self, token):
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def rate(self, key, limit=8, seconds=900):
        now = int(time.time())
        key = hashlib.sha256(key.encode()).hexdigest()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM limits WHERE until<=?", (now,))
            row = conn.execute("SELECT count FROM limits WHERE key=?", (key,)).fetchone()
            if row and row[0] >= limit:
                raise PanelError("slow", 429)
            conn.execute("INSERT INTO limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1", (key, now + seconds))

    def audit(self, owner, action, path="", result="ok"):
        with self.connect() as conn:
            conn.execute("INSERT INTO audit(time,owner,action,path,result) VALUES(?,?,?,?,?)",
                         (int(time.time()), owner, action, path[:512], result))
            conn.execute("DELETE FROM audit WHERE id <= (SELECT COALESCE(MAX(id),0)-10000 FROM audit)")


def csrf(token):
    return hmac.new(token.encode(), b"czm-owner-panel-csrf", hashlib.sha256).hexdigest()


class LocalAuth:
    def __init__(self, path):
        self.path = Path(path)

    async def action(self, action, body, ip):
        if action != "login":
            raise PanelError("request")
        try:
            record = json.loads(self.path.read_text())
            salt = bytes.fromhex(record["salt"])
            candidate = hashlib.scrypt(body.get("password", "").encode(), salt=salt, n=16384, r=8, p=1).hex()
            # Calculate the hash even when the login is incorrect.
            valid = hmac.compare_digest(candidate, record["hash"])
            valid = hmac.compare_digest(body.get("nick", "").encode(), record["login"].encode()) and valid
        except (OSError, KeyError, ValueError):
            raise PanelError("auth_unavailable", 503) from None
        if not valid:
            raise PanelError("credentials", 401)
        return {"profile": {"id": 1, "nick": record["login"]}}
