"""Ephemeral CZM pre-match rooms. Server authority; no game-server reservations."""
import re
import secrets
import unicodedata
import json
import hashlib

from . import accounts, service, social, links
from .db import now

LOBBY_SCHEMA = """
CREATE TABLE IF NOT EXISTS lobbies (
 id TEXT PRIMARY KEY, owner INTEGER NOT NULL REFERENCES accounts(player),
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 visibility TEXT NOT NULL CHECK(visibility IN ('public','private')),
 capacity INTEGER NOT NULL CHECK(capacity BETWEEN 2 AND 6),
 server TEXT NOT NULL, proto TEXT NOT NULL CHECK(proto IN ('gs','49')),
 revision INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL,
 last_seen INTEGER NOT NULL,
 voice_mute_all INTEGER NOT NULL DEFAULT 0,
 CHECK(length(title) BETWEEN 3 AND 160)
);
CREATE TABLE IF NOT EXISTS lobby_members (
 player INTEGER PRIMARY KEY REFERENCES accounts(player),
 lobby TEXT NOT NULL REFERENCES lobbies(id) ON DELETE CASCADE,
 ready_revision INTEGER NOT NULL DEFAULT 0,
 joined INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS lobby_members_lobby ON lobby_members(lobby,joined);
CREATE TABLE IF NOT EXISTS lobby_voice_mutes (
 lobby TEXT NOT NULL REFERENCES lobbies(id) ON DELETE CASCADE,
 player INTEGER NOT NULL REFERENCES accounts(player),
 host_muted INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(lobby,player)
);
CREATE TABLE IF NOT EXISTS lobby_moderation (
 player INTEGER PRIMARY KEY REFERENCES accounts(player),
 warnings INTEGER NOT NULL DEFAULT 0,
 level INTEGER NOT NULL DEFAULT 0,
 mute_until INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lobby_moderation_ops (
 player INTEGER NOT NULL REFERENCES accounts(player),
 kind TEXT NOT NULL,
 nonce TEXT NOT NULL,
 body_hash TEXT NOT NULL,
 response_json TEXT NOT NULL,
 created INTEGER NOT NULL,
 PRIMARY KEY(player,kind,nonce)
);

CREATE TABLE IF NOT EXISTS lobby_messages (
 id INTEGER PRIMARY KEY, lobby TEXT NOT NULL REFERENCES lobbies(id) ON DELETE CASCADE,
 sender INTEGER NOT NULL REFERENCES accounts(player),
 text TEXT NOT NULL, created INTEGER NOT NULL, nonce TEXT NOT NULL,
 UNIQUE(sender,nonce)
);
CREATE INDEX IF NOT EXISTS lobby_messages_history ON lobby_messages(lobby,id);
CREATE TABLE IF NOT EXISTS lobby_creation_ops (
 player INTEGER NOT NULL REFERENCES accounts(player),
 nonce TEXT NOT NULL, lobby TEXT NOT NULL,
 created INTEGER NOT NULL, PRIMARY KEY(player,nonce)
);

CREATE TABLE IF NOT EXISTS lobby_invites (
 id TEXT PRIMARY KEY,
 lobby TEXT NOT NULL REFERENCES lobbies(id) ON DELETE CASCADE,
 sender INTEGER NOT NULL REFERENCES accounts(player),
 target INTEGER NOT NULL REFERENCES accounts(player),
 nonce TEXT NOT NULL,
 created INTEGER NOT NULL,
 expires INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','accepted','declined','superseded')),
 UNIQUE(sender, nonce)
);
CREATE INDEX IF NOT EXISTS lobby_invites_target
 ON lobby_invites(target,status,expires);
CREATE INDEX IF NOT EXISTS lobby_invites_lobby
 ON lobby_invites(lobby,status);
CREATE TABLE IF NOT EXISTS lobby_launches (
 id TEXT PRIMARY KEY,
 lobby_id TEXT NOT NULL UNIQUE,
 owner INTEGER NOT NULL REFERENCES accounts(player),
 nonce TEXT NOT NULL,
 server TEXT NOT NULL,
 proto TEXT NOT NULL CHECK(proto IN ('gs','49')),
 size INTEGER NOT NULL CHECK(size BETWEEN 2 AND 6),
 created INTEGER NOT NULL,
 delivery_expires INTEGER NOT NULL,
 episode_expires INTEGER NOT NULL,
 UNIQUE(owner,nonce)
);
CREATE TABLE IF NOT EXISTS launch_members (
 launch TEXT NOT NULL REFERENCES lobby_launches(id) ON DELETE CASCADE,
 player INTEGER NOT NULL REFERENCES accounts(player),
 last_seen INTEGER NOT NULL DEFAULT 0,
 departed_at INTEGER NOT NULL DEFAULT 0,
 ended INTEGER NOT NULL DEFAULT 0,
 delivered_at INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(launch,player)
);
CREATE INDEX IF NOT EXISTS launch_members_player ON launch_members(player,launch);
"""

TITLE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
HOST_TTL = 120  # owner heartbeat at least once per 30 seconds

NONCE = re.compile(r"[A-Za-z0-9_-]{12,64}\Z")


def _actor(conn, key):
    actor = social.actor(conn, key)
    if service.active_ban(conn, actor):
        raise accounts.AuthError("banned", 403)
    return actor["id"]


def _title(value):
    text = unicodedata.normalize("NFKC", value).strip()
    if not 3 <= len(text) <= 40 or TITLE_CONTROL.search(text) or not text.strip():
        raise accounts.AuthError("title")
    # Name/content moderation is separate from links, with sanctions added later.
    return text


def _nonce(value):
    if not NONCE.fullmatch(value or ""):
        raise accounts.AuthError("nonce")
    return value


def _room(conn, room):
    result = conn.execute("SELECT * FROM lobbies WHERE id=?", (room,)).fetchone()
    if result is None or result["last_seen"] <= now()-HOST_TTL:
        raise accounts.AuthError("lobby_not_found", 404)
    return result


def _membership(conn, room, player):
    item = conn.execute("SELECT * FROM lobby_members WHERE player=? AND lobby=?", (player, room)).fetchone()
    if not item:
        raise accounts.AuthError("not_in_lobby", 403)
    return item



def _map_for_server(conn, address):
    """Optional map name from a *currently authenticated* player's live status.

    Thumbnails themselves come from the existing shared VDS map-picture
    system. A missing / unverified map is an empty string, not a guess.
    """
    from .social import PRESENCE_TTL
    seen=now()
    row=conn.execute(
        "SELECT pr.map FROM social_presence pr JOIN account_sessions sess "
        "ON sess.token_hash=pr.owner AND sess.player=pr.player "
        "WHERE pr.server=? AND pr.map!='' AND pr.seen>? "
        "AND sess.expires>? AND sess.seen>? "
        "ORDER BY pr.seen DESC LIMIT 1",
        (address,seen-PRESENCE_TTL,seen,seen-accounts.SESSION_IDLE)).fetchone()
    return row["map"] if row else ""


def _state(conn, room):
    people = conn.execute(
        "SELECT m.player, m.ready_revision, p.nick, p.avatar FROM lobby_members m "
        "JOIN players p ON p.id=m.player WHERE m.lobby=? ORDER BY m.joined,m.player",
        (room["id"],)).fetchall()
    voice_muted=conn.execute(
        "SELECT player FROM lobby_voice_mutes WHERE lobby=? AND host_muted=1",
        (room["id"],)).fetchall()
    return {"id": room["id"], "title": room["title"], "description": room["description"],
            "visibility": room["visibility"], "owner": room["owner"],
             "capacity": room["capacity"], "server": room["server"], "proto": room["proto"],
            "map": _map_for_server(conn,room["server"]),
            "voice_mute_all": bool(room["voice_mute_all"]),
            "voice_muted": [r["player"] for r in voice_muted],
            "revision": room["revision"], "members": [
                {"id": p["player"], "nick": p["nick"], "avatar": p["avatar"],
                 "ready": p["ready_revision"] == room["revision"]} for p in people]}


def _current(conn, player):
    return conn.execute(
        "SELECT l.* FROM lobbies l JOIN lobby_members m ON m.lobby=l.id "
        "WHERE m.player=? AND l.last_seen>?",
        (player, now()-HOST_TTL)).fetchone()


# Each cycle gives three warnings; the next violation escalates the mute.
# Punishments apply only to lobby speech and titles, never to game-server voice.
MUTE_DURATIONS = (600,3600,86400)


def moderate(conn, player, body, nonce, kind):
    _nonce(nonce)
    digest=hashlib.sha256(body.encode("utf-8")).hexdigest()
    prior=conn.execute("SELECT * FROM lobby_moderation_ops "
                       "WHERE player=? AND kind=? AND nonce=?",
                       (player,kind,nonce)).fetchone()
    if prior:
        if prior["body_hash"]!=digest:
            raise accounts.AuthError("nonce",409)
        return json.loads(prior["response_json"])
    row=conn.execute("SELECT * FROM lobby_moderation WHERE player=?",(player,)).fetchone()
    t=now()
    response=None
    if row and row["mute_until"]>t:
        response={"error":"lobby_muted","mute_until":row["mute_until"],
                  "level":row["level"],"_status":429}
    elif service.profanity.clean(body)!=links.clean(body):
        warnings=(row["warnings"] if row else 0)+1
        level=row["level"] if row else 0
        if warnings>3:
            level=min(level+1,len(MUTE_DURATIONS))
            until=t+MUTE_DURATIONS[level-1]
            warnings=0
            response={"error":"lobby_muted","mute_until":until,"level":level,"_status":429}
        else:
            until=0
            response={"error":"language_warning","warnings":warnings,"_status":422}
        conn.execute("INSERT INTO lobby_moderation(player,warnings,level,mute_until)"
                     " VALUES(?,?,?,?) ON CONFLICT(player) DO UPDATE SET "
                     "warnings=excluded.warnings,level=excluded.level,"
                     "mute_until=excluded.mute_until",
                     (player,warnings,level,until))
    if response is not None:
        conn.execute("INSERT INTO lobby_moderation_ops "
                     "(player,kind,nonce,body_hash,response_json,created) "
                     "VALUES(?,?,?,?,?,?)",
                     (player,kind,nonce,digest,json.dumps(response),t))
    return response


def create(conn, key, title, description, visibility, capacity, server, proto, nonce):
    player = _actor(conn, key)
    _nonce(nonce)
    title = _title(title)
    description = unicodedata.normalize("NFKC", description).strip()
    if len(description) > 120 or TITLE_CONTROL.search(description):
        raise accounts.AuthError("description")
    result=moderate(conn,player,title+"\n"+description,nonce,"create")
    if result:
        return result
    if visibility not in ("public", "private") or type(capacity) is not int or capacity not in range(2, 7):
        raise accounts.AuthError("settings")
    if not social._valid_server(server) or proto not in ("gs", "49"):
        raise accounts.AuthError("server")
    old = conn.execute("SELECT * FROM lobby_creation_ops WHERE player=? AND nonce=?", (player, nonce)).fetchone()
    if old:
        room = conn.execute("SELECT * FROM lobbies WHERE id=?", (old["lobby"],)).fetchone()
        if room and (room["title"], room["description"], room["visibility"], room["capacity"],
                     room["server"], room["proto"]) == (title, description, visibility, capacity, server, proto):
            return {"lobby": _state(conn, room)}
        raise accounts.AuthError("nonce", 409)
    if _current(conn, player):
        raise accounts.AuthError("already_in_lobby", 409)
    accounts.rate(conn, "lobby_create", str(player), 10, 3600)
    room_id = secrets.token_urlsafe(15)
    t = now()
    conn.execute("INSERT INTO lobbies(id,owner,title,description,visibility,capacity,server,proto,created,last_seen) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (room_id, player, title, description, visibility, capacity, server, proto, t,t))
    conn.execute("INSERT INTO lobby_members(player,lobby,joined) VALUES (?,?,?)",
                 (player, room_id, now()))
    conn.execute("INSERT INTO lobby_creation_ops(player,nonce,lobby,created) VALUES (?,?,?,?)",
                 (player, nonce, room_id, now()))
    return {"lobby": _state(conn, _room(conn, room_id))}


def mine(conn, key):
    player = _actor(conn, key)
    room = _current(conn, player)
    return {"lobby": _state(conn, room) if room else None}


def catalog(conn, key, offset=0):
    _actor(conn, key)
    rows = conn.execute("SELECT l.*, (SELECT COUNT(*) FROM lobby_members m WHERE m.lobby=l.id) AS count "
                        "FROM lobbies l WHERE l.visibility='public' AND l.last_seen>? "
                        "ORDER BY l.created DESC,l.id DESC LIMIT 41 OFFSET ?",
                        (now()-HOST_TTL,max(0,offset))).fetchall()
    return {"lobbies": [{"id": l["id"], "title": l["title"], "owner": l["owner"],
                        "capacity": l["capacity"], "count": l["count"],
                        "server": l["server"], "proto": l["proto"],
                        "map": _map_for_server(conn,l["server"])} for l in rows[:40]],
            "next": max(0,offset)+40 if len(rows)>40 else -1}


def detail(conn, key, room_id):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    _membership(conn, room_id, player)
    if player == room["owner"]:
        conn.execute("UPDATE lobbies SET last_seen=? WHERE id=?", (now(),room_id))
    return {"lobby": _state(conn, room)}


def join(conn, key, room_id):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if _current(conn, player):
        if conn.execute("SELECT 1 FROM lobby_members WHERE player=? AND lobby=?", (player, room_id)).fetchone():
            return {"lobby": _state(conn, room)}
        raise accounts.AuthError("already_in_lobby", 409)
    if room["visibility"] != "public":
        raise accounts.AuthError("invite_required", 403)
    if social.blocked(conn, player, room["owner"]):
        raise accounts.AuthError("unavailable", 403)
    if conn.execute("SELECT COUNT(*) FROM lobby_members WHERE lobby=?", (room_id,)).fetchone()[0] >= room["capacity"]:
        raise accounts.AuthError("lobby_full", 409)
    conn.execute("INSERT INTO lobby_members(player,lobby,joined) VALUES (?,?,?)",
                 (player, room_id, now()))
    return {"lobby": _state(conn, room)}


def leave(conn, key, room_id):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    _membership(conn, room_id, player)
    if player == room["owner"]:
        conn.execute("DELETE FROM lobbies WHERE id=?", (room_id,))
        return {"closed": True}
    conn.execute("DELETE FROM lobby_members WHERE lobby=? AND player=?", (room_id, player))
    return {"closed": False}


def ready(conn, key, room_id, revision, value):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    _membership(conn, room_id, player)
    if revision != room["revision"]:
        raise accounts.AuthError("stale_revision", 409)
    conn.execute("UPDATE lobby_members SET ready_revision=? WHERE lobby=? AND player=?",
                 (revision if value else 0, room_id, player))
    return {"lobby": _state(conn, room)}


def change_server(conn, key, room_id, server, proto):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if player != room["owner"]:
        raise accounts.AuthError("not_owner", 403)
    if not social._valid_server(server) or proto not in ("gs", "49"):
        raise accounts.AuthError("server")
    if (server, proto) != (room["server"], room["proto"]):
        conn.execute("UPDATE lobbies SET server=?,proto=?,revision=revision+1 WHERE id=?",
                     (server, proto, room_id))
        conn.execute("UPDATE lobby_members SET ready_revision=0 WHERE lobby=?", (room_id,))
    return {"lobby": _state(conn, _room(conn, room_id))}


def transfer(conn, key, room_id, target):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if player != room["owner"]:
        raise accounts.AuthError("not_owner", 403)
    _membership(conn, room_id, target)
    # Previous invitations must not survive a transfer of room authority.
    conn.execute("UPDATE lobby_invites SET status='superseded' "
                 "WHERE lobby=? AND status='pending'", (room_id,))
    conn.execute("UPDATE lobbies SET owner=?,last_seen=? WHERE id=?", (target,now(),room_id))
    return {"lobby": _state(conn, _room(conn, room_id))}


def kick(conn, key, room_id, target):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if player != room["owner"] or target == player:
        raise accounts.AuthError("not_owner", 403)
    _membership(conn, room_id, target)
    conn.execute("DELETE FROM lobby_members WHERE lobby=? AND player=?", (room_id, target))
    return {"lobby": _state(conn, room)}


def chat(conn, key, room_id, before=0):
    player = _actor(conn, key)
    _room(conn, room_id)
    _membership(conn, room_id, player)
    rows = conn.execute(
        "SELECT m.id,m.sender,p.nick,m.text,m.created FROM lobby_messages m "
        "JOIN players p ON p.id=m.sender "
        "WHERE m.lobby=? AND (?=0 OR m.id<?) ORDER BY m.id DESC LIMIT 50",
        (room_id,before,before)).fetchall()
    return {"messages": [dict(r) for r in reversed(rows)]}


def send(conn, key, room_id, text, nonce):
    player = _actor(conn, key)
    _nonce(nonce)
    _room(conn, room_id)
    _membership(conn, room_id, player)
    raw=service.clean_text(text,400)
    if not raw:
        raise accounts.AuthError("empty")
    result=moderate(conn,player,raw,nonce,"message")
    if result:
        return result
    text=service.profanity.clean(raw)
    old = conn.execute("SELECT * FROM lobby_messages WHERE sender=? AND nonce=?", (player, nonce)).fetchone()
    if old:
        if old["lobby"] != room_id or old["text"] != text:
            raise accounts.AuthError("nonce", 409)
        return {"message": dict(old)}
    accounts.rate(conn, "lobby_send", str(player), 30, 60)
    cur = conn.execute("INSERT INTO lobby_messages(lobby,sender,text,created,nonce) VALUES (?,?,?,?,?)",
                       (room_id, player, text, now(), nonce))
    return {"message": dict(conn.execute("SELECT * FROM lobby_messages WHERE id=?", (cur.lastrowid,)).fetchone())}


INVITE_SECONDS = 15 * 60


def _invite_row(row):
    return {"id": row["id"], "lobby": row["lobby"], "sender": row["sender"],
            "target": row["target"], "created": row["created"],
            "expires": row["expires"], "status": row["status"]}


def invite(conn, key, room_id, target, nonce):
    """An owner invites a friend using a durable, recipient-bound, expiring card."""
    player = _actor(conn, key)
    _nonce(nonce)
    room = _room(conn, room_id)
    if player != room["owner"]:
        raise accounts.AuthError("not_owner", 403)
    social.account(conn, target)
    if target == player:
        raise accounts.AuthError("self")
    if social.relation(conn, player, target) != "friend":
        raise accounts.AuthError("not_friends", 403)
    existing = conn.execute("SELECT * FROM lobby_invites WHERE sender=? AND nonce=?",
                            (player, nonce)).fetchone()
    if existing:
        if existing["lobby"] != room_id or existing["target"] != target:
            raise accounts.AuthError("nonce", 409)
        return {"invite": _invite_row(existing)}
    if _current(conn, target):
        raise accounts.AuthError("already_in_lobby", 409)
    pending = conn.execute("SELECT * FROM lobby_invites WHERE lobby=? AND target=? "
                           "AND status='pending' AND expires>? ORDER BY created DESC LIMIT 1",
                           (room_id, target, now())).fetchone()
    if pending:
        return {"invite": _invite_row(pending)}
    accounts.rate(conn, "lobby_invite", str(player), 20, 3600)
    invitation = secrets.token_urlsafe(18)
    t = now()
    conn.execute("UPDATE lobby_invites SET status='superseded' WHERE lobby=? AND target=? "
                 "AND status='pending'", (room_id, target))
    conn.execute("INSERT INTO lobby_invites(id,lobby,sender,target,nonce,created,expires) "
                 "VALUES(?,?,?,?,?,?,?)", (invitation, room_id, player, target, nonce, t, t+INVITE_SECONDS))
    return {"invite": _invite_row(conn.execute("SELECT * FROM lobby_invites WHERE id=?",
                                              (invitation,)).fetchone())}


def invitations(conn, key):
    player = _actor(conn, key)
    entries = conn.execute(
        "SELECT i.*, l.title, l.description, l.owner, l.server, l.proto, l.capacity "
        "FROM lobby_invites i JOIN lobbies l ON l.id=i.lobby "
        "WHERE i.target=? AND i.status='pending' AND i.expires>? "
        "AND NOT EXISTS (SELECT 1 FROM social_blocks b WHERE "
        "(b.source=i.target AND (b.target=i.sender OR b.target=l.owner)) "
        "OR (b.target=i.target AND (b.source=i.sender OR b.source=l.owner))) "
        "ORDER BY i.created DESC LIMIT 40", (player, now())).fetchall()
    return {"invites": [
        {"id": r["id"], "lobby": r["lobby"], "sender": r["sender"],
         "owner": r["owner"], "title": r["title"], "description": r["description"],
         "server": r["server"], "proto": r["proto"],
         "capacity": r["capacity"], "expires": r["expires"],
         "map": _map_for_server(conn,r["server"])} for r in entries]}


def answer_invitation(conn, key, invitation, accept):
    player = _actor(conn, key)
    row = conn.execute("SELECT * FROM lobby_invites WHERE id=? AND target=?",
                       (invitation, player)).fetchone()
    if not row:
        raise accounts.AuthError("invite_not_found", 404)
    if row["status"] == "accepted" and accept:
        room = conn.execute("SELECT * FROM lobbies WHERE id=?", (row["lobby"],)).fetchone()
        if room and conn.execute("SELECT 1 FROM lobby_members WHERE player=? AND lobby=?",
                                 (player, row["lobby"])).fetchone():
            return {"accepted": True, "lobby": _state(conn, room)}
        raise accounts.AuthError("invite_consumed", 409)
    if row["status"] != "pending":
        raise accounts.AuthError("invite_consumed", 409)
    if row["expires"] <= now():
        raise accounts.AuthError("invite_expired", 410)
    if not accept:
        conn.execute("UPDATE lobby_invites SET status='declined' WHERE id=?", (invitation,))
        return {"accepted": False}
    room = _room(conn, row["lobby"])
    if social.relation(conn, player, room["owner"]) != "friend" or social.blocked(
            conn, player, row["sender"]):
        raise accounts.AuthError("unavailable", 403)
    current = _current(conn, player)
    if current:
        raise accounts.AuthError("already_in_lobby", 409)
    if conn.execute("SELECT COUNT(*) FROM lobby_members WHERE lobby=?", (row["lobby"],)).fetchone()[0] >= room["capacity"]:
        raise accounts.AuthError("lobby_full", 409)
    conn.execute("INSERT INTO lobby_members(player,lobby,joined) VALUES(?,?,?)",
                 (player, row["lobby"], now()))
    conn.execute("UPDATE lobby_invites SET status='accepted' WHERE id=?", (invitation,))
    return {"accepted": True, "lobby": _state(conn, room)}


def edit(conn, key, room_id, title, description, visibility, capacity):
    player = _actor(conn, key)
    room = _room(conn, room_id)
    if room["owner"] != player:
        raise accounts.AuthError("not_owner", 403)
    title = _title(title)
    description = unicodedata.normalize("NFKC", description).strip()
    if len(description) > 120 or TITLE_CONTROL.search(description):
        raise accounts.AuthError("description")
    # Edits lack an explicit nonce. Name-based digest avoids repeated warnings
    # on retries, while separate changes remain distinct actions.
    nonce="name-"+hashlib.sha256((room_id+title+description).encode()).hexdigest()[:32]
    result=moderate(conn,player,title+"\n"+description,nonce,"edit")
    if result:
        return result
    if visibility not in ("public","private") or type(capacity) is not int or capacity not in range(2,7):
        raise accounts.AuthError("settings")
    used = conn.execute("SELECT COUNT(*) FROM lobby_members WHERE lobby=?", (room_id,)).fetchone()[0]
    if capacity < used:
        raise accounts.AuthError("lobby_full", 409)
    conn.execute("UPDATE lobbies SET title=?,description=?,visibility=?,capacity=? WHERE id=?",
                 (title, description, visibility, capacity, room_id))
    return {"lobby": _state(conn, _room(conn, room_id))}

# Internal launch transaction only. The HTTP entry point must independently
# verify a fresh game-server response and sufficient free slots before calling.
# Do not expose this in API until that preflight is implemented.
LAUNCH_DELIVERY_TTL = 15 * 60
LAUNCH_EPISODE_TTL = 6 * 3600


def _launch_state(conn, entry):
    members = conn.execute(
        "SELECT player FROM launch_members WHERE launch=? ORDER BY player",
        (entry["id"],)).fetchall()
    return {"id": entry["id"], "server": entry["server"], "proto": entry["proto"],
            "size": entry["size"], "created": entry["created"],
            "delivery_expires": entry["delivery_expires"],
            "members": [r["player"] for r in members]}


def launch_internal(conn, key, room_id, nonce, revision):
    """Atomically consume one room into an immutable, short-lived launch event.

    INTERNAL ONLY: caller must first probe the actual game server. Never
    accept client-submitted occupancy/capacity as proof of free slots.
    """
    player = _actor(conn, key)
    _nonce(nonce)
    previous = conn.execute("SELECT * FROM lobby_launches WHERE lobby_id=?",
                            (room_id,)).fetchone()
    if previous:
        if player != previous["owner"]:
            raise accounts.AuthError("not_owner", 403)
        if previous["nonce"] != nonce:
            raise accounts.AuthError("launch_already_started", 409)
        return {"launch": _launch_state(conn, previous)}
    if conn.execute("SELECT 1 FROM lobby_launches WHERE owner=? AND nonce=?",
                    (player,nonce)).fetchone():
        raise accounts.AuthError("nonce", 409)
    room = _room(conn, room_id)
    if player != room["owner"]:
        raise accounts.AuthError("not_owner", 403)
    if revision != room["revision"]:
        raise accounts.AuthError("stale_revision", 409)
    rows = conn.execute("SELECT player,ready_revision FROM lobby_members WHERE lobby=? "
                        "ORDER BY player", (room_id,)).fetchall()
    if len(rows)<2 or len(rows)>room["capacity"]:
        raise accounts.AuthError("members_not_ready", 409)
    if any(r["ready_revision"] != revision for r in rows if r["player"] != player):
        raise accounts.AuthError("members_not_ready", 409)
    launch_id = secrets.token_urlsafe(18)
    t=now()
    conn.execute("INSERT INTO lobby_launches(id,lobby_id,owner,nonce,server,proto,size,"
                 "created,delivery_expires,episode_expires) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (launch_id,room_id,player,nonce,room["server"],room["proto"],
                  len(rows),t,t+LAUNCH_DELIVERY_TTL,t+LAUNCH_EPISODE_TTL))
    conn.executemany("INSERT INTO launch_members(launch,player) VALUES(?,?)",
                     [(launch_id,r["player"]) for r in rows])
    # Delete (cascade) the room, chat, pending invitations and ready flags.
    conn.execute("DELETE FROM lobbies WHERE id=?", (room_id,))
    return {"launch": _launch_state(
        conn,conn.execute("SELECT * FROM lobby_launches WHERE id=?",(launch_id,)).fetchone())}


def pending_launch(conn, key):
    """Reconnect recovery for a member who missed the original launch event."""
    player = _actor(conn, key)
    rows=conn.execute("SELECT l.* FROM lobby_launches l "
                      "JOIN launch_members m ON m.launch=l.id "
                      "WHERE m.player=? AND m.delivered_at=0 AND l.delivery_expires>? "
                      "ORDER BY l.created DESC,l.id DESC LIMIT 5",
                      (player, now())).fetchall()
    return {"launches":[_launch_state(conn,r) for r in rows]}

# Players who missed several heartbeats or left for too long cannot make
# an old "playing together" label reappear just by selecting the same server.
LAUNCH_RECONNECT_GRACE = 120


def record_launch_presence(conn, player, current_server):
    t=now()
    rows=conn.execute(
        "SELECT m.launch,m.last_seen,m.departed_at,m.ended,l.server,"
        "l.delivery_expires FROM launch_members m "
        "JOIN lobby_launches l ON l.id=m.launch "
        "WHERE m.player=? AND l.episode_expires>? AND m.ended=0",
        (player,t)).fetchall()
    for r in rows:
        if current_server == r["server"]:
            expired_initial = not r["last_seen"] and t>r["delivery_expires"]
            expired_gap = bool(r["last_seen"] and t-r["last_seen"]>LAUNCH_RECONNECT_GRACE)
            expired_departure = bool(r["departed_at"] and t-r["departed_at"]>LAUNCH_RECONNECT_GRACE)
            if expired_initial or expired_gap or expired_departure:
                conn.execute("UPDATE launch_members SET ended=1 WHERE launch=? AND player=?",
                             (r["launch"],player))
            else:
                conn.execute("UPDATE launch_members SET last_seen=?,departed_at=0 "
                             "WHERE launch=? AND player=?", (t,r["launch"],player))
        elif current_server:
            # Changing to a different game server ends participation permanently.
            if r["last_seen"]:
                conn.execute("UPDATE launch_members SET ended=1 WHERE launch=? AND player=?",
                             (r["launch"],player))
        elif r["last_seen"] and not r["departed_at"]:
            # Connection lost: preserve a short manual reconnect window.
            conn.execute("UPDATE launch_members SET departed_at=? WHERE launch=? AND player=?",
                         (t,r["launch"],player))


def playing_together(conn, viewer, target, server, presence_ttl):
    """Return aggregate only; never expose member IDs to an outsider."""
    if not server:
        return None
    t=now()
    candidate=conn.execute(
        "SELECT l.id,l.size FROM lobby_launches l JOIN launch_members m ON m.launch=l.id "
        "WHERE m.player=? AND l.server=? AND l.episode_expires>? "
        "AND m.ended=0 AND m.last_seen>? "
        "ORDER BY l.created DESC LIMIT 1",
        (target,server,t,t-presence_ttl)).fetchone()
    if not candidate:
        return None
    total=conn.execute(
        "SELECT COUNT(DISTINCT m.player) FROM launch_members m "
        "JOIN social_presence pr ON pr.player=m.player AND pr.server=? AND pr.seen>? "
        "JOIN account_sessions a ON a.player=m.player AND a.token_hash=pr.owner "
        "AND a.expires>? AND a.seen>? "
        "WHERE m.launch=? AND m.ended=0 AND m.last_seen>? "
        "AND NOT EXISTS (SELECT 1 FROM social_blocks b WHERE "
        "(b.source=? AND b.target=m.player) OR (b.target=? AND b.source=m.player))",
        (server,t-presence_ttl,t,t-accounts.SESSION_IDLE,
         candidate["id"],t-presence_ttl,viewer,viewer)).fetchone()[0]
    if total<2:
        return None
    return {"count": total, "size": candidate["size"]}


def owner_heartbeat(conn, key, room_id):
    player=_actor(conn,key)
    room=_room(conn,room_id)
    _membership(conn,room_id,player)
    if room["owner"] != player:
        raise accounts.AuthError("not_owner",403)
    conn.execute("UPDATE lobbies SET last_seen=? WHERE id=?", (now(),room_id))
    return {"id":room_id,"alive":True,"ttl":HOST_TTL}


def launch_snapshot(conn,key,room_id,nonce,revision):
    """Authorize and freeze a request to be checked outside the SQLite write lock."""
    player=_actor(conn,key)
    _nonce(nonce)
    previous=conn.execute("SELECT * FROM lobby_launches WHERE lobby_id=?",
                          (room_id,)).fetchone()
    if previous:
        if player!=previous["owner"]:
            raise accounts.AuthError("not_owner",403)
        if previous["nonce"]!=nonce:
            raise accounts.AuthError("launch_already_started",409)
        return {"previous":_launch_state(conn,previous)}
    room=_room(conn,room_id)
    if player!=room["owner"]:
        raise accounts.AuthError("not_owner",403)
    if revision!=room["revision"]:
        raise accounts.AuthError("stale_revision",409)
    members=conn.execute("SELECT player,ready_revision FROM lobby_members WHERE lobby=? "
                         "ORDER BY player",(room_id,)).fetchall()
    if len(members)<2 or len(members)>room["capacity"] or any(
            m["ready_revision"]!=revision for m in members if m["player"]!=player):
        raise accounts.AuthError("members_not_ready",409)
    return {"previous":None,"server":room["server"],"proto":room["proto"],
            "members":tuple(m["player"] for m in members),"revision":revision}


def commit_launch_snapshot(conn,key,room_id,nonce,revision,snapshot):
    if snapshot.get("previous"):
        return {"launch":snapshot["previous"]}
    player=_actor(conn,key)
    # If the launch already committed while the probe was in-flight,
    # the idempotent internal handler returns the same immutable event.
    previous=conn.execute("SELECT * FROM lobby_launches WHERE lobby_id=?",
                          (room_id,)).fetchone()
    if previous:
        return launch_internal(conn,key,room_id,nonce,revision)
    room=_room(conn,room_id)
    members=tuple(r[0] for r in conn.execute(
        "SELECT player FROM lobby_members WHERE lobby=? ORDER BY player",(room_id,)))
    if (room["server"],room["proto"],room["revision"],members)!=(
            snapshot["server"],snapshot["proto"],snapshot["revision"],tuple(snapshot["members"])):
        raise accounts.AuthError("lobby_changed",409)
    return launch_internal(conn,key,room_id,nonce,revision)

def acknowledge_launch(conn,key,launch_id):
    """The authenticated client has safely queued the one-time join action."""
    player=_actor(conn,key)
    entry=conn.execute("SELECT l.* FROM lobby_launches l "
                       "JOIN launch_members m ON m.launch=l.id "
                       "WHERE l.id=? AND m.player=?",(launch_id,player)).fetchone()
    if not entry:
        raise accounts.AuthError("launch_not_found",404)
    if entry["delivery_expires"]<=now():
        raise accounts.AuthError("launch_expired",410)
    conn.execute("UPDATE launch_members SET delivered_at=CASE "
                 "WHEN delivered_at=0 THEN ? ELSE delivered_at END "
                 "WHERE launch=? AND player=?",(now(),launch_id,player))
    return {"ok":True,"id":launch_id}
