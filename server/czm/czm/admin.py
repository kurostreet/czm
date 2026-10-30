"""Head administrator tools. A server allowlist and registered SUPPORT are both required."""
import hashlib
import json

from . import accounts,community,moderation,moderator_guard,server_moderation,service,play_feed
from .config import get_settings
from .db import now

PAGE=20
SCHEMA="""
CREATE TABLE IF NOT EXISTS admin_actions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor INTEGER NOT NULL,
 action TEXT NOT NULL, target INTEGER NOT NULL DEFAULT 0,
 detail TEXT NOT NULL, nonce TEXT NOT NULL, digest TEXT NOT NULL,
 result TEXT NOT NULL, created INTEGER NOT NULL, UNIQUE(actor,nonce)
);
"""

def allowed(conn,player):
    return player in get_settings().admin_ids and community.has(conn,player,"support")

def actor(conn,key):
    player=accounts.authenticated(conn,key)
    if not allowed(conn,player["id"]):raise accounts.AuthError("admin_required",403)
    return player

def person(conn,target):
    row=conn.execute("SELECT p.id,p.nick,p.seen,a.login,a.player AS account FROM players p "
        "LEFT JOIN accounts a ON a.player=p.id WHERE p.id=?",(target,)).fetchone()
    if row is None:raise accounts.AuthError("not_found",404)
    result=dict(row);result["account"]=row["account"] is not None
    result["roles"]=community.roles(conn,target)
    return result

def view(conn,key,section,target=0,query="",offset=0):
    principal=actor(conn,key);offset=max(0,offset)
    if section=="overview":
        result=moderation.summary(conn,key)
        for label,sql in {
            "players":"SELECT COUNT(*) FROM players","accounts":"SELECT COUNT(*) FROM accounts",
            "servers_blocked":"SELECT COUNT(*) FROM server_cases WHERE blocked=1",
            "server_reports":"SELECT COUNT(*) FROM server_reports",
            "moderators_paused":"SELECT COUNT(*) FROM moderator_state WHERE paused=1",
            "tickets":"SELECT COUNT(*) FROM tester_tickets"}.items():result[label]=conn.execute(sql).fetchone()[0]
        result["recent_players"]=conn.execute("SELECT COUNT(*) FROM players WHERE seen>?",(now()-120,)).fetchone()[0]
        result["development"]=service.latest_release(conn,channel="development")
        if result["development"]:
            result["development"]={k:result["development"][k] for k in ("version","code")}
        result["play"]=[{k:r[k] for k in ("version","code")} for r in play_feed.latest(conn)]
        return result
    if section=="players":
        needle=query.strip().replace("|","||").replace("%","|%").replace("_","|_")
        like="%"+needle+"%"
        rows=conn.execute("SELECT p.id FROM players p LEFT JOIN accounts a ON a.player=p.id "
            "WHERE (?='' OR CAST(p.id AS TEXT)=? OR p.nick LIKE ? ESCAPE '|' OR a.login LIKE ? ESCAPE '|') "
            "ORDER BY CASE WHEN CAST(p.id AS TEXT)=? THEN 0 ELSE 1 END,p.seen DESC,p.id DESC LIMIT ? OFFSET ?",
            (query.strip(),query.strip(),like,like,query.strip(),PAGE+1,offset)).fetchall()
        return {"players":[person(conn,r[0]) for r in rows[:PAGE]],"next":offset+PAGE if len(rows)>PAGE else -1}
    if section=="player":
        result=person(conn,target);result["moderation"]=moderation.player(conn,key,target)
        result["servers"]=[dict(r) for r in conn.execute("SELECT server,name FROM owner_servers WHERE player=? ORDER BY updated",(target,))]
        project=conn.execute("SELECT project FROM community_roles WHERE player=? AND role='server_owner'",(target,)).fetchone()
        result["project"]=project[0] if project else ""
        result["sanctions"]=[{**dict(r),"target":{"id":target,"nick":result["nick"]},"forever":r["until"] is None}
            for r in conn.execute("SELECT id,kind,reason,until FROM bans WHERE player=? AND lifted IS NULL "
                                  "AND (until IS NULL OR until>?) ORDER BY id DESC",(target,now()))]
        return result
    if section=="reports":return moderation.reports(conn,key,offset)
    if section=="sanctions":
        rows=conn.execute("SELECT b.id,b.player,b.kind,b.reason,b.until,p.nick FROM bans b LEFT JOIN players p ON p.id=b.player "
            "WHERE b.lifted IS NULL AND (b.until IS NULL OR b.until>?) ORDER BY b.id DESC LIMIT ? OFFSET ?",(now(),PAGE+1,offset)).fetchall()
        return {"sanctions":[{**dict(r),"target":{"id":r["player"],"nick":r["nick"] or "Удалённый аккаунт"},"forever":r["until"] is None}
                             for r in rows[:PAGE]],"next":offset+PAGE if len(rows)>PAGE else -1}
    if section=="moderators":return {"moderators":moderator_guard.moderators(conn)}
    if section=="moderator":
        active=community.has(conn,target,"moderator")
        if not active and not conn.execute("SELECT 1 FROM moderator_state WHERE player=?",(target,)).fetchone():
            raise accounts.AuthError("moderator_required",404)
        result=moderator_guard.status(conn,target)
        total=conn.execute("SELECT COUNT(*) FROM moderation_log WHERE moderator=?",(target,)).fetchone()[0]
        return {**result,"has_role":active,"history":moderator_guard.history(conn,target,offset//10),
                "reviewable":moderator_guard.reviewable(conn,target),"next":offset+10 if total>offset+10 else -1,
                "batch_last_log":conn.execute("SELECT MAX(log) FROM moderation_events WHERE batch=?",(result["batch"],)).fetchone()[0] or 0}
    if section=="servers":
        result=server_moderation.listing(conn,offset//server_moderation.PAGE)
        result["next"]=offset+server_moderation.PAGE if result["more"] else -1
        if offset==0:result["projects"]=[dict(r) for r in conn.execute(
            "SELECT o.server,o.name,o.player,p.nick,r.project FROM owner_servers o JOIN players p ON p.id=o.player "
            "JOIN community_roles r ON r.player=o.player AND r.role='server_owner' ORDER BY o.updated DESC LIMIT 100")]
        return result
    if section=="server":
        address=community.public_endpoint(query)
        result=server_moderation.info(conn,address)
        result["owners"]=[{**dict(r),"id":r["player"]} for r in conn.execute(
            "SELECT o.player,p.nick,r.project FROM owner_servers o JOIN players p ON p.id=o.player "
            "JOIN community_roles r ON r.player=o.player AND r.role='server_owner' WHERE o.server=? ORDER BY o.player",(address,))]
        result["reports"]=[dict(r) for r in conn.execute(
            "SELECT r.reporter,p.nick,r.reason,r.comment,r.created,"
            "(SELECT COUNT(*) FROM server_reports all_reports WHERE all_reports.reporter=r.reporter) AS author_total "
            "FROM server_reports r JOIN server_cases s ON s.id=r.server_id LEFT JOIN players p ON p.id=r.reporter "
            "WHERE s.server=? ORDER BY r.id DESC LIMIT 30",(address,))]
        result["history"]=[dict(r) for r in conn.execute("SELECT l.actor,l.action,l.reason,l.created FROM server_moderation_log l "
            "JOIN server_cases s ON s.id=l.server_id WHERE s.server=? ORDER BY l.id DESC LIMIT 20",(address,))]
        return result
    if section=="moderation_history":return moderation.history(conn,key,offset)
    if section=="role_history":
        rows=conn.execute("SELECT player,role,action,actor,created FROM community_role_log ORDER BY id DESC LIMIT ? OFFSET ?",(PAGE+1,offset)).fetchall()
        return {"roles":[dict(r) for r in rows[:PAGE]],"next":offset+PAGE if len(rows)>PAGE else -1}
    if section=="history":
        rows=conn.execute("SELECT id,actor,action,target,detail,created FROM admin_actions ORDER BY id DESC LIMIT ? OFFSET ?",
            (PAGE+1,offset)).fetchall()
        return {"actions":[dict(r) for r in rows[:PAGE]],"next":offset+PAGE if len(rows)>PAGE else -1}
    raise accounts.AuthError("section",404)

def action(conn,key,data):
    principal=actor(conn,key);nonce=data["nonce"]
    serial=json.dumps({k:v for k,v in data.items() if k!="nonce"},sort_keys=True,ensure_ascii=False)
    digest=hashlib.sha256(serial.encode()).hexdigest()
    previous=conn.execute("SELECT digest,result FROM admin_actions WHERE actor=? AND nonce=?",(principal["id"],nonce)).fetchone()
    if previous:
        if previous["digest"]!=digest:raise accounts.AuthError("nonce",409)
        return {**json.loads(previous["result"]),"repeated":True}
    accounts.rate(conn,"head-admin-actions",str(principal["id"]),100,60)
    kind=data["action"];target=data.get("target",0);reason=service.clean_text(data.get("reason",""),200)
    origin=f"game:{principal['id']}"
    if kind in moderation.ACTIONS:
        if not reason:raise accounts.AuthError("reason")
        result=moderation.act(conn,key,target,kind,data.get("minutes"),reason,data.get("report"),
            data.get("message"),data.get("lobby_message"),nonce)
    elif kind=="lift":result=moderation.lift(conn,key,data.get("sanction",0),nonce)
    elif kind=="role_grant":result=community.grant(conn,target,data.get("role",""),data.get("project",""),origin)
    elif kind=="role_revoke":result=community.revoke(conn,target,data.get("role",""),origin)
    elif kind in ("server_ban","server_unban"):
        address=community.public_endpoint(data.get("server",""))
        result=server_moderation.set_blocked(conn,address,kind=="server_ban",origin,reason)
    elif kind in ("mod_pause","mod_resume"):
        result=(moderator_guard.pause if kind=="mod_pause" else moderator_guard.resume)(conn,target,origin)
    elif kind=="mod_undo":
        moderator_guard.pause(conn,target,origin)
        expected=data.get("expected_log",0)
        if data.get("all_history"):
            result=moderator_guard.undo_all(conn,target,expected,origin)
        else:
            batch=data.get("batch",0)
            latest=conn.execute("SELECT MAX(log) FROM moderation_events WHERE batch=?",(batch,)).fetchone()[0] or 0
            if not expected or expected!=latest:raise accounts.AuthError("batch",409)
            result=moderator_guard.undo(conn,target,batch,origin)
    elif kind=="owner_server_remove":
        person(conn,target);address=community.public_endpoint(data.get("server",""))
        conn.execute("DELETE FROM owner_servers WHERE player=? AND server=?",(target,address));result={"ok":True}
    else:raise accounts.AuthError("action")
    result={"ok":True,**result}
    conn.execute("INSERT INTO admin_actions(actor,action,target,detail,nonce,digest,result,created) VALUES(?,?,?,?,?,?,?,?)",
        (principal["id"],kind,target,serial,nonce,digest,json.dumps(result,ensure_ascii=False),now()))
    return result
