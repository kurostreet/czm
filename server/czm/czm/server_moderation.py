"""Endpoint-specific reports and reversible restrictions. Reports never auto-ban.

Only the owner's authenticated bot changes restrictions. The public policy never
contains reporter identities, complaint counts or private moderation evidence.
"""
import re

from . import accounts, social, service
from .db import now
from .tab import server_address

SCHEMA = """
CREATE TABLE IF NOT EXISTS server_cases (
 id INTEGER PRIMARY KEY, server TEXT NOT NULL UNIQUE, name TEXT NOT NULL DEFAULT '',
 epoch INTEGER NOT NULL DEFAULT 1, blocked INTEGER NOT NULL DEFAULT 0,
 reason TEXT NOT NULL DEFAULT '', updated INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS server_reports (
 id INTEGER PRIMARY KEY, server_id INTEGER NOT NULL REFERENCES server_cases(id),
 epoch INTEGER NOT NULL, reporter INTEGER NOT NULL, nonce TEXT NOT NULL, email_hash TEXT NOT NULL DEFAULT '',
 reason TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL,
 UNIQUE(reporter,nonce)
);
CREATE INDEX IF NOT EXISTS server_reports_server ON server_reports(server_id,epoch,id);
CREATE INDEX IF NOT EXISTS server_reports_author ON server_reports(reporter,id);
CREATE INDEX IF NOT EXISTS server_reports_email ON server_reports(email_hash,created);
CREATE TABLE IF NOT EXISTS server_moderation_log (
 id INTEGER PRIMARY KEY, server_id INTEGER NOT NULL REFERENCES server_cases(id),
 actor TEXT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS server_report_delivery (
 server_id INTEGER NOT NULL REFERENCES server_cases(id), owner INTEGER NOT NULL,
 last_report INTEGER NOT NULL, PRIMARY KEY(server_id,owner)
);
CREATE TABLE IF NOT EXISTS server_hidden (
 player INTEGER NOT NULL REFERENCES accounts(player) ON DELETE CASCADE,
 server TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1,
 updated INTEGER NOT NULL, PRIMARY KEY(player,server)
);
"""
REASONS = {"sexual", "hate", "harassment", "copyright", "spam", "other"}
PAGE = 25
REPORT_COOLDOWN = 30 * 86400


def clean(value, limit):
    return service.clean_text(value, limit)


def _case(conn, address, name=""):
    address = server_address(address.strip())
    conn.execute("INSERT OR IGNORE INTO server_cases(server,name,updated) VALUES(?,?,?)",
                 (address, clean(name, 96), now()))
    return conn.execute("SELECT * FROM server_cases WHERE server=?", (address,)).fetchone()


def info(conn, address):
    address = server_address(address.strip())
    row = conn.execute("SELECT * FROM server_cases WHERE server=?", (address,)).fetchone()
    if row is None:
        return {"server": address, "name": "", "count": 0, "reporters": 0, "blocked": False, "reason": ""}
    count = conn.execute("SELECT COUNT(*),COUNT(DISTINCT reporter) FROM server_reports WHERE server_id=? AND epoch=?",
                         (row["id"], row["epoch"])).fetchone()
    return {"id": row["id"], "server": address, "name": row["name"], "count": count[0], "reporters": count[1],
            "blocked": bool(row["blocked"]), "reason": row["reason"]}


def report(conn, key, address, name, reason, comment, nonce):
    player = social.actor(conn, key)
    comment = clean(comment, 500)
    reasons = [reason] if isinstance(reason, str) else reason
    if not isinstance(reasons, list) or len(reasons)>6 or any(not isinstance(r,str) or r not in REASONS for r in reasons):
        raise accounts.AuthError("reason")
    if not reasons and comment:
        reasons = ["other"]
    if not reasons or ("other" in reasons and not comment):
        raise accounts.AuthError("reason")
    reason = ",".join(sorted(set(reasons)))
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", nonce):
        raise accounts.AuthError("nonce")
    address = server_address(address.strip())
    previous = conn.execute("SELECT r.reason,r.comment,s.server FROM server_reports r "
                            "JOIN server_cases s ON s.id=r.server_id WHERE reporter=? AND nonce=?",
                            (player["id"], nonce)).fetchone()
    if previous:
        if (previous["server"], previous["reason"], previous["comment"]) != (address, reason, comment):
            raise accounts.AuthError("nonce", 409)
        return {"ok": True, "duplicate": True, "hidden": _hidden(conn, player["id"])}
    if service.active_ban(conn, player):
        raise accounts.AuthError("banned", 403)
    account = conn.execute("SELECT email FROM accounts WHERE player=?", (player["id"],)).fetchone()
    # accounts.email is set only after the existing email-code confirmation.
    if not account or not account["email"]:
        raise accounts.AuthError("email_required", 403)
    email_hash = service.hash_secret("server-report-email:" + account["email"].strip().lower())
    # The cooldown spans review rounds: lifting a restriction does not let an
    # account file another complaint about the same endpoint before 30 days.
    if conn.execute("SELECT 1 FROM server_reports r JOIN server_cases s ON s.id=r.server_id "
                    "WHERE (r.reporter=? OR r.email_hash=?) AND s.server=? AND r.created>? LIMIT 1",
                    (player["id"], email_hash, address, now() - REPORT_COOLDOWN)).fetchone():
        raise accounts.AuthError("server_report_cooldown", 429)
    # Technical flood limits also cover rapid complaints about different servers.
    accounts.rate(conn, "server-report-player", str(player["id"]), 20, 60)
    accounts.rate(conn, "server-report-email", email_hash, 20, 60)
    if player["device_hash"]:
        accounts.rate(conn, "server-report-device", player["device_hash"], 20, 60)
    row = _case(conn, address, name)
    conn.execute("INSERT INTO server_reports(server_id,epoch,reporter,nonce,email_hash,reason,comment,created) "
                 "VALUES(?,?,?,?,?,?,?,?)", (row["id"], row["epoch"], player["id"], nonce, email_hash, reason, comment, now()))
    conn.execute("INSERT INTO server_hidden(player,server,name,enabled,updated) VALUES(?,?,?,1,?) "
                 "ON CONFLICT(player,server) DO UPDATE SET enabled=1,name=excluded.name,updated=excluded.updated",
                 (player["id"], address, clean(name, 96) or row["name"], now()))
    return {"ok": True, "duplicate": False, "hidden": _hidden(conn, player["id"])}


def _hidden(conn, player):
    return [dict(r) for r in conn.execute(
        "SELECT h.server,h.name,h.enabled,COALESCE(s.blocked,0) AS restricted FROM server_hidden h "
        "LEFT JOIN server_cases s ON s.server=h.server WHERE h.player=? ORDER BY h.updated DESC,h.server",
        (player,))]


def hidden(conn, key):
    player = social.actor(conn, key)
    return {"hidden": _hidden(conn, player["id"])}


def hidden_action(conn, key, address, enabled, remove=False):
    player = social.actor(conn, key)
    address = server_address(address)
    if remove:
        conn.execute("DELETE FROM server_hidden WHERE player=? AND server=?", (player["id"], address))
    else:
        conn.execute("UPDATE server_hidden SET enabled=?,updated=? WHERE player=? AND server=?",
                     (int(enabled), now(), player["id"], address))
    return {"ok": True, "hidden": _hidden(conn, player["id"])}


def listing(conn, page=0):
    rows = conn.execute(
        "SELECT s.server,s.name,s.blocked,COUNT(r.id) AS count,COUNT(DISTINCT r.reporter) AS reporters FROM server_cases s "
        "LEFT JOIN server_reports r ON r.server_id=s.id AND r.epoch=s.epoch "
        "GROUP BY s.id HAVING COUNT(r.id)>0 OR s.blocked=1 ORDER BY count DESC,s.server LIMIT ? OFFSET ?",
        (PAGE + 1, max(0, page) * PAGE)).fetchall()
    return {"servers": [dict(row) for row in rows[:PAGE]], "more": len(rows) > PAGE}


def set_blocked(conn, address, blocked, actor, reason=""):
    reason = clean(reason, 200)
    if blocked and not reason:
        raise accounts.AuthError("reason")
    row = _case(conn, address)
    if bool(row["blocked"]) == blocked:
        return {**info(conn, row["server"]), "changed": False}
    # Lifting preserves complaint counters, the audit trail and the 30-day cooldown.
    conn.execute("UPDATE server_cases SET blocked=?,reason=?,updated=? WHERE id=?",
                 (int(blocked), reason if blocked else "", now(), row["id"]))
    conn.execute("INSERT INTO server_moderation_log(server_id,actor,action,reason,created) VALUES(?,?,?,?,?)",
                 (row["id"], str(actor), "ban" if blocked else "unban", reason, now()))
    return {**info(conn, row["server"]), "changed": True}


def require_allowed(conn, address):
    address = server_address(address)
    if conn.execute("SELECT 1 FROM server_cases WHERE server=? AND blocked=1", (address,)).fetchone():
        raise accounts.AuthError("server_blocked", 403)


def policy(conn):
    return {"blocked": [r[0] for r in conn.execute(
        "SELECT server FROM server_cases WHERE blocked=1 ORDER BY server")]}


def pending(conn, owner):
    rows = conn.execute(
        "SELECT s.id AS server_id,s.server,s.name,s.blocked,r.id,r.epoch,r.reporter,r.email_hash,r.reason,r.comment,p.nick FROM server_cases s "
        "JOIN server_reports r ON r.server_id=s.id AND r.epoch=s.epoch "
        "LEFT JOIN players p ON p.id=r.reporter "
        "LEFT JOIN server_report_delivery d ON d.server_id=s.id AND d.owner=? "
        "WHERE r.id>COALESCE(d.last_report,0) ORDER BY r.id LIMIT 30", (owner,)).fetchall()
    result = []
    for r in rows:
        counts = conn.execute("SELECT COUNT(*),COUNT(DISTINCT reporter) FROM server_reports "
                              "WHERE server_id=? AND epoch=? AND id<=?",
                              (r["server_id"], r["epoch"], r["id"])).fetchone()
        author = conn.execute("SELECT COUNT(*),COUNT(DISTINCT server_id) FROM server_reports "
                              "WHERE (reporter=? OR (email_hash!='' AND email_hash=?)) AND id<=?",
                              (r["reporter"], r["email_hash"], r["id"])).fetchone()
        result.append({"id": r["server_id"], "server": r["server"], "name": r["name"], "blocked": bool(r["blocked"]),
                       "count": counts[0], "reporters": counts[1], "last_report": r["id"],
                       "reporter": r["reporter"], "reporter_nick": r["nick"] or "Удалённый аккаунт",
                       "author_count": author[0], "author_servers": author[1], "reason": r["reason"], "comment": r["comment"]})
    return result


def delivered(conn, server_id, owner, last_report):
    conn.execute("INSERT INTO server_report_delivery(server_id,owner,last_report) VALUES(?,?,?) "
                 "ON CONFLICT(server_id,owner) DO UPDATE SET last_report=MAX(last_report,excluded.last_report)",
                 (server_id, owner, last_report))


def cleanup(conn):
    # Retain moderation history but not a permanent fingerprint of a deleted email.
    conn.execute("UPDATE server_reports SET email_hash='' WHERE email_hash!='' AND created<=?",
                 (now() - REPORT_COOLDOWN,))
