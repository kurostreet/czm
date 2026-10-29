"""Review batches and reversible effects. Ten unreviewed actions pause a moderator."""
import hashlib
import json

from . import accounts
from .db import now

LIMIT = 10
SCHEMA = """
CREATE TABLE IF NOT EXISTS moderator_batches (
 id INTEGER PRIMARY KEY, moderator INTEGER NOT NULL, opened INTEGER NOT NULL,
 closed INTEGER, state TEXT NOT NULL DEFAULT 'pending', reviewed_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS moderator_state (
 player INTEGER PRIMARY KEY, paused INTEGER NOT NULL DEFAULT 0, batch INTEGER,
 updated INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS moderation_effects (
 log INTEGER NOT NULL REFERENCES moderation_log(id), resource TEXT NOT NULL,
 before_json TEXT NOT NULL, after_json TEXT NOT NULL, PRIMARY KEY(log,resource)
);
CREATE TABLE IF NOT EXISTS moderation_resource_heads (
 resource TEXT PRIMARY KEY, log INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS moderation_events (
 log INTEGER PRIMARY KEY REFERENCES moderation_log(id), batch INTEGER,
 paused INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS moderation_event_delivery (
 log INTEGER NOT NULL REFERENCES moderation_events(log), owner INTEGER NOT NULL,
 sent INTEGER NOT NULL, PRIMARY KEY(log,owner)
);
CREATE TABLE IF NOT EXISTS moderator_owner_log (
 id INTEGER PRIMARY KEY, moderator INTEGER NOT NULL, actor TEXT NOT NULL,
 action TEXT NOT NULL, batch INTEGER, created INTEGER NOT NULL, detail TEXT NOT NULL DEFAULT ''
);
"""
# Only these mutable columns may be restored; identities protect against row-ID reuse.
FIELDS = {"bans": ("lifted",), "warnings": ("seen",), "reports": ("status", "resolved"),
          "messages": ("deleted",), "private_messages": ("deleted",), "lobby_messages": ("deleted",)}


def paused(conn, player):
    row = conn.execute("SELECT paused FROM moderator_state WHERE player=?", (player,)).fetchone()
    return bool(row and row[0])


def require_active(conn, player):
    if paused(conn, player):
        raise accounts.AuthError("moderator_paused", 403)


def _row(conn, table, row_id):
    row = conn.execute("SELECT * FROM " + table + " WHERE id=?", (row_id,)).fetchone()
    if row is None:
        return None
    mutable = FIELDS[table]
    identity = {k: row[k] for k in row.keys() if k not in mutable}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return {**{k: row[k] for k in mutable}, "identity": fingerprint}


def capture(conn, target, report=None, message=None, lobby_message=None):
    ids = {table: set() for table in FIELDS}
    for table in ("bans", "warnings"):
        ids[table].update(r[0] for r in conn.execute("SELECT id FROM " + table + " WHERE player=?", (target,)))
    ids["reports"].update(r[0] for r in conn.execute("SELECT id FROM reports WHERE target=?", (target,)))
    if message:
        ids["messages"].add(message)
    if lobby_message:
        ids["lobby_messages"].add(lobby_message)
    if report:
        row = conn.execute("SELECT * FROM reports WHERE id=? AND target=?", (report, target)).fetchone()
        if row:
            for table, field in (("messages", "message"), ("private_messages", "private_message"), ("lobby_messages", "lobby_message")):
                # Older schemas use *_id names in the complaint record.
                field = field if field in row.keys() else field + "_id"
                if field in row.keys() and row[field]:
                    ids[table].add(row[field])
    return {f"{table}:{row_id}": _row(conn, table, row_id) for table, values in ids.items() for row_id in values}


def record(conn, log_id, moderator, guarded, before, after):
    batch = None
    if guarded:
        require_active(conn, moderator)
        state = conn.execute("SELECT batch FROM moderator_state WHERE player=?", (moderator,)).fetchone()
        batch = state[0] if state else None
        if batch is None:
            batch = conn.execute("INSERT INTO moderator_batches(moderator,opened) VALUES(?,?)", (moderator, now())).lastrowid
            conn.execute("INSERT INTO moderator_state(player,batch,updated) VALUES(?,?,?) "
                         "ON CONFLICT(player) DO UPDATE SET batch=excluded.batch,updated=excluded.updated", (moderator, batch, now()))
    # Keep all selected resource heads, including an intentional repeated removal.
    for resource in before.keys() | after.keys():
        old, new = before.get(resource), after.get(resource)
        if old is None and new is None:
            continue
        if old == new and resource.split(":", 1)[0] not in ("messages", "private_messages", "lobby_messages"):
            continue
        conn.execute("INSERT INTO moderation_effects(log,resource,before_json,after_json) VALUES(?,?,?,?)",
                     (log_id, resource, json.dumps(old, sort_keys=True), json.dumps(new, sort_keys=True)))
        conn.execute("INSERT INTO moderation_resource_heads(resource,log) VALUES(?,?) "
                     "ON CONFLICT(resource) DO UPDATE SET log=excluded.log", (resource, log_id))
    count = conn.execute("SELECT COUNT(*) FROM moderation_events WHERE batch=?", (batch,)).fetchone()[0] + 1 if batch else 0
    suspended = bool(guarded and count >= LIMIT)
    conn.execute("INSERT INTO moderation_events(log,batch,paused,created) VALUES(?,?,?,?)", (log_id, batch, int(suspended), now()))
    if suspended:
        conn.execute("UPDATE moderator_state SET paused=1,updated=? WHERE player=?", (now(), moderator))
    return {"paused": suspended, "count": count, "limit": LIMIT, "batch": batch or 0}


def status(conn, moderator):
    row = conn.execute("SELECT p.nick,s.paused,s.batch FROM players p LEFT JOIN moderator_state s ON s.player=p.id WHERE p.id=?", (moderator,)).fetchone()
    if row is None:
        state = conn.execute("SELECT paused,batch FROM moderator_state WHERE player=?", (moderator,)).fetchone()
        if state is None:
            raise accounts.AuthError("not_found", 404)
        row = {"nick": "Удалённый аккаунт", "paused": state["paused"], "batch": state["batch"]}
    batch = row["batch"] or 0
    stats = conn.execute("SELECT COUNT(*),MIN(l.created),MAX(l.created) FROM moderation_events e "
                         "JOIN moderation_log l ON l.id=e.log WHERE e.batch=?", (batch,)).fetchone()
    actions = [dict(r) for r in conn.execute("SELECT l.id,l.target,p.nick,l.action,l.reason,l.created FROM moderation_events e "
        "JOIN moderation_log l ON l.id=e.log LEFT JOIN players p ON p.id=l.target WHERE e.batch=? ORDER BY l.id", (batch,))]
    total = conn.execute("SELECT COUNT(*) FROM moderation_log WHERE moderator=?", (moderator,)).fetchone()[0]
    bans = conn.execute("SELECT COUNT(*),SUM(created>?) FROM moderation_log WHERE moderator=? AND action='ban'",
                        (now()-86400, moderator)).fetchone()
    return {"player": moderator, "nick": row["nick"], "paused": bool(row["paused"]), "batch": batch,
            "count": stats[0], "first": stats[1] or 0, "last": stats[2] or 0, "total": total,
            "bans_total": bans[0], "bans_day": bans[1] or 0, "actions": actions}


def moderators(conn):
    return [status(conn, r[0]) for r in conn.execute("SELECT player FROM community_roles WHERE role='moderator' ORDER BY player")]


def history(conn, moderator, page=0):
    return [dict(r) for r in conn.execute("SELECT l.id,l.target,l.action,l.reason,l.created,b.state FROM moderation_log l "
        "LEFT JOIN moderation_events e ON e.log=l.id LEFT JOIN moderator_batches b ON b.id=e.batch "
        "WHERE l.moderator=? ORDER BY l.id DESC LIMIT 10 OFFSET ?", (moderator, max(0, page)*10))]


def reviewable(conn, moderator):
    row = conn.execute("SELECT COUNT(e.log),MAX(e.log),MIN(e.created),MAX(e.created) FROM moderation_events e "
        "JOIN moderator_batches b ON b.id=e.batch WHERE b.moderator=? AND b.state IN ('pending','approved')", (moderator,)).fetchone()
    return {"count": row[0], "last_log": row[1] or 0, "first": row[2] or 0, "last": row[3] or 0}


def pause(conn, moderator, actor):
    from . import community
    if community.has(conn, moderator, "support"):
        raise accounts.AuthError("staff", 403)
    status(conn, moderator)
    conn.execute("INSERT INTO moderator_state(player,paused,updated) VALUES(?,1,?) "
                 "ON CONFLICT(player) DO UPDATE SET paused=1,updated=excluded.updated", (moderator, now()))
    conn.execute("INSERT INTO moderator_owner_log(moderator,actor,action,created) VALUES(?,?,'pause',?)", (moderator, str(actor), now()))
    return status(conn, moderator)


def resume(conn, moderator, actor):
    from . import community
    if not community.has(conn, moderator, "moderator"):
        raise accounts.AuthError("moderator_required", 403)
    info = status(conn, moderator)
    if info["batch"]:
        conn.execute("UPDATE moderator_batches SET state='approved',closed=?,reviewed_by=? WHERE id=? AND state='pending'",
                     (now(), str(actor), info["batch"]))
    conn.execute("INSERT INTO moderator_state(player,paused,batch,updated) VALUES(?,0,NULL,?) "
                 "ON CONFLICT(player) DO UPDATE SET paused=0,batch=NULL,updated=excluded.updated", (moderator, now()))
    conn.execute("INSERT INTO moderator_owner_log(moderator,actor,action,batch,created) VALUES(?,?,'resume',?,?)",
                 (moderator, str(actor), info["batch"], now()))
    return status(conn, moderator)


def undo(conn, moderator, batch_id, actor, reviewed=False):
    batch = conn.execute("SELECT * FROM moderator_batches WHERE id=? AND moderator=?", (batch_id, moderator)).fetchone()
    if batch is None or batch["state"] not in (("pending", "approved", "reverted") if reviewed else ("pending", "reverted")):
        raise accounts.AuthError("batch", 409)
    if batch["state"] == "reverted":
        return {"ok": True, "repeated": True, "restored": 0, "skipped": 0}
    restored = skipped = 0
    events = conn.execute("SELECT log FROM moderation_events WHERE batch=? ORDER BY log DESC", (batch_id,)).fetchall()
    for event in events:
        for effect in conn.execute("SELECT * FROM moderation_effects WHERE log=?", (event[0],)).fetchall():
            resource = effect["resource"]; table, raw_id = resource.split(":")
            if table not in FIELDS:
                continue
            head = conn.execute("SELECT log FROM moderation_resource_heads WHERE resource=?", (resource,)).fetchone()
            before, after = json.loads(effect["before_json"]), json.loads(effect["after_json"])
            current = _row(conn, table, int(raw_id))
            if not head or head[0] != event[0] or current != after:
                skipped += 1; continue
            if before is None and table in ("bans", "warnings"):
                column = "lifted" if table == "bans" else "seen"
                conn.execute("UPDATE " + table + " SET " + column + "=? WHERE id=?", (now(), int(raw_id)))
            elif before is not None:
                columns = FIELDS[table]
                conn.execute("UPDATE " + table + " SET " + ",".join(k+"=?" for k in columns) + " WHERE id=?",
                             (*[before[k] for k in columns], int(raw_id)))
            else:
                skipped += 1; continue
            # The preceding effect in the same batch can now be undone too.
            previous = conn.execute("SELECT MAX(e.log) FROM moderation_effects e LEFT JOIN moderation_events v ON v.log=e.log "
                                    "LEFT JOIN moderator_batches b ON b.id=v.batch WHERE e.resource=? AND e.log<? "
                                    "AND (b.state IS NULL OR b.state!='reverted')", (resource, event[0])).fetchone()[0]
            if previous:
                conn.execute("UPDATE moderation_resource_heads SET log=? WHERE resource=?", (previous, resource))
            else:
                conn.execute("DELETE FROM moderation_resource_heads WHERE resource=?", (resource,))
            restored += 1
    conn.execute("UPDATE moderator_batches SET state='reverted',closed=?,reviewed_by=? WHERE id=?", (now(), str(actor), batch_id))
    pause(conn, moderator, actor)
    conn.execute("UPDATE moderator_state SET batch=NULL WHERE player=? AND batch=?", (moderator, batch_id))
    conn.execute("INSERT INTO moderator_owner_log(moderator,actor,action,batch,created,detail) VALUES(?,?,'undo',?,?,?)",
                 (moderator, str(actor), batch_id, now(), json.dumps({"restored": restored, "skipped": skipped})))
    return {"ok": True, "restored": restored, "skipped": skipped, "paused": True}


def undo_all(conn, moderator, last_log, actor):
    current = reviewable(conn, moderator)
    if current["last_log"] != last_log:
        raise accounts.AuthError("batch", 409)
    batches = conn.execute("SELECT id FROM moderator_batches WHERE moderator=? AND state IN ('pending','approved') ORDER BY id DESC", (moderator,)).fetchall()
    result = {"ok": True, "restored": 0, "skipped": 0, "paused": True}
    for batch in batches:
        part = undo(conn, moderator, batch[0], actor, reviewed=True)
        result["restored"] += part["restored"]; result["skipped"] += part["skipped"]
    return result


def pending(conn, owner):
    return [dict(r) for r in conn.execute("SELECT e.*,l.moderator,l.target,l.action,l.reason,l.created,p.nick AS moderator_nick,t.nick AS target_nick "
        "FROM moderation_events e JOIN moderation_log l ON l.id=e.log LEFT JOIN players p ON p.id=l.moderator "
        "LEFT JOIN players t ON t.id=l.target LEFT JOIN moderation_event_delivery d ON d.log=e.log AND d.owner=? "
        "WHERE d.log IS NULL ORDER BY e.log LIMIT 30", (owner,))]


def delivered(conn, log_id, owner):
    conn.execute("INSERT OR IGNORE INTO moderation_event_delivery(log,owner,sent) VALUES(?,?,?)", (log_id, owner, now()))
