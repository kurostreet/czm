"""Account friendships and private messages. No game scores are inferred here."""
import re

from . import accounts, service, notifications
from .config import get_settings
from .db import now
from .tab import server_address

PRESENCE_TTL = 90
PAGE_SIZE = 40


def actor(conn, key, require_account=True):
    player = service.player_by_key(conn, key)
    if player is None:
        raise accounts.AuthError("session", 401)
    if require_account and not conn.execute("SELECT 1 FROM accounts WHERE player=?", (player["id"],)).fetchone():
        raise accounts.AuthError("account_required", 403)
    return player


def account(conn, target):
    row = conn.execute("SELECT p.* FROM players p JOIN accounts a ON a.player=p.id WHERE p.id=?", (target,)).fetchone()
    if row is None:
        raise accounts.AuthError("account_not_found", 404)
    return row


def blocked(conn, a, b):
    return bool(conn.execute("SELECT 1 FROM social_blocks WHERE (source=? AND target=?) OR (source=? AND target=?)",
                             (a, b, b, a)).fetchone())


def relation(conn, a, b):
    if a == b:
        return "self"
    if conn.execute("SELECT 1 FROM social_blocks WHERE source=? AND target=?", (a, b)).fetchone():
        return "blocked"
    if blocked(conn, a, b):
        return "unavailable"
    outgoing = bool(conn.execute("SELECT 1 FROM social_follows WHERE source=? AND target=?", (a, b)).fetchone())
    incoming = bool(conn.execute("SELECT 1 FROM social_follows WHERE source=? AND target=?", (b, a)).fetchone())
    return "friend" if outgoing and incoming else "following" if outgoing else "follower" if incoming else "none"


def counts(conn, player):
    mutual = "EXISTS(SELECT 1 FROM social_follows r WHERE r.source=f.target AND r.target=f.source)"
    friends = conn.execute(f"SELECT COUNT(*) FROM social_follows f WHERE f.source=? AND {mutual}", (player,)).fetchone()[0]
    followers = conn.execute(f"SELECT COUNT(*) FROM social_follows f WHERE f.target=? AND NOT {mutual}", (player,)).fetchone()[0]
    following = conn.execute(f"SELECT COUNT(*) FROM social_follows f WHERE f.source=? AND NOT {mutual}", (player,)).fetchone()[0]
    requests = conn.execute(f"SELECT COUNT(*) FROM social_follows f WHERE f.target=? AND f.seen=0 AND NOT {mutual}", (player,)).fetchone()[0]
    unread = conn.execute(
        "SELECT COUNT(*) FROM private_messages m JOIN private_dialogs d ON d.id=m.dialog WHERE "
        "(d.low=? OR d.high=?) AND m.sender!=? AND m.deleted=0 AND m.id>CASE WHEN d.low=? THEN d.read_low ELSE d.read_high END",
        (player, player, player, player)).fetchone()[0]
    result = {"friends": friends, "followers": followers, "following": following, "requests": requests, "unread": unread}
    result.update(notifications.counts(conn, player, get_settings().room_list))
    return result


def profile(conn, viewer, target, compact=False):
    row = conn.execute("SELECT p.*, a.created AS registered FROM players p LEFT JOIN accounts a ON a.player=p.id WHERE p.id=?", (target,)).fetchone()
    if row is None:
        raise accounts.AuthError("not_found", 404)
    extra = conn.execute("SELECT * FROM social_profiles WHERE player=?", (target,)).fetchone()
    rel = relation(conn, viewer["id"], target)
    # Revoked/expired account sessions never keep a device online.
    presence = conn.execute(
        "SELECT pr.* FROM social_presence pr WHERE pr.player=? AND pr.seen>? AND "
        "((NOT EXISTS(SELECT 1 FROM accounts a WHERE a.player=pr.player) AND pr.owner=?) OR "
        "EXISTS(SELECT 1 FROM account_sessions s WHERE s.player=pr.player AND s.token_hash=pr.owner AND s.expires>? AND s.seen>?)) "
        "ORDER BY (pr.server!='') DESC, pr.seen DESC LIMIT 1",
        (target, now()-PRESENCE_TTL, row["key_hash"], now(), now()-accounts.SESSION_IDLE)).fetchone()
    hidden = rel in ("blocked", "unavailable")
    online = bool(presence) and not hidden
    result = {"id": target, "nick": row["nick"], "avatar": service.avatar_ref(row),
              "account": row["registered"] is not None, "created": row["registered"] or row["created"],
              "status": extra["status"] if extra else "", "relation": rel,
              "online": online, "last_seen": 0 if hidden else extra["last_seen"] if extra else 0,
              "playing": online and bool(presence["server"]), "server": "", "map": ""}
    from . import moderation
    staff = moderation.role(conn, target)
    if staff:
        result["role"] = staff
    if not hidden:
        from . import community
        result.update(community.profile(conn, target))
    from . import playtime
    if not compact:
        standing = playtime.standing(conn, target)
        if standing and not hidden:
            result["top"] = standing          # the exact place and the time on servers
    else:
        place = playtime.places(conn).get(target)
        if place and not hidden:
            result["top"] = {"place": place, "tier": playtime.tier(place)}
    if online and rel in ("self", "friend"):
        result.update(server=presence["server"], map=presence["map"])
        from . import lobbies
        if presence["server"]:
            group=lobbies.playing_together(conn,viewer["id"],target,
                                          presence["server"],PRESENCE_TTL)
            if group:
                result["together"]=group
        else:
            # A room only exists while its owner is actively in the lobby.
            # Private room IDs cannot be obtained from friend profile cards.
            room=lobbies._current(conn,target)
            if room:
                people=conn.execute("SELECT COUNT(*) FROM lobby_members WHERE lobby=?",
                                    (room["id"],)).fetchone()[0]
                result["lobby"]={"count":people,"capacity":room["capacity"],
                                 "id":room["id"] if room["visibility"]=="public" else "",
                                 "public":room["visibility"]=="public"}
    if not compact:
        public = counts(conn, target)
        result["counts"] = {k: public[k] for k in ("friends", "followers", "following")}
    return result


def heartbeat(conn, key, server="", map_name=""):
    player = actor(conn, key, False)
    server = server_address(server) if server else ""
    if map_name and not re.fullmatch(r"[A-Za-z0-9_+.-]{1,64}", map_name):
        raise accounts.AuthError("map")
    t = now()
    conn.execute("DELETE FROM social_presence WHERE seen<=?", (t-PRESENCE_TTL,))
    conn.execute("INSERT INTO social_presence VALUES(?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET player=excluded.player,seen=excluded.seen,server=excluded.server,map=excluded.map",
                 (service.hash_secret(key), player["id"], t, server, map_name if server else ""))
    conn.execute("INSERT INTO social_profiles(player,last_seen) VALUES(?,?) ON CONFLICT(player) DO UPDATE SET last_seen=excluded.last_seen", (player["id"], t))
    from . import playtime
    playtime.accrue(conn, player["id"], service.hash_secret(key), bool(server), t)  # only time connected to a game server
    registered = bool(conn.execute("SELECT 1 FROM accounts WHERE player=?", (player["id"],)).fetchone())
    if registered:
        notifications.baseline(conn, player["id"], get_settings().room_list)
        from . import lobbies
        lobbies.record_launch_presence(conn,player["id"],server)
    return {"id": player["id"], "account": registered, "ttl": PRESENCE_TTL,
            "counts": counts(conn, player["id"]) if registered else {"friends": 0, "followers": 0, "following": 0, "requests": 0, "unread": 0}}


def summary(conn, key):
    player = actor(conn, key)
    return {"profile": profile(conn, player, player["id"]), "counts": counts(conn, player["id"])}


def update_status(conn, key, text):
    player = actor(conn, key)
    if service.active_ban(conn, player):
        raise accounts.AuthError("banned", 403)
    from . import moderation
    moderation.require_text(conn, player)
    text = service.profanity.clean(service.clean_text(text, 100))
    conn.execute("INSERT INTO social_profiles(player,status) VALUES(?,?) ON CONFLICT(player) DO UPDATE SET status=excluded.status", (player["id"], text))
    return {"profile": profile(conn, player, player["id"])}


def action(conn, key, target, action):
    player = actor(conn, key)
    a = player["id"]
    if action == "seen":
        conn.execute("UPDATE social_follows SET seen=1 WHERE target=?", (a,))
        conn.execute("UPDATE social_notices SET seen=1 WHERE player=? AND kind='followers' AND seen=0", (a,))
        return {"counts": counts(conn, a)}
    account(conn, target)
    if a == target:
        raise accounts.AuthError("self")
    if action == "follow":
        if service.active_ban(conn, player):
            raise accounts.AuthError("banned", 403)
        if blocked(conn, a, target):
            raise accounts.AuthError("unavailable", 403)
        if relation(conn, a, target) not in ("friend", "following"):
            if conn.execute("SELECT COUNT(*) FROM social_follows WHERE source=?", (a,)).fetchone()[0] >= 1000:
                raise accounts.AuthError("limit", 409)
            accounts.rate(conn, "social_follow", str(a), 30, 3600)
            previous = relation(conn, a, target)
            conn.execute("INSERT INTO social_follows(source,target,created) VALUES(?,?,?)", (a, target, now()))
            notifications.clear_pair(conn, a, target)
            if previous == "follower":
                conn.execute("UPDATE social_follows SET seen=1 WHERE (source=? AND target=?) OR (source=? AND target=?)", (a,target,target,a))
                notifications.add(conn, target, a, "friends")
            else:
                notifications.add(conn, target, a, "followers")
    elif action == "unfollow":
        previous = relation(conn, a, target)
        # Deleting A->B leaves B->A intact: the former friend becomes A's follower.
        conn.execute("DELETE FROM social_follows WHERE source=? AND target=?", (a, target))
        notifications.clear_pair(conn, a, target)
        if previous == "friend": notifications.add(conn, target, a, "following")
    elif action == "block":
        conn.execute("INSERT OR IGNORE INTO social_blocks VALUES(?,?)", (a, target))
        conn.execute("DELETE FROM social_follows WHERE (source=? AND target=?) OR (source=? AND target=?)", (a, target, target, a))
        notifications.clear_pair(conn, a, target)
    elif action == "unblock":
        conn.execute("DELETE FROM social_blocks WHERE source=? AND target=?", (a, target))
    else:
        raise accounts.AuthError("action")
    return {"profile": profile(conn, player, target), "counts": counts(conn, a)}


def people(conn, key, kind, offset=0):
    player = actor(conn, key)
    a = player["id"]
    if kind == "blocked":
        query = "SELECT b.target AS target FROM social_blocks b WHERE b.source=? ORDER BY b.target"
    else:
        mutual = "EXISTS(SELECT 1 FROM social_follows r WHERE r.source=f.target AND r.target=f.source)"
        if kind == "friends":
            query = f"SELECT f.target AS target FROM social_follows f WHERE f.source=? AND {mutual} ORDER BY f.created DESC,f.target"
        elif kind == "following":
            query = f"SELECT f.target AS target FROM social_follows f WHERE f.source=? AND NOT {mutual} ORDER BY f.created DESC,f.target"
        elif kind == "followers":
            query = f"SELECT f.source AS target FROM social_follows f WHERE f.target=? AND NOT {mutual} ORDER BY f.created DESC,f.source"
        else:
            raise accounts.AuthError("kind")
    rows = conn.execute(query + " LIMIT ? OFFSET ?", (a, PAGE_SIZE+1, offset)).fetchall()
    people = []
    for r in rows[:PAGE_SIZE]:
        item = profile(conn, player, r["target"], True)
        item["notice"] = notifications.event_id(conn, a, r["target"], kind)
        people.append(item)
    return {"people": people,
            "next": offset+PAGE_SIZE if len(rows)>PAGE_SIZE else -1, "counts": counts(conn, a)}


def _dialog(conn, a, b):
    return conn.execute("SELECT * FROM private_dialogs WHERE low=? AND high=?", (min(a, b), max(a, b))).fetchone()


def _text(row):
    """The text a reader gets: masked like the chat, except the server address of a game invite."""
    if row["deleted"]:
        return ""
    text = row["text"]
    if text.startswith(INVITE):
        parts = text[len(INVITE):].split(" ", 2)
        if len(parts) >= 2 and parts[0] in ("gs", "49") and _valid_server(parts[1]):
            name = service.profanity.clean(parts[2]) if len(parts) > 2 else ""
            return f"{INVITE}{parts[0]} {parts[1]} {name}".rstrip()
    return service.profanity.clean(text)


def _message(row):
    return {"id": row["id"], "p": row["sender"], "t": _text(row), "ts": row["created"], "deleted": bool(row["deleted"])}


INVITE = "czm:invite "
_SERVER = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3}):(\d{1,5})$")


def send(conn, key, target, text, nonce, invite=False):
    player = actor(conn, key)
    a = player["id"]
    account(conn, target)
    if relation(conn, a, target) != "friend":
        raise accounts.AuthError("not_friends", 403)
    if service.active_ban(conn, player):
        raise accounts.AuthError("banned", 403)
    if not invite:
        from . import moderation
        moderation.require_text(conn, player)
    # typed text never passes for an invite: addresses are masked like links in the chat
    if not invite:
        text = service.profanity.clean(service.clean_text(text, 400))
    if not text:
        raise accounts.AuthError("empty")
    old = conn.execute("SELECT m.*,d.low,d.high FROM private_messages m JOIN private_dialogs d ON d.id=m.dialog WHERE m.sender=? AND m.nonce=?", (a, nonce)).fetchone()
    if old:
        if old["text"] != text or target not in (old["low"], old["high"]):
            raise accounts.AuthError("nonce", 409)
        return {"message": _message(old)}
    accounts.rate(conn, "private_send", str(a), 30, 60)
    d = _dialog(conn, a, target)
    if d is None:
        conn.execute("INSERT INTO private_dialogs(low,high) VALUES(?,?)", (min(a,target), max(a,target)))
        d = _dialog(conn, a, target)
    cur = conn.execute("INSERT INTO private_messages(dialog,sender,text,created,nonce) VALUES(?,?,?,?,?)", (d["id"], a, text, now(), nonce))
    conn.execute("UPDATE private_dialogs SET last_message=? WHERE id=?", (cur.lastrowid, d["id"]))
    return {"message": _message(conn.execute("SELECT * FROM private_messages WHERE id=?", (cur.lastrowid,)).fetchone())}


def history(conn, key, target, before=0):
    player = actor(conn, key)
    account(conn, target)
    a = player["id"]
    d = _dialog(conn, a, target)
    rows = conn.execute("SELECT * FROM private_messages WHERE dialog=? AND (?=0 OR id<?) ORDER BY id DESC LIMIT 51",
                        (d["id"], before, before)).fetchall() if d else []
    return {"profile": profile(conn, player, target), "messages": [_message(r) for r in reversed(rows[:50])],
            "before": rows[49]["id"] if len(rows)>50 else 0,
            "can_send": relation(conn, a, target)=="friend" and not service.active_ban(conn, player)}


def mark_read(conn, key, target, through):
    player = actor(conn, key)
    a = player["id"]
    d = _dialog(conn, a, target)
    if d:
        column = "read_low" if d["low"] == a else "read_high"
        # A claimed ID can only acknowledge messages already in this conversation.
        through = min(max(0, through), d["last_message"])
        conn.execute(f"UPDATE private_dialogs SET {column}=MAX({column},?) WHERE id=?", (through, d["id"]))
    return {"counts": counts(conn, a)}


def dialogs(conn, key, offset=0):
    player = actor(conn, key)
    a = player["id"]
    rows = conn.execute("SELECT * FROM private_dialogs WHERE (low=? OR high=?) AND last_message>0 ORDER BY last_message DESC LIMIT ? OFFSET ?",
                        (a, a, PAGE_SIZE+1, offset)).fetchall()
    result = []
    for d in rows[:PAGE_SIZE]:
        peer = d["high"] if d["low"] == a else d["low"]
        unread = conn.execute("SELECT COUNT(*) FROM private_messages WHERE dialog=? AND sender!=? AND id>? AND deleted=0",
                              (d["id"], a, d["read_low"] if d["low"]==a else d["read_high"])).fetchone()[0]
        item = profile(conn, player, peer, True)
        item["unread"] = unread
        item["last"] = _message(conn.execute("SELECT * FROM private_messages WHERE id=?", (d["last_message"],)).fetchone())
        result.append(item)
    return {"people": result, "next": offset+PAGE_SIZE if len(rows)>PAGE_SIZE else -1, "counts": counts(conn, a)}


def online_count(conn) -> int:
    """Players with the game open right now: every client reports presence about every 30 s."""
    return conn.execute("SELECT COUNT(DISTINCT player) FROM social_presence WHERE seen>?", (now()-PRESENCE_TTL,)).fetchone()[0]


def _valid_server(server):
    m = _SERVER.match(server or "")
    return bool(m) and all(int(x) <= 255 for x in m.groups()[:4]) and 0 < int(m.group(5)) < 65536


def invite(conn, key, target, server, proto, name, nonce):
    """A game invite in the private dialog: the friend's game shows it as a card with a join button."""
    if not _valid_server(server) or proto not in ("gs", "49"):
        raise accounts.AuthError("server")
    from . import server_moderation
    server_moderation.require_allowed(conn, server)
    name = service.profanity.clean(service.clean_text(name, 60)) or server
    return send(conn, key, target, f"{INVITE}{proto} {server} {name}", nonce, invite=True)
