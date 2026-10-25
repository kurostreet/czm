"""In-game moderation by the official SUPPORT account.

The role belongs to a server player ID (granted with `python -m czm.cli support-grant <id>`),
never to a nick, an email sent by a client or a tag. Every moderation request is checked
here; a hidden button in an ordinary game is not a permission.

Sanctions share the bans table with the bot's bans: kind 'ban' closes everything,
'text' the chat, private messages, status and lobby messages, 'voice' the lobby voice,
'photo' the own photo. A player and the phone he was on are matched, like bans.
"""
import sqlite3

from . import accounts, service, social
from .db import now

ROLE = "support"
SANCTIONS = {"mute_text": "text", "mute_voice": "voice", "restrict_photo": "photo", "ban": "ban"}
ACTIONS = set(SANCTIONS) | {"delete_message", "remove_avatar", "warn", "dismiss", "close_lobby"}
MAX_MINUTES = 365 * 24 * 60
FOREVER_ALLOWED = {"ban", "restrict_photo"}
REPORT_STATUS = {"delete_message": "deleted", "remove_avatar": "deleted", "close_lobby": "deleted",
                 "warn": "warned", "mute_text": "muted", "mute_voice": "muted",
                 "restrict_photo": "deleted", "ban": "banned", "dismiss": "dismissed"}
PAGE = 30


# the role ----------------------------------------------------------------------

def role(conn: sqlite3.Connection, player_id: int) -> str:
    row = conn.execute("SELECT role FROM staff WHERE player=?", (player_id,)).fetchone()
    return row["role"] if row else ""


def grant(conn: sqlite3.Connection, player_id: int) -> dict:
    player = conn.execute("SELECT p.id, p.nick FROM players p JOIN accounts a ON a.player=p.id WHERE p.id=?",
                          (player_id,)).fetchone()
    if player is None:
        raise accounts.AuthError("account_not_found", 404)  # only a registered account keeps the role
    conn.execute("INSERT INTO staff(player, role, granted) VALUES(?,?,?) ON CONFLICT(player) DO UPDATE SET role=excluded.role",
                 (player_id, ROLE, now()))
    return {"id": player["id"], "nick": player["nick"], "role": ROLE}


def revoke(conn: sqlite3.Connection, player_id: int) -> bool:
    return conn.execute("DELETE FROM staff WHERE player=?", (player_id,)).rowcount > 0


def support_actor(conn: sqlite3.Connection, key: str) -> sqlite3.Row:
    player = social.actor(conn, key)
    if role(conn, player["id"]) != ROLE:
        raise accounts.AuthError("forbidden", 403)
    return player


# what a player is under ------------------------------------------------------------

def _player(conn, player):
    if isinstance(player, sqlite3.Row):
        return player
    return conn.execute("SELECT * FROM players WHERE id=?", (player,)).fetchone()


def sanction(conn: sqlite3.Connection, player, kind: str) -> dict | None:
    """The active text/voice/photo restriction of a player (or of his phone), or None."""
    row = _player(conn, player)
    if row is None:
        return None
    s = conn.execute(
        "SELECT * FROM bans WHERE kind=? AND lifted IS NULL AND (until IS NULL OR until > ?) "
        "AND (player=? OR (device_hash != '' AND device_hash=?)) ORDER BY until IS NULL DESC, until DESC LIMIT 1",
        (kind, now(), row["id"], row["device_hash"])).fetchone()
    if s is None:
        return None
    return {"id": s["id"], "until": s["until"] or 0, "forever": s["until"] is None, "reason": s["reason"]}


def require_text(conn: sqlite3.Connection, player) -> None:
    if sanction(conn, player, "text"):
        raise accounts.AuthError("muted", 403)


def state(conn: sqlite3.Connection, player: sqlite3.Row) -> dict:
    """What the game tells the player: his restrictions and the oldest warning not yet shown."""
    warning = conn.execute("SELECT id, reason, created FROM warnings WHERE player=? AND seen=0 ORDER BY id LIMIT 1",
                           (player["id"],)).fetchone()
    return {"text": sanction(conn, player, "text"), "voice": sanction(conn, player, "voice"),
            "photo": sanction(conn, player, "photo"),
            "warning": dict(warning) if warning else None}


def warning_seen(conn: sqlite3.Connection, key: str, warning_id: int) -> dict:
    player = service.player_by_key(conn, key or "")
    if player is None:
        raise accounts.AuthError("hello", 401)
    conn.execute("UPDATE warnings SET seen=? WHERE id=? AND player=?", (now(), warning_id, player["id"]))
    return {"moderation": state(conn, player)}


# the panel -------------------------------------------------------------------------

def _person(conn, player_id):
    row = conn.execute("SELECT id, nick, avatar, avatar_rev FROM players WHERE id=?", (player_id,)).fetchone()
    if row is None:
        return {"id": player_id, "nick": "", "avatar": ""}
    return {"id": row["id"], "nick": row["nick"], "avatar": service.avatar_ref(row)}


def summary(conn: sqlite3.Connection, key: str) -> dict:
    support_actor(conn, key)
    t = now()
    return {"reports_open": conn.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0],
            "sanctions_active": conn.execute(
                "SELECT COUNT(*) FROM bans WHERE lifted IS NULL AND (until IS NULL OR until > ?)", (t,)).fetchone()[0]}


def reports(conn: sqlite3.Connection, key: str, offset: int = 0) -> dict:
    support_actor(conn, key)
    rows = conn.execute("SELECT id FROM reports WHERE status='open' ORDER BY id DESC LIMIT ? OFFSET ?",
                        (PAGE + 1, max(0, offset))).fetchall()
    items = []
    for r in rows[:PAGE]:
        info = service.report_info(conn, r["id"])
        if info is None:
            continue
        items.append({"id": info["id"], "kind": info["kind"], "evidence": info["evidence"], "context": info["context"],
                      "target": _person(conn, info["target"]), "reporter": info["reporter"],
                      "reports_week": info["reports_week"],
                      "created": conn.execute("SELECT created FROM reports WHERE id=?", (info["id"],)).fetchone()[0]})
    return {"reports": items, "next": offset + PAGE if len(rows) > PAGE else -1}


def sanctions(conn: sqlite3.Connection, key: str) -> dict:
    support_actor(conn, key)
    rows = conn.execute(
        "SELECT * FROM bans WHERE lifted IS NULL AND (until IS NULL OR until > ?) ORDER BY id DESC LIMIT 60",
        (now(),)).fetchall()
    return {"sanctions": [{"id": r["id"], "kind": r["kind"], "target": _person(conn, r["player"]),
                           "until": r["until"] or 0, "forever": r["until"] is None, "reason": r["reason"],
                           "created": r["created"], "moderator": r["moderator"]} for r in rows]}


def history(conn: sqlite3.Connection, key: str, offset: int = 0) -> dict:
    support_actor(conn, key)
    rows = conn.execute("SELECT * FROM moderation_log ORDER BY id DESC LIMIT ? OFFSET ?",
                        (PAGE + 1, max(0, offset))).fetchall()
    return {"history": [{"id": r["id"], "action": r["action"], "target": _person(conn, r["target"]),
                         "moderator": _person(conn, r["moderator"]), "reason": r["reason"],
                         "until": r["until"] or 0, "evidence": r["evidence"], "created": r["created"]}
                        for r in rows[:PAGE]],
            "next": offset + PAGE if len(rows) > PAGE else -1}


def player(conn: sqlite3.Connection, key: str, target: int, message: int = 0, lobby_message: int = 0) -> dict:
    """The card a moderator acts from: who it is, what he is under, the message in question."""
    support_actor(conn, key)
    row = _player(conn, target)
    if row is None:
        raise accounts.AuthError("not_found", 404)
    ban = service.active_ban(conn, row)
    quoted = None
    if message:
        m = conn.execute("SELECT id, text, room FROM messages WHERE id=? AND player=? AND deleted=0", (message, target)).fetchone()
        quoted = {"message": m["id"], "text": m["text"], "context": m["room"]} if m else None
    elif lobby_message:
        m = conn.execute("SELECT m.id, m.text, l.title FROM lobby_messages m JOIN lobbies l ON l.id=m.lobby "
                         "WHERE m.id=? AND m.sender=? AND m.deleted=0", (lobby_message, target)).fetchone()
        quoted = {"lobby_message": m["id"], "text": m["text"], "context": m["title"]} if m else None
    return {"target": _person(conn, target), "role": role(conn, target), "quote": quoted,
            "ban": ban, "moderation": {k: v for k, v in state(conn, row).items() if k != "warning"},
            "reports_week": conn.execute("SELECT COUNT(*) FROM reports WHERE target=? AND created>?",
                                         (target, now() - 7 * 86400)).fetchone()[0]}


# actions ---------------------------------------------------------------------------

def _logged(conn, moderator, nonce):
    if not nonce:
        return None
    row = conn.execute("SELECT * FROM moderation_log WHERE moderator=? AND nonce=?", (moderator, nonce)).fetchone()
    return row


def act(conn: sqlite3.Connection, key: str, target: int, action: str, minutes: int | None, reason: str,
        report: int | None = None, message: int | None = None, lobby_message: int | None = None,
        nonce: str = "") -> dict:
    moderator = support_actor(conn, key)
    if action not in ACTIONS:
        raise accounts.AuthError("action")
    reason = service.clean_text(reason or "", 200)
    previous = _logged(conn, moderator["id"], nonce)
    if previous is not None:
        if previous["target"] != target or previous["action"] != action:
            raise accounts.AuthError("nonce", 409)
        return {"ok": True, "log": previous["id"], "repeated": True}
    row = _player(conn, target)
    if row is None:
        raise accounts.AuthError("not_found", 404)
    if target == moderator["id"]:
        raise accounts.AuthError("self")
    if role(conn, target):
        raise accounts.AuthError("staff", 403)

    info = None
    if report:
        info = service.report_info(conn, report)
        # the complaint must be about this very player: never punish a neighbour by mistake
        if info is None or info["target"] != target:
            raise accounts.AuthError("target", 409)
    evidence = info["evidence"] if info else ""
    t = now()
    until = None
    sanction_id = None

    if action in SANCTIONS:
        if minutes is None or minutes < 0 or minutes > MAX_MINUTES or (minutes == 0 and action not in FOREVER_ALLOWED):
            raise accounts.AuthError("minutes")
        if not reason:
            raise accounts.AuthError("reason")
        until = t + minutes * 60 if minutes else None
        sanction_id = conn.execute(
            "INSERT INTO bans(player, device_hash, until, reason, created, kind, moderator) VALUES(?,?,?,?,?,?,?)",
            (target, row["device_hash"], until, reason, t, SANCTIONS[action], moderator["id"])).lastrowid
        if action == "restrict_photo":
            service.reset_avatar(conn, target)
        if action == "ban" and info and info["kind"] in service.MESSAGE_REPORTS + ("lobby", "profile"):
            service.remove_report_content(conn, info)
    elif action == "warn":
        if not reason:
            raise accounts.AuthError("reason")
        conn.execute("INSERT INTO warnings(player, reason, created) VALUES(?,?,?)", (target, reason, t))
    elif action == "remove_avatar":
        service.reset_avatar(conn, target)
    elif action == "delete_message":
        if info and info["kind"] in service.MESSAGE_REPORTS:
            service.delete_report_message(conn, info)
        elif message:
            m = conn.execute("SELECT player, text FROM messages WHERE id=?", (message,)).fetchone()
            if m is None or m["player"] != target:
                raise accounts.AuthError("target", 409)
            service.delete_message(conn, message)
            evidence = m["text"]
        elif lobby_message:
            m = conn.execute("SELECT sender, text FROM lobby_messages WHERE id=?", (lobby_message,)).fetchone()
            if m is None or m["sender"] != target:
                raise accounts.AuthError("target", 409)
            conn.execute("UPDATE lobby_messages SET deleted=1 WHERE id=?", (lobby_message,))
            evidence = m["text"]
        else:
            raise accounts.AuthError("message")
    elif action == "close_lobby":
        if not info or info["kind"] != "lobby":
            raise accounts.AuthError("lobby")
        service.remove_report_content(conn, info)
    elif action == "dismiss":
        if not info:
            raise accounts.AuthError("report")

    if info and info["status"] == "open":
        service.resolve_report(conn, report, REPORT_STATUS[action])
    if action == "ban":
        conn.execute("UPDATE reports SET status='banned', resolved=? WHERE target=? AND status='open'", (t, target))
    log = conn.execute(
        "INSERT INTO moderation_log(moderator, target, action, reason, until, sanction, report, evidence, created, nonce) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (moderator["id"], target, action, reason, until, sanction_id, report, evidence[:2000], t, nonce or None)).lastrowid
    return {"ok": True, "log": log, "until": until or 0, "forever": action in SANCTIONS and until is None}


def lift(conn: sqlite3.Connection, key: str, sanction_id: int, nonce: str = "") -> dict:
    moderator = support_actor(conn, key)
    previous = _logged(conn, moderator["id"], nonce)
    if previous is not None:
        return {"ok": True, "log": previous["id"], "repeated": True}
    s = conn.execute("SELECT * FROM bans WHERE id=?", (sanction_id,)).fetchone()
    if s is None:
        raise accounts.AuthError("not_found", 404)
    if s["lifted"] is None:
        conn.execute("UPDATE bans SET lifted=? WHERE id=?", (now(), sanction_id))
    log = conn.execute(
        "INSERT INTO moderation_log(moderator, target, action, reason, sanction, created, nonce) VALUES(?,?,?,?,?,?,?)",
        (moderator["id"], s["player"], "lift", s["kind"], sanction_id, now(), nonce or None)).lastrowid
    return {"ok": True, "log": log}
