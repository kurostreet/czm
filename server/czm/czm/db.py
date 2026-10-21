"""SQLite storage. One connection per call, WAL mode; the service is small."""
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    device_hash TEXT NOT NULL DEFAULT '',
    nick TEXT NOT NULL DEFAULT 'Player',
    avatar TEXT NOT NULL DEFAULT '',      -- '', '1'..'10' or 'photo'
    avatar_rev INTEGER NOT NULL DEFAULT 0,
    lang TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL,
    seen INTEGER NOT NULL,
    last_message INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS players_device ON players(device_hash);

CREATE TABLE IF NOT EXISTS accounts (
    player INTEGER PRIMARY KEY REFERENCES players(id),
    login TEXT NOT NULL,
    nick_key TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS account_sessions (
    token_hash TEXT PRIMARY KEY,
    player INTEGER NOT NULL REFERENCES accounts(player),
    created INTEGER NOT NULL,
    seen INTEGER NOT NULL,
    expires INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS account_sessions_player ON account_sessions(player);
CREATE TABLE IF NOT EXISTS tab_bindings (
    tag TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    player INTEGER NOT NULL REFERENCES players(id),
    guest INTEGER NOT NULL,
    server TEXT NOT NULL,
    userid INTEGER NOT NULL,
    expires INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tab_bindings_owner ON tab_bindings(owner);
CREATE INDEX IF NOT EXISTS tab_bindings_expires ON tab_bindings(expires);
CREATE TABLE IF NOT EXISTS social_profiles (
    player INTEGER PRIMARY KEY REFERENCES players(id),
    status TEXT NOT NULL DEFAULT '',
    last_seen INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS social_presence (
    owner TEXT PRIMARY KEY,
    player INTEGER NOT NULL REFERENCES players(id),
    seen INTEGER NOT NULL,
    server TEXT NOT NULL DEFAULT '',
    map TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS social_presence_player ON social_presence(player, seen);
CREATE TABLE IF NOT EXISTS social_follows (
    source INTEGER NOT NULL REFERENCES accounts(player),
    target INTEGER NOT NULL REFERENCES accounts(player),
    created INTEGER NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(source, target),
    CHECK(source != target)
);
CREATE INDEX IF NOT EXISTS social_follows_target ON social_follows(target, source);
CREATE TABLE IF NOT EXISTS social_blocks (
    source INTEGER NOT NULL REFERENCES accounts(player),
    target INTEGER NOT NULL REFERENCES accounts(player),
    PRIMARY KEY(source, target),
    CHECK(source != target)
);
CREATE TABLE IF NOT EXISTS private_dialogs (
    id INTEGER PRIMARY KEY,
    low INTEGER NOT NULL REFERENCES accounts(player),
    high INTEGER NOT NULL REFERENCES accounts(player),
    read_low INTEGER NOT NULL DEFAULT 0,
    read_high INTEGER NOT NULL DEFAULT 0,
    last_message INTEGER NOT NULL DEFAULT 0,
    UNIQUE(low, high),
    CHECK(low < high)
);
CREATE TABLE IF NOT EXISTS private_messages (
    id INTEGER PRIMARY KEY,
    dialog INTEGER NOT NULL REFERENCES private_dialogs(id),
    sender INTEGER NOT NULL REFERENCES accounts(player),
    text TEXT NOT NULL,
    created INTEGER NOT NULL,
    nonce TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    UNIQUE(sender, nonce)
);
CREATE INDEX IF NOT EXISTS private_messages_dialog ON private_messages(dialog, id);
CREATE TABLE IF NOT EXISTS auth_limits (
    bucket TEXT PRIMARY KEY,
    count INTEGER NOT NULL,
    expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_codes (
    player INTEGER NOT NULL REFERENCES accounts(player),
    purpose TEXT NOT NULL,
    target TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    expires INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(player, purpose)
);

CREATE TABLE IF NOT EXISTS player_settings (
    player INTEGER PRIMARY KEY REFERENCES accounts(player),
    revision INTEGER NOT NULL,
    payload TEXT NOT NULL,
    updated INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings_history (
    player INTEGER NOT NULL REFERENCES accounts(player),
    revision INTEGER NOT NULL,
    payload TEXT NOT NULL,
    updated INTEGER NOT NULL,
    PRIMARY KEY(player,revision)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    room TEXT NOT NULL,
    player INTEGER NOT NULL,
    text TEXT NOT NULL,
    created INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS messages_room ON messages(room, id);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    reporter INTEGER NOT NULL,
    target INTEGER NOT NULL,
    message INTEGER,                      -- NULL: the avatar
    created INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',  -- open, banned, deleted, dismissed
    resolved INTEGER
);
CREATE INDEX IF NOT EXISTS reports_target ON reports(target);

CREATE TABLE IF NOT EXISTS bans (
    id INTEGER PRIMARY KEY,
    player INTEGER NOT NULL,
    device_hash TEXT NOT NULL DEFAULT '',
    until INTEGER,                        -- NULL: forever
    reason TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL,
    lifted INTEGER
);
CREATE INDEX IF NOT EXISTS bans_player ON bans(player);
CREATE INDEX IF NOT EXISTS bans_device ON bans(device_hash);

CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    created INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY,
    version TEXT NOT NULL,
    code INTEGER NOT NULL,
    file TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL,
    published INTEGER
);

CREATE TABLE IF NOT EXISTS release_patches (
    release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    base_code INTEGER NOT NULL,
    base_sha256 TEXT NOT NULL,
    file TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    PRIMARY KEY (release_id, base_code, base_sha256)
);

-- the public site: download counter (one per address and day, addresses kept hashed for two days)
CREATE TABLE IF NOT EXISTS site_counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS site_downloads (
    day INTEGER NOT NULL,
    ip_hash TEXT NOT NULL,
    PRIMARY KEY (day, ip_hash)
);

-- core APKs sent by GitHub Actions, assembled into releases by `czm.cli assemble`
CREATE TABLE IF NOT EXISTS builds (
    id INTEGER PRIMARY KEY,
    commit_sha TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL,
    code INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    file TEXT NOT NULL,                   -- core APK in the incoming folder
    status TEXT NOT NULL DEFAULT 'new',   -- new, done, failed
    error TEXT NOT NULL DEFAULT '',
    release_id INTEGER,
    created INTEGER NOT NULL,
    finished INTEGER,
    notified INTEGER NOT NULL DEFAULT 0
);

-- Google Play bundles sent to the testing tracks by `czm.cli assemble` (play_publish.py)
CREATE TABLE IF NOT EXISTS play_publishes (
    id INTEGER PRIMARY KEY,
    version TEXT NOT NULL,
    version_code INTEGER,
    tracks TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,                 -- sent, failed
    error TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0
);

-- Private APK testing: a one-use invitation grants access to one registered game account.
CREATE TABLE IF NOT EXISTS development_access (
    player INTEGER PRIMARY KEY REFERENCES players(id),
    created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS development_invites (
    token_hash TEXT PRIMARY KEY,
    created INTEGER NOT NULL,
    expires INTEGER NOT NULL,
    player INTEGER REFERENCES players(id),
    used INTEGER
);
"""

# columns added after the first version of a table
COLUMNS = {
    "releases": {"news_id": "INTEGER", "auto": "INTEGER NOT NULL DEFAULT 0", "channel": "TEXT NOT NULL DEFAULT 'legacy'"},
    "reports": {"private_message": "INTEGER"},
}

_lock = threading.Lock()


def now() -> int:
    return int(time.time())


def connect() -> sqlite3.Connection:
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """A connection with one write transaction at a time."""
    with _lock:
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()


def init() -> None:
    with _lock:
        conn = connect()
        try:
            conn.executescript(SCHEMA)
            from . import lobbies
            conn.executescript(lobbies.LOBBY_SCHEMA)
            for table, columns in COLUMNS.items():
                have = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
                for name, kind in columns.items():
                    if name not in have:
                        try:
                            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
                        except sqlite3.OperationalError as e:  # the other process was first
                            if "duplicate column" not in str(e):
                                raise
        finally:
            conn.close()


def cleanup(conn: sqlite3.Connection, keep_days: int, room_history: int, rooms: list[str]) -> None:
    """Old messages go away: older than keep_days, or beyond the history of a room."""
    conn.execute("DELETE FROM messages WHERE created < ?", (now() - keep_days * 86400,))
    for room in rooms:
        conn.execute(
            "DELETE FROM messages WHERE room = ? AND id NOT IN "
            "(SELECT id FROM messages WHERE room = ? ORDER BY id DESC LIMIT ?)",
            (room, room, room_history * 3),
        )
