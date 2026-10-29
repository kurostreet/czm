"""What the service does with players, messages, complaints, bans, news and releases.

Functions take an open connection (see db.db()) and return plain dicts, so the API
and the Telegram bot share them.
"""
import hashlib
import re
import sqlite3
import unicodedata

from . import profanity
from .config import get_settings
from .db import now

BAN_LENGTHS = {"week": 7 * 86400, "month": 30 * 86400, "forever": None}
_COLOR = re.compile(r"\^[0-9]")


def hash_secret(value: str) -> str:
    return hashlib.sha256((get_settings().pepper + ":" + value).encode()).hexdigest()


def clean_text(text: str, limit: int) -> str:
    """One line, no control characters or colour codes, at most limit characters."""
    text = _COLOR.sub("", text or "")
    text = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def clean_nick(nick: str) -> str:
    nick = clean_text(nick, 24)
    return nick if len(nick) >= 2 else "Player"


def has_photo(player_id: int) -> bool:
    return (get_settings().avatar_dir / f"{player_id}.png").exists()


def clean_avatar(avatar: str, photo: bool = False) -> str:
    avatar = (avatar or "").strip()
    if avatar == "photo":
        # a photo exists only after an upload
        return "photo" if photo else ""
    if avatar.isdigit() and 1 <= int(avatar) <= 10:
        return avatar
    return ""


def avatar_ref(row: sqlite3.Row) -> str:
    """How the client shows a player's avatar: '', '1'..'10' or 'photo:<rev>'."""
    if row["avatar"] == "photo":
        return f"photo:{row['avatar_rev']}"
    return row["avatar"]


# players ---------------------------------------------------------------------

def player_by_key(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    if not key or len(key) < 16 or len(key) > 128:
        return None
    from . import accounts
    if key.startswith(accounts.SESSION_PREFIX):
        return accounts.player_for_session(conn, key)
    return conn.execute("SELECT * FROM players WHERE key_hash = ? AND NOT EXISTS "
                        "(SELECT 1 FROM accounts a WHERE a.player=players.id)", (hash_secret(key),)).fetchone()


def hello(conn: sqlite3.Connection, key: str, device: str, nick: str, avatar: str, lang: str, version: str, keep_avatar: bool = False) -> sqlite3.Row:
    from . import accounts
    t = now()
    key_hash = hash_secret(key)
    device_hash = hash_secret(device) if device else ""
    row = player_by_key(conn, key)
    if row is None and (key.startswith(accounts.SESSION_PREFIX) or conn.execute("SELECT 1 FROM players WHERE key_hash=?", (key_hash,)).fetchone()):
        raise accounts.AuthError("session", 401)
    if row is None:
        next_id = conn.execute("SELECT last_id+1 FROM player_id_sequence WHERE id=1").fetchone()[0]
        conn.execute(
            "INSERT INTO players (id, key_hash, device_hash, nick, avatar, lang, version, created, seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (next_id, key_hash, device_hash, clean_nick(nick), clean_avatar(avatar), lang[:8], version[:32], t, t),
        )
    else:
        if keep_avatar:
            avatar = row["avatar"]
        conn.execute(
            "UPDATE players SET device_hash = CASE WHEN ? != '' THEN ? ELSE device_hash END, nick = ?, avatar = ?, lang = ?, version = ?, seen = ? WHERE id = ?",
            (device_hash, device_hash, clean_nick(nick), clean_avatar(avatar, has_photo(row["id"])), lang[:8], version[:32], t, row["id"]),
        )
    return conn.execute("SELECT * FROM players WHERE id = ?", (row["id"],)).fetchone() if row else \
        conn.execute("SELECT * FROM players WHERE key_hash = ?", (key_hash,)).fetchone()


def active_ban(conn: sqlite3.Connection, player: sqlite3.Row) -> dict | None:
    """The ban on this player or on this phone, if any."""
    t = now()
    row = conn.execute(
        "SELECT * FROM bans WHERE kind = 'ban' AND lifted IS NULL AND (until IS NULL OR until > ?) "
        "AND (player = ? OR (device_hash != '' AND device_hash = ?)) ORDER BY until IS NULL DESC, until DESC LIMIT 1",
        (t, player["id"], player["device_hash"]),
    ).fetchone()
    if row is None:
        return None
    return {"until": row["until"] or 0, "forever": row["until"] is None, "reason": row["reason"]}


def set_photo(conn: sqlite3.Connection, player_id: int) -> int:
    conn.execute("UPDATE players SET avatar = 'photo', avatar_rev = avatar_rev + 1 WHERE id = ?", (player_id,))
    return conn.execute("SELECT avatar_rev FROM players WHERE id = ?", (player_id,)).fetchone()[0]


# chat ------------------------------------------------------------------------

def messages(conn: sqlite3.Connection, room: str, after: int, viewer: int = 0) -> list[dict]:
    """The room's recent messages; without the players the viewer blocked."""
    limit = get_settings().room_history
    rows = conn.execute(
        "SELECT m.id, m.player, m.text, m.created, p.nick, p.avatar, p.avatar_rev, s.role FROM messages m "
        "JOIN players p ON p.id = m.player LEFT JOIN staff s ON s.player = m.player "
        "WHERE m.room = ? AND m.deleted = 0 AND m.id > ? "
        "AND NOT EXISTS (SELECT 1 FROM social_blocks b WHERE b.source = ? AND b.target = m.player) "
        "ORDER BY m.id DESC LIMIT ?",
        (room, after, viewer, limit),
    ).fetchall()
    from . import playtime, community
    places = playtime.places(conn) if rows else {}
    roles = community.role_map(conn, [r["player"] for r in rows])
    return [
        {"id": r["id"], "p": r["player"], "n": r["nick"], "a": avatar_ref(r), "t": profanity.clean(r["text"]), "ts": r["created"],
         **({"r": roles[r["player"]][0], "rp": roles[r["player"]][1]} if r["player"] in roles else {}),
         **({"k": places[r["player"]]} if r["player"] in places else {})}   # the place in the Top 100
        for r in reversed(rows)
    ]


def deleted_since(conn: sqlite3.Connection, room: str, after: int) -> list[int]:
    """Messages the client may still show that were removed by the owner."""
    rows = conn.execute(
        "SELECT id FROM messages WHERE room = ? AND deleted = 1 AND id > ? ORDER BY id DESC LIMIT 50",
        (room, max(0, after - 300)),
    ).fetchall()
    return [r["id"] for r in rows]


class ChatError(Exception):
    def __init__(self, code: str, status: int, **extra):
        super().__init__(code)
        self.code, self.status, self.extra = code, status, extra


def post_message(conn: sqlite3.Connection, player: sqlite3.Row, room: str, text: str) -> dict:
    settings = get_settings()
    ban = active_ban(conn, player)
    if ban:
        raise ChatError("banned", 403, ban=ban)
    from . import moderation
    mute = moderation.sanction(conn, player, "text")
    if mute:
        raise ChatError("muted", 403, mute=mute)

    text = clean_text(text, settings.message_max_chars)
    if not text:
        raise ChatError("empty", 400)

    t = now()
    wait = player["last_message"] + settings.message_interval_seconds - t
    if wait > 0:
        raise ChatError("slow", 429, wait=int(wait) + 1)

    # the same text again within a minute is spam
    last = conn.execute(
        "SELECT text FROM messages WHERE player = ? AND created > ? ORDER BY id DESC LIMIT 1", (player["id"], t - 60)
    ).fetchone()
    text = profanity.clean(text)
    if last and last["text"] == text:
        raise ChatError("repeat", 429, wait=5)

    # Keep read cursors valid even after retention deletes the entire chat.
    next_id = conn.execute("SELECT last_id+1 FROM chat_message_sequence WHERE id=1").fetchone()[0]
    cur = conn.execute("INSERT INTO messages (id, room, player, text, created) VALUES (?, ?, ?, ?, ?)", (next_id, room, player["id"], text, t))
    conn.execute("UPDATE players SET last_message = ? WHERE id = ?", (t, player["id"]))
    return {"id": cur.lastrowid, "p": player["id"], "n": player["nick"], "a": avatar_ref(player), "t": text, "ts": t}


# complaints and bans ---------------------------------------------------------

MESSAGE_REPORTS = ("chat", "private", "lobby_message")


def _profile_status(conn: sqlite3.Connection, player_id: int) -> str:
    row = conn.execute("SELECT status FROM social_profiles WHERE player = ?", (player_id,)).fetchone()
    return row["status"] if row else ""


def report(conn: sqlite3.Connection, reporter: sqlite3.Row, message_id: int | None, player_id: int | None,
           private_message_id: int | None = None, lobby_message_id: int | None = None,
           lobby_id: str | None = None) -> dict | None:
    """A new complaint, or None if it repeats one or makes no sense.

    The reported text is copied into the complaint: lobby rooms and old chat messages
    are deleted long before the owner may look at it."""
    t = now()
    if conn.execute("SELECT COUNT(*) FROM reports WHERE reporter = ? AND created > ?", (reporter["id"], t - 3600)).fetchone()[0] >= 10:
        raise ChatError("slow", 429, wait=600)

    def member(lobby, player):
        return conn.execute("SELECT 1 FROM lobby_members WHERE lobby = ? AND player = ?", (lobby, player)).fetchone() is not None

    kind, evidence, context, lobby = "profile", "", "", None
    if private_message_id:
        message = conn.execute(
            "SELECT m.*,d.low,d.high FROM private_messages m JOIN private_dialogs d ON d.id=m.dialog WHERE m.id=? AND m.deleted=0",
            (private_message_id,)).fetchone()
        if message is None or reporter["id"] not in (message["low"], message["high"]) or message["sender"] == reporter["id"]:
            return None
        player_id, message_id, lobby_message_id = message["sender"], None, None
        kind, evidence, context = "private", message["text"], "Личное сообщение"
    elif lobby_message_id:
        message = conn.execute("SELECT m.*, l.title FROM lobby_messages m JOIN lobbies l ON l.id = m.lobby "
                               "WHERE m.id = ? AND m.deleted = 0", (lobby_message_id,)).fetchone()
        # only someone in the same room has seen the message
        if message is None or not member(message["lobby"], reporter["id"]):
            return None
        player_id, message_id = message["sender"], None
        kind, evidence, context, lobby = "lobby_message", message["text"], message["title"], message["lobby"]
    elif lobby_id:
        room = conn.execute("SELECT * FROM lobbies WHERE id = ?", (lobby_id,)).fetchone()
        if room is None:
            return None
        message_id, lobby = None, room["id"]
        if player_id:  # someone in the room: voice or behaviour
            if not member(room["id"], reporter["id"]) or not member(room["id"], player_id):
                return None
            kind, context = "lobby_member", room["title"]
        else:  # the room itself: its name and description
            if room["visibility"] != "public" and not member(room["id"], reporter["id"]):
                return None
            player_id = room["owner"]
            kind, context = "lobby", room["title"]
            evidence = room["title"] + ("\n" + room["description"] if room["description"] else "")
    elif message_id:
        message = conn.execute("SELECT * FROM messages WHERE id = ? AND deleted = 0", (message_id,)).fetchone()
        if message is None:
            return None
        player_id = message["player"]
        kind, evidence, context = "chat", message["text"], message["room"]
    if not player_id or player_id == reporter["id"]:
        return None
    if conn.execute("SELECT 1 FROM players WHERE id = ?", (player_id,)).fetchone() is None:
        return None
    if kind == "profile":
        evidence = _profile_status(conn, player_id)

    if conn.execute(
        "SELECT 1 FROM reports WHERE reporter = ? AND target = ? AND message IS ? AND private_message IS ? "
        "AND lobby_message IS ? AND lobby IS ? AND kind IN (?, '') AND created > ?",
        (reporter["id"], player_id, message_id or None, private_message_id or None, lobby_message_id or None,
         lobby, kind, t - 86400),
    ).fetchone():
        return None

    cur = conn.execute(
        "INSERT INTO reports (reporter, target, message, private_message, lobby_message, lobby, kind, evidence, context, created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (reporter["id"], player_id, message_id or None, private_message_id or None, lobby_message_id or None,
         lobby, kind, evidence[:2000], context[:200], t),
    )
    return report_info(conn, cur.lastrowid)


def report_info(conn: sqlite3.Connection, report_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if r is None:
        return None
    target = conn.execute("SELECT * FROM players WHERE id = ?", (r["target"],)).fetchone()
    reporter = conn.execute("SELECT nick FROM players WHERE id = ?", (r["reporter"],)).fetchone()
    kind = r["kind"] or ("private" if r["private_message"] else "chat" if r["message"] else "profile")
    evidence, context = r["evidence"], r["context"]
    if not r["kind"]:  # written before the text was copied into complaints
        message = conn.execute("SELECT * FROM messages WHERE id = ?", (r["message"],)).fetchone() if r["message"] else None
        private = conn.execute("SELECT * FROM private_messages WHERE id=?", (r["private_message"],)).fetchone() if r["private_message"] else None
        evidence = private["text"] if private else message["text"] if message else ""
        context = "Личное сообщение" if private else message["room"] if message else ""
    count = conn.execute("SELECT COUNT(*) FROM reports WHERE target = ? AND created > ?", (r["target"], now() - 7 * 86400)).fetchone()[0]
    return {
        "id": r["id"],
        "status": r["status"],
        "kind": kind,
        "target": target["id"] if target else r["target"],
        "nick": target["nick"] if target else "",
        "avatar": target["avatar"] if target else "",
        "avatar_rev": target["avatar_rev"] if target else 0,
        "reporter": r["reporter"],
        "reporter_nick": reporter["nick"] if reporter else "",
        # the reported text; None for a profile or for someone's voice in a lobby
        "message": evidence if kind in MESSAGE_REPORTS or kind == "lobby" else None,
        "evidence": evidence,
        "room": context if kind in ("chat", "private") else None,
        "context": context,
        "lobby": r["lobby"],
        "message_id": r["message"],
        "private_message_id": r["private_message"],
        "lobby_message_id": r["lobby_message"],
        "reports_week": count,
    }


def ban(conn: sqlite3.Connection, player_id: int, length: str, reason: str) -> dict | None:
    player = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if player is None or length not in BAN_LENGTHS:
        return None
    seconds = BAN_LENGTHS[length]
    until = now() + seconds if seconds else None
    conn.execute(
        "INSERT INTO bans (player, device_hash, until, reason, created) VALUES (?, ?, ?, ?, ?)",
        (player_id, player["device_hash"], until, reason[:200], now()),
    )
    return {"player": player_id, "nick": player["nick"], "until": until}


def reset_avatar(conn: sqlite3.Connection, player_id: int) -> None:
    conn.execute("UPDATE players SET avatar = '' WHERE id = ?", (player_id,))
    path = get_settings().avatar_dir / f"{player_id}.png"
    path.unlink(missing_ok=True)


def unban(conn: sqlite3.Connection, player_id: int) -> int:
    player = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if player is None:
        return 0
    cur = conn.execute(
        "UPDATE bans SET lifted = ? WHERE lifted IS NULL AND (player = ? OR (device_hash != '' AND device_hash = ?))",
        (now(), player_id, player["device_hash"]),
    )
    return cur.rowcount


def active_bans(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT b.*, p.nick FROM bans b JOIN players p ON p.id = b.player "
        "WHERE b.lifted IS NULL AND (b.until IS NULL OR b.until > ?) ORDER BY b.id DESC LIMIT 50",
        (now(),),
    ).fetchall()
    return [{"player": r["player"], "nick": r["nick"], "until": r["until"], "reason": r["reason"], "kind": r["kind"]} for r in rows]


def resolve_report(conn: sqlite3.Connection, report_id: int, status: str) -> None:
    conn.execute("UPDATE reports SET status = ?, resolved = ? WHERE id = ?", (status, now(), report_id))


def delete_message(conn: sqlite3.Connection, message_id: int) -> None:
    conn.execute("UPDATE messages SET deleted = 1 WHERE id = ?", (message_id,))


def delete_report_message(conn, info):
    if info.get("private_message_id"):
        conn.execute("UPDATE private_messages SET deleted=1 WHERE id=?", (info["private_message_id"],))
    elif info.get("lobby_message_id"):
        conn.execute("UPDATE lobby_messages SET deleted=1 WHERE id=?", (info["lobby_message_id"],))
    elif info.get("message_id"):
        delete_message(conn, info["message_id"])


def remove_report_content(conn, info) -> str:
    """Take down what the complaint is about. Returns what was done, for the owner."""
    kind = info.get("kind")
    if kind in MESSAGE_REPORTS:
        delete_report_message(conn, info)
        return "сообщение удалено"
    if kind == "lobby" and info.get("lobby"):
        conn.execute("DELETE FROM lobbies WHERE id=?", (info["lobby"],))
        return "лобби закрыто"
    if kind == "profile":
        reset_avatar(conn, info["target"])
        conn.execute("UPDATE social_profiles SET status='' WHERE player=?", (info["target"],))
        return "аватар и статус сброшены"
    return ""


# news and releases -----------------------------------------------------------

def bilingual(text: str) -> tuple[str, str]:
    """The owner writes "Russian | English" in the bot; one text is Russian for everybody."""
    ru, _, en = (text or "").partition("|")
    return ru.strip(), en.strip()


def add_news(conn: sqlite3.Connection, text: str, text_en: str = "") -> int:
    return conn.execute("INSERT INTO news (text, text_en, created) VALUES (?, ?, ?)",
                        (text.strip()[:1000], (text_en or "").strip()[:1000], now())).lastrowid


def news(conn: sqlite3.Connection, after: int = 0, limit: int = 20, lang: str = "ru") -> list[dict]:
    """The bell: in English for the English game when the item has an English text, else Russian."""
    english = (lang or "").lower().startswith("en")
    rows = conn.execute(
        "SELECT * FROM news WHERE deleted = 0 AND id > ? ORDER BY id DESC LIMIT ?", (after, limit)
    ).fetchall()
    return [{"id": r["id"], "text": r["text_en"] if english and r["text_en"] else r["text"], "ts": r["created"]} for r in rows]


def last_news_id(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COALESCE(MAX(id), 0) FROM news WHERE deleted = 0").fetchone()[0]


def edit_news(conn: sqlite3.Connection, news_id: int, text: str, text_en: str | None = None) -> bool:
    """The owner corrects a news item: the bell and the site show the new text. text_en None keeps
    the English text, "" removes it (the English game shows the Russian one)."""
    text = text.strip()[:1000]
    if not text:
        return False
    if text_en is None:
        return conn.execute("UPDATE news SET text = ? WHERE id = ? AND deleted = 0", (text, news_id)).rowcount > 0
    return conn.execute("UPDATE news SET text = ?, text_en = ? WHERE id = ? AND deleted = 0",
                        (text, text_en.strip()[:1000], news_id)).rowcount > 0


def delete_news(conn: sqlite3.Connection, news_id: int) -> bool:
    return conn.execute("UPDATE news SET deleted = 1 WHERE id = ?", (news_id,)).rowcount > 0


def _release(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    return {
        "id": r["id"], "version": r["version"], "code": r["code"], "size": r["size"], "sha256": r["sha256"],
        "notes": r["notes"], "url": f"{get_settings().public_url}/dl/{r['file']}", "published": r["published"], "channel": r["channel"],
    }


def latest_release(conn: sqlite3.Connection, published_only: bool = True, *, base_code: int | None = None,
                   channel: str = "legacy") -> dict | None:
    if channel == "development":
        scope = "channel IN ('development', 'migration')"
    elif published_only:
        # The final migration APK remains pinned for old installs while private builds advance.
        scope = "channel = CASE WHEN EXISTS (SELECT 1 FROM releases WHERE channel='migration' AND published IS NOT NULL) THEN 'migration' ELSE 'legacy' END"
    else:
        scope = "1=1"
    query = f"SELECT * FROM releases WHERE {scope}" + (" AND published IS NOT NULL" if published_only else "") + " ORDER BY code DESC LIMIT 1"
    release = _release(conn.execute(query).fetchone())
    if release and base_code is not None and 0 < base_code < release["code"]:
        for patch in conn.execute("SELECT * FROM release_patches WHERE release_id = ? AND base_code = ? ORDER BY size",
                                  (release["id"], base_code)):
            path = get_settings().apk_dir / patch["file"]
            if path.is_file() and path.stat().st_size == patch["size"] and 0 < patch["size"] < release["size"]:
                release.update(patch_format=1, patch_url=f"{get_settings().public_url}/dl/{patch['file']}",
                               patch_size=patch["size"], patch_sha256=patch["sha256"], base_sha256=patch["base_sha256"])
                break
    return release


def release_by_id(conn: sqlite3.Connection, release_id: int) -> dict | None:
    return _release(conn.execute("SELECT * FROM releases WHERE id = ?", (release_id,)).fetchone())


DEFAULT_NOTES = "Исправления и улучшения."


def release_news_text(version: str, notes: str) -> str:
    return f"Обновление {version}\n{notes.strip() or DEFAULT_NOTES}"[:1000]


def publish_release(conn: sqlite3.Connection, release_id: int, notes: str) -> None:
    """The site build goes to its channel. Players hear about Google Play releases only
    (play_feed.py): a site build never makes news in the bell or on the site."""
    notes = notes.strip()[:1000] or DEFAULT_NOTES
    conn.execute("UPDATE releases SET published = ?, notes = ? WHERE id = ?", (now(), notes, release_id))


def unpublish_release(conn: sqlite3.Connection, release_id: int) -> None:
    """Players go back to the previous published build; its news item leaves the bell."""
    row = conn.execute("SELECT news_id FROM releases WHERE id = ?", (release_id,)).fetchone()
    if row is None:
        return
    if row["news_id"]:
        delete_news(conn, row["news_id"])
    conn.execute("UPDATE releases SET published = NULL WHERE id = ?", (release_id,))


def set_release_notes(conn: sqlite3.Connection, release_id: int, notes: str) -> None:
    """Corrects what is new of a published release, in the update card and in the news."""
    notes = notes.strip()[:1000] or DEFAULT_NOTES
    row = conn.execute("SELECT version, news_id FROM releases WHERE id = ?", (release_id,)).fetchone()
    if row is None:
        return
    conn.execute("UPDATE releases SET notes = ? WHERE id = ?", (notes, release_id))


# automatic builds ------------------------------------------------------------

def build_by_commit(conn: sqlite3.Connection, commit: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM builds WHERE commit_sha = ?", (commit,)).fetchone()


def add_build(conn: sqlite3.Connection, commit: str, version: str, code: int, notes: str, file: str) -> int:
    conn.execute("DELETE FROM builds WHERE commit_sha = ? AND status = 'failed'", (commit,))
    return conn.execute(
        "INSERT INTO builds (commit_sha, version, code, notes, file, created) VALUES (?, ?, ?, ?, ?, ?)",
        (commit, version, code, notes.strip()[:1000], file, now()),
    ).lastrowid


def pending_builds(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM builds WHERE status = 'new' ORDER BY id").fetchall()


def finish_build(conn: sqlite3.Connection, build_id: int, status: str, error: str = "", release_id: int | None = None) -> None:
    conn.execute("UPDATE builds SET status = ?, error = ?, release_id = ?, finished = ? WHERE id = ?",
                 (status, error[:500], release_id, now(), build_id))


def unnotified_builds(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT b.*, r.size AS release_size, r.published AS release_published, r.notes AS release_notes, r.channel AS release_channel "
        "FROM builds b LEFT JOIN releases r ON r.id = b.release_id "
        "WHERE b.status IN ('done', 'failed') AND b.notified = 0 ORDER BY b.id"
    ).fetchall()
    return [dict(r) for r in rows]


def mark_build_notified(conn: sqlite3.Connection, build_id: int) -> None:
    conn.execute("UPDATE builds SET notified = 1 WHERE id = ?", (build_id,))


def add_play_publish(conn: sqlite3.Connection, version: str, code: int | None, tracks: str, status: str,
                     error: str = "") -> None:
    conn.execute("INSERT INTO play_publishes(version, version_code, tracks, status, error, created) VALUES (?,?,?,?,?,?)",
                 (version, code, tracks, status, error[:500], now()))


def release_notes_for(conn: sqlite3.Connection, version: str) -> str:
    row = conn.execute("SELECT notes FROM releases WHERE version = ? ORDER BY id DESC LIMIT 1", (version,)).fetchone()
    return row[0] if row else ""


def unnotified_play_publishes(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM play_publishes WHERE notified = 0 ORDER BY id").fetchall()]


def mark_play_publish_notified(conn: sqlite3.Connection, publish_id: int) -> None:
    conn.execute("UPDATE play_publishes SET notified = 1 WHERE id = ?", (publish_id,))


def stats(conn: sqlite3.Connection) -> dict:
    t = now()
    one = lambda q, *a: conn.execute(q, a).fetchone()[0]  # noqa: E731
    return {
        "players": one("SELECT COUNT(*) FROM players"),
        "players_day": one("SELECT COUNT(*) FROM players WHERE seen > ?", t - 86400),
        "players_new_day": one("SELECT COUNT(*) FROM players WHERE created > ?", t - 86400),
        "messages_day": one("SELECT COUNT(*) FROM messages WHERE created > ?", t - 86400),
        "reports_open": one("SELECT COUNT(*) FROM reports WHERE status = 'open'"),
        "bans_active": one("SELECT COUNT(*) FROM bans WHERE lifted IS NULL AND (until IS NULL OR until > ?)", t),
    }

