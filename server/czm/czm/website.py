"""Public data for the site counter-zombie.ru: live numbers, the chat as a broadcast, release notes.

Everything here is read-only for visitors and needs no player key. Numbers are real:
- online: players with the game open now (the same count as the chat button);
- offline: every other known install;
- downloads: installs known before the site counted downloads, plus one per address and day
  that fetched the APK through the public link since.
"""
import hashlib
import re
import sqlite3
import time

from . import profanity, service, social
from .config import get_settings

ROOMS = ("global", "ru", "en")
CHAT_LIMIT = 100
NEWS_LIMIT = 3
_ONLY_MASK = re.compile(r"^[\s*]*$")


def ensure_counters(conn: sqlite3.Connection) -> None:
    """The first run remembers how many installs existed before downloads were counted."""
    conn.execute("INSERT OR IGNORE INTO site_counters(name, value) "
                 "SELECT 'downloads_base', COUNT(*) FROM players")
    conn.execute("INSERT OR IGNORE INTO site_counters(name, value) VALUES ('downloads', 0)")


def _counter(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT value FROM site_counters WHERE name = ?", (name,)).fetchone()
    return int(row[0]) if row else 0


def record_download(conn: sqlite3.Connection, ip: str) -> bool:
    """One download per address and day; the address is kept only as a salted hash for two days."""
    ensure_counters(conn)
    day = int(time.time() // 86400)
    digest = hashlib.sha256(f"{get_settings().pepper}:dl:{day}:{ip}".encode()).hexdigest()[:32]
    conn.execute("DELETE FROM site_downloads WHERE day < ?", (day - 1,))
    added = conn.execute("INSERT OR IGNORE INTO site_downloads(day, ip_hash) VALUES (?, ?)", (day, digest)).rowcount > 0
    if added:
        conn.execute("UPDATE site_counters SET value = value + 1 WHERE name = 'downloads'")
    return added


def set_play_beta_testers(conn: sqlite3.Connection, count: int) -> None:
    """Record ONLY the opted-in count checked in Google Play Console, not button clicks."""
    if not isinstance(count, int) or not 0 <= count <= 1000000:
        raise ValueError("invalid Play Console tester count")
    ensure_counters(conn)
    for name, value in (("play_beta_testers", count), ("play_beta_checked_at", int(time.time()))):
        conn.execute(
            "INSERT INTO site_counters(name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (name, value),
        )


def stats(conn: sqlite3.Connection) -> dict:
    ensure_counters(conn)
    players = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    online = min(social.online_count(conn), players)
    release = service.latest_release(conn)
    beta_checked = _counter(conn, "play_beta_checked_at")
    return {
        "online": online,
        "offline": max(0, players - online),
        "downloads": _counter(conn, "downloads_base") + _counter(conn, "downloads"),
        # A public number is shown only after an owner entered the count from Play Console.
        "play_beta_testers": _counter(conn, "play_beta_testers") if beta_checked else None,
        "play_beta_checked_at": beta_checked,
        "version": release["version"] if release else "",
        "size_mb": round(release["size"] / 1048576) if release and release.get("size") else 0,
    }


def avatar_url(player: int, ref: str) -> str:
    if ref.startswith("photo:"):
        return f"/avatars/{player}.png?v={ref[6:]}"
    if ref.isdigit() and 1 <= int(ref) <= 10:
        return f"/assets/avatar-{int(ref)}.png"
    return "/assets/logo-96.png"


def chat(conn: sqlite3.Connection, after: int = 0) -> list[dict]:
    """The last messages of every room, oldest first; masked-only lines are left out."""
    rows = conn.execute(
        "SELECT m.id, m.room, m.player, m.text, m.created, p.nick, p.avatar, p.avatar_rev FROM messages m "
        "JOIN players p ON p.id = m.player WHERE m.deleted = 0 AND m.id > ? AND m.room IN (?, ?, ?) "
        "ORDER BY m.id DESC LIMIT ?",
        (max(0, after), *ROOMS, CHAT_LIMIT),
    ).fetchall()
    out = []
    for r in reversed(rows):
        text = profanity.clean(r["text"])
        if _ONLY_MASK.match(text):
            continue
        out.append({"id": r["id"], "room": r["room"], "nick": r["nick"], "avatar": avatar_url(r["player"], service.avatar_ref(r)),
                    "text": text, "ts": r["created"]})
    return out


def deleted(conn: sqlite3.Connection, after: int) -> list[int]:
    rows = conn.execute("SELECT id FROM messages WHERE deleted = 1 AND id > ? ORDER BY id DESC LIMIT 50",
                        (max(0, after - 300),)).fetchall()
    return [r["id"] for r in rows]


def news(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT version, notes, published FROM releases WHERE published IS NOT NULL ORDER BY code DESC LIMIT ?",
        (NEWS_LIMIT,),
    ).fetchall()
    return [{"version": r["version"], "notes": (r["notes"] or service.DEFAULT_NOTES).strip()[:600], "ts": r["published"]}
            for r in rows]

