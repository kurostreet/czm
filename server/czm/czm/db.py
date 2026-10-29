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

-- Keep IDs unique across account deletion: moderation records intentionally outlive profiles.
CREATE TABLE IF NOT EXISTS player_id_sequence (
    id INTEGER PRIMARY KEY CHECK(id=1),
    last_id INTEGER NOT NULL
);
INSERT OR IGNORE INTO player_id_sequence(id,last_id) VALUES(1,0);
UPDATE player_id_sequence SET last_id=MAX(last_id, COALESCE((SELECT MAX(id) FROM players),0)) WHERE id=1;
CREATE TRIGGER IF NOT EXISTS player_id_sequence_insert AFTER INSERT ON players
BEGIN
    UPDATE player_id_sequence SET last_id=MAX(last_id,NEW.id) WHERE id=1;
END;

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
CREATE INDEX IF NOT EXISTS social_presence_server ON social_presence(server, seen);
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

-- The official SUPPORT account(s); granted on the server only (python -m czm.cli support-grant).
CREATE TABLE IF NOT EXISTS staff (
    player INTEGER PRIMARY KEY REFERENCES players(id),
    role TEXT NOT NULL CHECK(role IN ('support')),
    granted INTEGER NOT NULL
);
-- Every moderation step taken in the game: who, on whom, what, why, for how long.
CREATE TABLE IF NOT EXISTS moderation_log (
    id INTEGER PRIMARY KEY,
    moderator INTEGER NOT NULL,
    target INTEGER NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    until INTEGER,                        -- a sanction's end, NULL: forever or not a sanction
    sanction INTEGER,                     -- bans.id
    report INTEGER,
    evidence TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL,
    nonce TEXT,
    UNIQUE(moderator, nonce)
);
CREATE INDEX IF NOT EXISTS moderation_log_target ON moderation_log(target, id);
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY,
    player INTEGER NOT NULL REFERENCES players(id),
    reason TEXT NOT NULL,
    created INTEGER NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS warnings_player ON warnings(player, seen);

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
    "players": {"rules_version": "INTEGER NOT NULL DEFAULT 0",
                "rules_at": "INTEGER NOT NULL DEFAULT 0",
                "rules_client": "INTEGER NOT NULL DEFAULT 0"},
    # kind: chat, private, lobby_message, lobby, lobby_member, profile ('' = written before kinds).
    # evidence keeps the reported text: lobby rooms and old chat disappear before a review.
    "reports": {"private_message": "INTEGER",
                "lobby_message": "INTEGER",
                "lobby": "TEXT",
                "kind": "TEXT NOT NULL DEFAULT ''",
                "evidence": "TEXT NOT NULL DEFAULT ''",
                "context": "TEXT NOT NULL DEFAULT ''"},
    "lobby_messages": {"deleted": "INTEGER NOT NULL DEFAULT 0"},
    # the English text of a news item: players with the English game read it ('' = Russian for all)
    "news": {"text_en": "TEXT NOT NULL DEFAULT ''"},
    # kind: ban (everything), text, voice, photo; moderator: who gave it in the game (NULL: the bot)
    "bans": {"kind": "TEXT NOT NULL DEFAULT 'ban'", "moderator": "INTEGER"},
    "lobbies": {"last_seen": "INTEGER NOT NULL DEFAULT 0",
                "voice_mute_all":"INTEGER NOT NULL DEFAULT 0",
                "language":"TEXT NOT NULL DEFAULT ''"},
    "launch_members": {"last_seen": "INTEGER NOT NULL DEFAULT 0",
                       "departed_at": "INTEGER NOT NULL DEFAULT 0",
                       "ended": "INTEGER NOT NULL DEFAULT 0",
                       "delivered_at": "INTEGER NOT NULL DEFAULT 0"},
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
            # Older versions could remove the highest profile ID while retaining its
            # safety records. Reserve those IDs too when upgrading an existing database.
            conn.execute("UPDATE player_id_sequence SET last_id=MAX(last_id, "
                         "COALESCE((SELECT MAX(player) FROM bans),0), "
                         "COALESCE((SELECT MAX(target) FROM reports),0), "
                         "COALESCE((SELECT MAX(reporter) FROM reports),0), "
                         "COALESCE((SELECT MAX(target) FROM moderation_log),0), "
                         "COALESCE((SELECT MAX(moderator) FROM moderation_log),0)) WHERE id=1")
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
            from . import notifications, play_feed, playtime, server_moderation, community, moderator_guard
            conn.executescript(notifications.SCHEMA)
            conn.executescript(playtime.SCHEMA)
            conn.executescript(server_moderation.SCHEMA)
            conn.executescript(community.SCHEMA)
            conn.executescript(moderator_guard.SCHEMA)
            play_feed.migrate(conn)
            # Preserve existing unviewed incoming requests on upgrade.
            conn.execute("INSERT OR IGNORE INTO social_notices(player,peer,kind,created) "
                         "SELECT f.target,f.source,'followers',f.created FROM social_follows f "
                         "WHERE f.seen=0 AND NOT EXISTS(SELECT 1 FROM social_follows r WHERE r.source=f.target AND r.target=f.source)")
        finally:
            conn.close()


def cleanup(conn: sqlite3.Connection, keep_days: int, room_history: int, rooms: list[str]) -> None:
    """Delete expired social data without retaining former lobby content."""
    conn.execute("DELETE FROM messages WHERE created < ?", (now() - keep_days * 86400,))
    from .lobbies import HOST_TTL
    conn.execute("DELETE FROM lobbies WHERE last_seen <= ?", (now()-HOST_TTL,))
    conn.execute("DELETE FROM lobby_launches WHERE episode_expires <= ?", (now(),))
    conn.execute("DELETE FROM lobby_creation_ops WHERE created < ?", (now() - 7*86400,))
    conn.execute("DELETE FROM lobby_moderation_ops WHERE created < ?", (now() - 30*86400,))
    conn.execute("DELETE FROM lobby_invites WHERE expires < ?", (now() - 86400,))
    from . import server_moderation, community
    server_moderation.cleanup(conn)
    community.cleanup(conn)
    for room in rooms:
        conn.execute(
            "DELETE FROM messages WHERE room = ? AND id NOT IN "
            "(SELECT id FROM messages WHERE room = ? ORDER BY id DESC LIMIT ?)",
            (room, room, room_history * 3),
        )

