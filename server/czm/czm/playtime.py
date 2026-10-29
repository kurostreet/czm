"""Time on game servers and the Top 100 built from it.

Only real play counts: the game reports presence about every 30 seconds, with the server's address
while it is actually connected to a game server (not the menu, a lobby or a connection attempt).
The service credits the time between two such reports by its own clock, at most CAP seconds at a
time: a phone that sleeps, loses the network or closes the game stops earning at once, and a client
never sends a number of hours. Two phones of one account credit the same wall-clock time once.

The time belongs to the player row: an account keeps it on any phone, a guest who registers keeps
his. Nothing is invented for the time before this was counted.

On a third-party server the game's reports are part of the trust: the service bounds what a client
can earn, but cannot prove every second of it without the server's own help.
"""
import sqlite3

from .db import now

CAP = 60                       # seconds credited per report at most (reports come every 30 s)
LIMIT = 100

SCHEMA = """
CREATE TABLE IF NOT EXISTS playtime (
    player INTEGER PRIMARY KEY REFERENCES players(id),
    seconds INTEGER NOT NULL DEFAULT 0,
    credited INTEGER NOT NULL DEFAULT 0,    -- the service's time up to which play was counted
    updated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS playtime_rank ON playtime(seconds DESC, player);
-- each install of a player: when it last reported being in a game (0: in the menu)
CREATE TABLE IF NOT EXISTS playtime_installs (
    player INTEGER NOT NULL,
    owner TEXT NOT NULL,
    last_play INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player, owner)
);
"""
# who is on the board: some time played and no active ban
_ELIGIBLE = ("t.seconds > 0 AND NOT EXISTS (SELECT 1 FROM bans b WHERE b.player = t.player AND b.kind = 'ban' "
             "AND b.lifted IS NULL AND (b.until IS NULL OR b.until > ?))")


def accrue(conn: sqlite3.Connection, player: int, owner: str, playing: bool, t: int | None = None) -> int:
    """A presence report of one install: returns the seconds it adds.

    The install played from its previous in-game report to this one (at most CAP seconds back);
    only the part after what was already counted for the player is added, so two phones of one
    account, a repeated or a late report never count the same second twice."""
    t = now() if t is None else t
    conn.execute("INSERT OR IGNORE INTO playtime(player, updated) VALUES (?, ?)", (player, t))
    if not playing:
        conn.execute("UPDATE playtime_installs SET last_play=0 WHERE player=? AND owner=?", (player, owner))
        return 0
    row = conn.execute("SELECT last_play FROM playtime_installs WHERE player=? AND owner=?", (player, owner)).fetchone()
    previous = row["last_play"] if row else 0
    counted = conn.execute("SELECT credited FROM playtime WHERE player=?", (player,)).fetchone()["credited"]
    credit = max(0, t - max(counted, previous, t - CAP)) if previous else 0
    conn.execute("INSERT INTO playtime_installs(player, owner, last_play) VALUES (?,?,?) "
                 "ON CONFLICT(player, owner) DO UPDATE SET last_play=MAX(last_play, excluded.last_play)", (player, owner, t))
    conn.execute("UPDATE playtime SET seconds=seconds+?, credited=MAX(credited, ?), updated=? WHERE player=?",
                 (credit, t if previous else counted, t, player))
    conn.execute("DELETE FROM playtime_installs WHERE player=? AND last_play>0 AND last_play<?", (player, t - 86400))
    return credit


def tier(place: int | None) -> str:
    """TOP 1, 2, 3 have their own crowns; then gold to 10, silver to 50, bronze to 100."""
    if not place or place > LIMIT:
        return ""
    if place <= 3:
        return f"top{place}"
    return "top10" if place <= 10 else "top50" if place <= 50 else "top100"


def places(conn: sqlite3.Connection) -> dict[int, int]:
    """player id -> place, for the hundred."""
    rows = conn.execute(f"SELECT t.player FROM playtime t WHERE {_ELIGIBLE} ORDER BY t.seconds DESC, t.player LIMIT ?",
                        (now(), LIMIT)).fetchall()
    return {r["player"]: i + 1 for i, r in enumerate(rows)}


def standing(conn: sqlite3.Connection, player: int) -> dict | None:
    """The exact place of any player and his time; None before his first minute on a server."""
    row = conn.execute(f"SELECT t.seconds FROM playtime t WHERE t.player=? AND {_ELIGIBLE}", (player, now())).fetchone()
    if row is None:
        return None
    seconds = row["seconds"]
    above = conn.execute(f"SELECT COUNT(*) FROM playtime t WHERE {_ELIGIBLE} AND (t.seconds > ? OR (t.seconds = ? AND t.player < ?))",
                         (now(), seconds, seconds, player)).fetchone()[0]
    place = above + 1
    return {"place": place, "seconds": seconds, "tier": tier(place)}


def board(conn: sqlite3.Connection, viewer: int = 0) -> dict:
    from . import social
    t = now()
    rows = conn.execute(
        f"SELECT t.player, t.seconds, p.nick, p.avatar, p.avatar_rev, "
        f"EXISTS(SELECT 1 FROM social_presence pr WHERE pr.player=t.player AND pr.seen>?) AS online, "
        f"EXISTS(SELECT 1 FROM staff s WHERE s.player=t.player) AS support "
        f"FROM playtime t JOIN players p ON p.id=t.player WHERE {_ELIGIBLE} "
        f"ORDER BY t.seconds DESC, t.player LIMIT ?", (t - social.PRESENCE_TTL, t, LIMIT)).fetchall()
    from . import service, community
    roles = community.role_map(conn, [r["player"] for r in rows])
    top = [{"place": i + 1, "id": r["player"], "nick": r["nick"], "avatar": service.avatar_ref(r), "seconds": r["seconds"],
            "online": bool(r["online"]), "tier": tier(i + 1),
            **({"role": roles[r["player"]][0], "project": roles[r["player"]][1]} if r["player"] in roles else {})}
           for i, r in enumerate(rows)]
    result = {"top": top, "players": conn.execute(f"SELECT COUNT(*) FROM playtime t WHERE {_ELIGIBLE}", (t,)).fetchone()[0]}
    if viewer:
        me = standing(conn, viewer)
        if me and me["place"] > LIMIT and len(top) == LIMIT:
            me["behind"] = max(0, top[-1]["seconds"] - me["seconds"] + 1)   # to pass the hundredth now
        result["me"] = me
    return result
