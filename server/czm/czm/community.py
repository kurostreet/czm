"""Account roles, optional public contacts, project servers and private tester tickets."""
import base64
import hashlib
import io
import ipaddress
import json
import re
from urllib.parse import urlsplit

from PIL import Image

from . import accounts, service, social, server_moderation
from .db import now
from .tab import server_address

ROLES = ("moderator", "tester", "server_owner")
SCHEMA = """
CREATE TABLE IF NOT EXISTS community_roles (
 player INTEGER NOT NULL REFERENCES accounts(player) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('moderator','tester','server_owner')),
 project TEXT NOT NULL DEFAULT '', granted INTEGER NOT NULL,
 PRIMARY KEY(player,role)
);
CREATE TABLE IF NOT EXISTS community_profiles (
 player INTEGER PRIMARY KEY REFERENCES accounts(player) ON DELETE CASCADE,
 telegram TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS owner_servers (
 player INTEGER NOT NULL REFERENCES accounts(player) ON DELETE CASCADE,
 server TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', updated INTEGER NOT NULL,
 PRIMARY KEY(player,server)
);
CREATE TABLE IF NOT EXISTS community_role_log (
 id INTEGER PRIMARY KEY, player INTEGER NOT NULL, role TEXT NOT NULL,
 action TEXT NOT NULL, actor TEXT NOT NULL, created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tester_tickets (
 id INTEGER PRIMARY KEY AUTOINCREMENT, player INTEGER NOT NULL REFERENCES accounts(player) ON DELETE CASCADE,
 subject TEXT NOT NULL, text TEXT NOT NULL, photo BLOB, text_file BLOB,
 file_name TEXT NOT NULL DEFAULT '', nonce TEXT NOT NULL, digest TEXT NOT NULL,
 created INTEGER NOT NULL, UNIQUE(player,nonce)
);
CREATE TABLE IF NOT EXISTS tester_ticket_delivery (
 ticket INTEGER NOT NULL REFERENCES tester_tickets(id) ON DELETE CASCADE,
 owner INTEGER NOT NULL, parts INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL, PRIMARY KEY(ticket,owner)
);
CREATE TABLE IF NOT EXISTS tester_ticket_receipts (
 ticket INTEGER NOT NULL, owner INTEGER NOT NULL, message INTEGER NOT NULL,
 created INTEGER NOT NULL, PRIMARY KEY(owner,message)
);
"""


def has(conn, player, role):
    if role == "support":
        return conn.execute("SELECT 1 FROM staff WHERE player=? AND role='support'", (player,)).fetchone() is not None
    return conn.execute("SELECT 1 FROM community_roles WHERE player=? AND role=?", (player, role)).fetchone() is not None


def roles(conn, player):
    return [r for r in ("support", *ROLES) if has(conn, player, r)]


def primary(conn, player):
    values = roles(conn, player)
    return values[0] if values else ""


def role_map(conn, players):
    ids = list(set(players))
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(f"SELECT player,role,'' AS project,0 AS priority FROM staff WHERE player IN ({marks}) "
        f"UNION ALL SELECT player,role,project,CASE role WHEN 'moderator' THEN 1 WHEN 'tester' THEN 2 ELSE 3 END "
        f"FROM community_roles WHERE player IN ({marks}) ORDER BY priority", (*ids, *ids))
    result = {}
    for row in rows:
        result.setdefault(row["player"], (row["role"], row["project"]))
    return result


def capabilities(conn, player):
    from . import moderator_guard
    values = roles(conn, player)
    return {"moderate": "support" in values or ("moderator" in values and not moderator_guard.paused(conn, player)),
            "tester": "tester" in values, "server_owner": "server_owner" in values}


def grant(conn, player, role, project="", actor="owner"):
    if role not in ROLES:
        raise accounts.AuthError("role")
    account = conn.execute("SELECT p.id,p.nick FROM players p JOIN accounts a ON a.player=p.id WHERE p.id=?", (player,)).fetchone()
    if account is None:
        raise accounts.AuthError("account_not_found", 404)
    project = service.clean_text(project, 32) if role == "server_owner" else ""
    conn.execute("INSERT INTO community_roles(player,role,project,granted) VALUES(?,?,?,?) "
                 "ON CONFLICT(player,role) DO UPDATE SET project=excluded.project", (player, role, project, now()))
    conn.execute("INSERT INTO community_role_log(player,role,action,actor,created) VALUES(?,?,'grant',?,?)",
                 (player, role, str(actor), now()))
    return {**dict(account), "role": role, "project": project}


def revoke(conn, player, role, actor="owner"):
    if role not in ROLES:
        raise accounts.AuthError("role")
    changed = conn.execute("DELETE FROM community_roles WHERE player=? AND role=?", (player, role)).rowcount > 0
    if changed:
        conn.execute("INSERT INTO community_role_log(player,role,action,actor,created) VALUES(?,?,'revoke',?,?)",
                     (player, role, str(actor), now()))
    return {"ok": True, "changed": changed}


def telegram_link(value):
    value = value.strip()
    if not value:
        return ""
    if value.startswith("@"):
        value = "https://t.me/" + value[1:]
    if value.startswith("t.me/"):
        value = "https://" + value
    try:
        link = urlsplit(value)
    except ValueError as exc:
        raise accounts.AuthError("telegram") from exc
    name = link.path[1:] if link.path.startswith("/") else ""
    if (link.scheme != "https" or link.netloc.lower() != "t.me" or link.query or link.fragment
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", name)
            or name.lower() in {"share", "proxy", "login", "joinchat", "addstickers", "addemoji", "iv", "s"}):
        raise accounts.AuthError("telegram")
    return "https://t.me/" + name


def contact(conn, key, value):
    player = social.actor(conn, key)
    if roles(conn, player["id"]):
        raise accounts.AuthError("role_contact_disabled", 403)
    from . import moderation
    moderation.require_text(conn, player)
    link = telegram_link(value)
    conn.execute("INSERT INTO community_profiles(player,telegram) VALUES(?,?) "
                 "ON CONFLICT(player) DO UPDATE SET telegram=excluded.telegram", (player["id"], link))
    return {"ok": True, "telegram": link}


def profile(conn, player):
    values = roles(conn, player)
    row = conn.execute("SELECT telegram FROM community_profiles WHERE player=?", (player,)).fetchone()
    result = {"roles": values, "telegram": row[0] if row and not values else ""}
    if "server_owner" in values:
        result["project"] = conn.execute("SELECT project FROM community_roles WHERE player=? AND role='server_owner'", (player,)).fetchone()[0]
        result["servers"] = [dict(r) for r in conn.execute(
            "SELECT o.server,o.name FROM owner_servers o LEFT JOIN server_cases s ON s.server=o.server "
            "WHERE o.player=? AND COALESCE(s.blocked,0)=0 ORDER BY o.updated,o.server", (player,))]
    return result


def owner_actor(conn, key):
    player = social.actor(conn, key)
    if not has(conn, player["id"], "server_owner"):
        raise accounts.AuthError("server_owner_required", 403)
    if service.active_ban(conn, player):
        raise accounts.AuthError("banned", 403)
    return player


def public_endpoint(value):
    value = value.strip()
    if re.fullmatch(r"[0-9.]+", value):
        value += ":27015"
    address = server_address(value)
    host = address.rsplit(":", 1)[0].strip("[]")
    if not ipaddress.ip_address(host).is_global:
        raise accounts.AuthError("server")
    return address


def owner_list(conn, key):
    player = owner_actor(conn, key)
    return {"servers": [dict(r) for r in conn.execute(
        "SELECT o.server,o.name,COALESCE(s.blocked,0) AS restricted FROM owner_servers o "
        "LEFT JOIN server_cases s ON s.server=o.server WHERE o.player=? ORDER BY o.updated,o.server", (player["id"],))]}


def server_owners(conn):
    """Public association to an administrator-assigned owner, never a safety guarantee."""
    entries = conn.execute(
        "SELECT s.server,s.player FROM owner_servers s JOIN community_roles r "
        "ON r.player=s.player AND r.role='server_owner' JOIN accounts a ON a.player=s.player "
        "LEFT JOIN server_cases c ON c.server=s.server WHERE COALESCE(c.blocked,0)=0 "
        "ORDER BY r.granted,s.player,s.server")
    owners = {}
    for row in entries:
        owners.setdefault(row["server"], row["player"])
    return {"owners": [{"server": server, "owner": owner} for server, owner in owners.items()]}


def owner_change(conn, key, address, remove=False, name=""):
    player = owner_actor(conn, key)
    from . import rules
    rules.guard(conn, key)
    address = public_endpoint(address)
    if remove:
        conn.execute("DELETE FROM owner_servers WHERE player=? AND server=?", (player["id"], address))
    else:
        server_moderation.require_allowed(conn, address)
        count = conn.execute("SELECT COUNT(*) FROM owner_servers WHERE player=? AND server!=?", (player["id"], address)).fetchone()[0]
        if count >= 5:
            raise accounts.AuthError("servers_limit", 409)
        conn.execute("INSERT INTO owner_servers(player,server,name,updated) VALUES(?,?,?,?) "
                     "ON CONFLICT(player,server) DO UPDATE SET name=excluded.name,updated=excluded.updated",
                     (player["id"], address, service.clean_text(name, 96) or address, now()))
    return {"ok": True, **owner_list(conn, key)}


def _bytes(value, maximum):
    try:
        if len(value) > (maximum + 2) // 3 * 4:
            raise ValueError("size")
        data = base64.b64decode(value, validate=True)
        if len(data) > maximum:
            raise ValueError("size")
        return data
    except (ValueError, TypeError) as exc:
        raise accounts.AuthError("attachment") from exc


def ticket(conn, key, subject, text, photo, text_file, file_name, nonce):
    player = social.actor(conn, key)
    if not has(conn, player["id"], "tester"):
        raise accounts.AuthError("tester_required", 403)
    if service.active_ban(conn, player):
        raise accounts.AuthError("banned", 403)
    subject, text = service.clean_text(subject, 100), service.clean_text(text, 2000)
    if not subject or not text or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", nonce):
        raise accounts.AuthError("ticket")
    image, document = None, None
    if photo:
        raw = _bytes(photo, 4 * 1024 * 1024)
        try:
            with Image.open(io.BytesIO(raw)) as original:
                if original.width * original.height > 20_000_000:
                    raise ValueError("pixels")
                original.load()
                im = original.convert("RGB"); im.thumbnail((1280, 1280))
                encoded = io.BytesIO(); im.save(encoded, format="JPEG", quality=82)
                image = encoded.getvalue()
                if len(image) > 1024 * 1024:
                    raise ValueError("size")
        except (ValueError, OSError, Image.DecompressionBombError) as exc:
            raise accounts.AuthError("photo") from exc
    if text_file:
        document = _bytes(text_file, 64 * 1024)
        try:
            decoded = document.decode("utf-8-sig")
            if "\x00" in decoded:
                raise ValueError("binary")
        except (UnicodeError, ValueError) as exc:
            raise accounts.AuthError("text_file") from exc
        file_name = re.sub(r"[^A-Za-z0-9_. -]", "_", file_name.rsplit("/", 1)[-1])[:60]
        if not file_name.lower().endswith(".txt"):
            file_name = "report.txt"
    else:
        file_name = ""
    digest = hashlib.sha256(json.dumps([subject, text, hashlib.sha256(image or b"").hexdigest(),
        hashlib.sha256(document or b"").hexdigest(), file_name], ensure_ascii=False).encode()).hexdigest()
    previous = conn.execute("SELECT id,digest FROM tester_tickets WHERE player=? AND nonce=?", (player["id"], nonce)).fetchone()
    if previous:
        if previous["digest"] != digest:
            raise accounts.AuthError("nonce", 409)
        return {"ok": True, "id": previous["id"], "duplicate": True}
    accounts.rate(conn, "tester-ticket-hour", str(player["id"]), 5, 3600)
    accounts.rate(conn, "tester-ticket-day", str(player["id"]), 30, 86400)
    row = conn.execute("INSERT INTO tester_tickets(player,subject,text,photo,text_file,file_name,nonce,digest,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?)", (player["id"], subject, text, image, document, file_name, nonce, digest, now()))
    return {"ok": True, "id": row.lastrowid, "duplicate": False}


def tickets_pending(conn, owner):
    return [dict(r) for r in conn.execute(
        "SELECT t.*,p.nick,COALESCE(d.parts,0) AS parts FROM tester_tickets t JOIN players p ON p.id=t.player "
        "LEFT JOIN tester_ticket_delivery d ON d.ticket=t.id AND d.owner=? "
        "WHERE (COALESCE(d.parts,0) & (1 + CASE WHEN t.photo IS NOT NULL THEN 2 ELSE 0 END + "
        "CASE WHEN t.text_file IS NOT NULL THEN 4 ELSE 0 END)) != "
        "(1 + CASE WHEN t.photo IS NOT NULL THEN 2 ELSE 0 END + CASE WHEN t.text_file IS NOT NULL THEN 4 ELSE 0 END) "
        "ORDER BY t.id LIMIT 5", (owner,))]


def ticket_receipt(conn, ticket_id, owner, message_id):
    if isinstance(message_id, int) and message_id > 0:
        conn.execute("INSERT OR IGNORE INTO tester_ticket_receipts(ticket,owner,message,created) VALUES(?,?,?,?)",
                     (ticket_id, owner, message_id, now()))


def ticket_delivered(conn, ticket_id, owner, part=7, message_id=None):
    ticket_receipt(conn, ticket_id, owner, message_id)
    if not conn.execute("SELECT 1 FROM tester_tickets WHERE id=?", (ticket_id,)).fetchone():
        return
    conn.execute("INSERT INTO tester_ticket_delivery(ticket,owner,parts,updated) VALUES(?,?,?,?) "
                 "ON CONFLICT(ticket,owner) DO UPDATE SET parts=parts|excluded.parts,updated=excluded.updated",
                 (ticket_id, owner, part, now()))


def ticket_cleanup_pending(conn, owner):
    return [dict(r) for r in conn.execute("SELECT r.* FROM tester_ticket_receipts r LEFT JOIN tester_tickets t ON t.id=r.ticket "
                                         "WHERE r.owner=? AND t.id IS NULL ORDER BY r.created LIMIT 30", (owner,))]


def ticket_cleanup_done(conn, owner, message_id):
    conn.execute("DELETE FROM tester_ticket_receipts WHERE owner=? AND message=?", (owner, message_id))


def cleanup(conn):
    conn.execute("DELETE FROM tester_tickets WHERE created<?", (now() - 90 * 86400,))
