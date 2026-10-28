"""What players hear about Google Play releases: the bell's news and the site's "What's new".

A build that passed CI or sits on the internal track is not news. Every quarter of an hour the
service reads the Play tracks (read only) and learns each release's code, version and notes. A
release becomes news as soon as it is on the public track: the closed test (alpha) while there is
no production, then production. The bell in the game, the site's "What's new" and the owner's bot
get it at once (the owner's decision of 28.10.2026: every alpha update is announced everywhere).
Google may still be reviewing it for a few hours; the bell's button opens Google Play, which offers
the update as soon as Google approves it. Internal releases are never announced.

The old feed (one item per site build, "1.35-<commit>") was cleared once; the migration screen of
old site installs is a separate mechanism (distribution.py) and stays. play_witnesses still records
who updated (account deletion removes those rows).
"""
import logging
import re
import sqlite3
import time

from .db import now

log = logging.getLogger("czm.play_feed")

PUBLIC_TRACKS = ("production", "alpha")
SYNC_EVERY = 900
WITNESSES = 2                  # a fallback only: sync() announces a public release first
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
          "октября", "ноября", "декабря")

SCHEMA = """
-- Releases of the Google Play app as the Play tracks list them; announced: when it became news.
CREATE TABLE IF NOT EXISTS play_releases (
    code INTEGER PRIMARY KEY,
    version TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    notes_en TEXT NOT NULL DEFAULT '',      -- the English notes ('' = none: English players read Russian)
    tracks TEXT NOT NULL DEFAULT '',
    first_seen INTEGER NOT NULL,
    public_since INTEGER,
    announced INTEGER,
    news_id INTEGER,
    notified INTEGER NOT NULL DEFAULT 0
);
-- Players who updated to a release on the public track (existing installs, not staff).
CREATE TABLE IF NOT EXISTS play_witnesses (
    code INTEGER NOT NULL,
    player INTEGER NOT NULL,
    seen INTEGER NOT NULL,
    PRIMARY KEY (code, player)
);
"""


def version_name(version: str) -> str:
    """What a player reads: "1.35", never the commit of "1.35-85efaec"."""
    m = re.match(r"\d+(?:\.\d+)*", version or "")
    return m.group(0) if m else ""


def day(ts: int) -> str:
    t = time.localtime(ts)
    return f"{t.tm_mday} {MONTHS[t.tm_mon - 1]}"


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?…])\s+|\n+", text or "") if p.strip()]


def _words(sentence: str) -> set[str]:
    return set(re.findall(r"\w+", sentence.lower().replace("ё", "е")))


def fresh_notes(notes: str, earlier: list[str]) -> str:
    """Play notes often repeat the previous update for players who skipped it; the bell and the site
    list every update, so a news item keeps only the sentences that are new. A sentence is old when
    nearly all of its words (4 of 5) were in one sentence of an earlier item: "Индикатор загрузки не
    зависает" after "Индикатор загрузки больше не зависает" is old, a new fix is not."""
    old = [_words(s) for text in earlier for s in _sentences(text)]
    kept = []
    for sentence in _sentences(notes):
        words = _words(sentence)
        if words and any(len(words & o) * 5 >= len(words) * 4 for o in old if o):
            continue
        kept.append(sentence)
    return " ".join(kept)


def news_text(row, earlier: list[str] | None = None) -> str:
    title = TITLE
    name = version_name(row["version"])
    head = f"{title}, версия {name}" if name else title
    notes = (row["notes"] or "").strip()
    body = fresh_notes(notes, earlier or []) if earlier else notes
    return f"{head}\n{body or 'Исправления и улучшения.'}"[:1000]


def news_text_en(row, earlier: list[str] | None = None) -> str:
    """The same item for the English game; '' when the release has no English notes."""
    notes = (row["notes_en"] or "").strip()
    if not notes:
        return ""
    name = version_name(row["version"])
    head = f"{TITLE_EN}, version {name}" if name else TITLE_EN
    body = fresh_notes(notes, earlier or []) if earlier else notes
    return f"{head}\n{body or 'Fixes and improvements.'}"[:1000]


def _flag(conn, name: str) -> bool:
    row = conn.execute("SELECT value FROM site_counters WHERE name=?", (name,)).fetchone()
    return bool(row and row[0])


def _set_flag(conn, name: str, value: int) -> None:
    conn.execute("INSERT INTO site_counters(name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                 (name, value))


def migrate(conn: sqlite3.Connection) -> None:
    """Once: the bell and the site drop the items of the old site builds. Called by db.init(),
    outside a transaction: executescript commits whatever is open."""
    conn.executescript(SCHEMA)
    if "notes_en" not in {r[1] for r in conn.execute("PRAGMA table_info(play_releases)")}:
        conn.execute("ALTER TABLE play_releases ADD COLUMN notes_en TEXT NOT NULL DEFAULT ''")
    if _flag(conn, "news_feed_play"):
        return
    gone = conn.execute("UPDATE news SET deleted=1 WHERE deleted=0 AND id IN "
                        "(SELECT news_id FROM releases WHERE news_id IS NOT NULL)").rowcount
    _set_flag(conn, "news_feed_play", 1)
    log.info("news of %d site builds left the bell", gone)


def _notes(release: dict, english: bool = False) -> str:
    notes = release.get("releaseNotes") or []
    for n in notes:
        if str(n.get("language", "")).lower().startswith("en" if english else "ru"):
            return str(n.get("text", "")).strip()
    if english:
        return ""
    return str(notes[0].get("text", "")).strip() if notes else ""


def _version(release: dict) -> str:
    # our publisher names releases "40140101 (1.35-85efaec)"
    name = str(release.get("name", ""))
    m = re.search(r"\(([^()]+)\)", name)
    return (m.group(1) if m else name).strip()[:32]


def public_track(tracks: dict) -> str:
    live = any(r.get("status") == "completed" for r in tracks.get("production", []))
    return "production" if live else "alpha"


def sync(conn: sqlite3.Connection, tracks: dict) -> None:
    """tracks: {"internal": [release, ...], "alpha": [...], ...} as the Play Developer API lists them."""
    t = now()
    first_run = conn.execute("SELECT COUNT(*) FROM play_releases").fetchone()[0] == 0
    public = public_track(tracks)
    found: dict[int, dict] = {}
    for track, releases in tracks.items():
        for release in releases or []:
            if release.get("status") not in ("completed", "inProgress"):
                continue                      # a draft or a halted rollout reaches nobody
            for code in release.get("versionCodes") or []:
                info = found.setdefault(int(code), {"version": _version(release), "notes": _notes(release),
                                                    "notes_en": _notes(release, True), "tracks": set()})
                info["tracks"].add(track)
    for code, info in found.items():
        on_public = public in info["tracks"]
        listed = ",".join(sorted(info["tracks"]))
        row = conn.execute("SELECT * FROM play_releases WHERE code=?", (code,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO play_releases(code, version, notes, notes_en, tracks, first_seen, public_since) "
                         "VALUES (?,?,?,?,?,?,?)", (code, info["version"], info["notes"], info["notes_en"], listed, t,
                                                    t if on_public else None))
            if first_run and on_public:
                # players already have it: the site lists it, the bell does not ring for it
                uploaded = conn.execute("SELECT MIN(created) FROM play_publishes WHERE version_code=?", (code,)).fetchone()[0]
                conn.execute("UPDATE play_releases SET announced=?, notified=1 WHERE code=?", (uploaded or t, code))
        else:
            conn.execute("UPDATE play_releases SET version=?, notes=?, notes_en=?, tracks=?, public_since=COALESCE(public_since, ?) "
                         "WHERE code=?", (info["version"] or row["version"], info["notes"] or row["notes"],
                                          info["notes_en"] or row["notes_en"], listed, t if on_public else None, code))
    if found:
        marks = ",".join("?" * len(found))
        conn.execute(f"UPDATE play_releases SET tracks='' WHERE code NOT IN ({marks})", tuple(found))
    if not first_run:
        # a release on the public track is news at once: the bell, the site and the bot
        for code in sorted(c for c, info in found.items() if public in info["tracks"]):
            announce(conn, code)


def witness(conn: sqlite3.Connection, before, player, code: int, store: int | None = None) -> bool:
    """Called by hello: before is the player's row before this hello (None for a new install).
    Returns True when this update made the release news."""
    if not code or store == 0 or before is None or player is None:
        return False
    if before["version"] == player["version"]:
        return False                          # no update: the same build as last time
    row = conn.execute("SELECT * FROM play_releases WHERE code=? AND public_since IS NOT NULL AND announced IS NULL",
                       (code,)).fetchone()
    if row is None or before["created"] >= row["public_since"]:
        return False
    if conn.execute("SELECT 1 FROM staff WHERE player=?", (player["id"],)).fetchone():
        return False
    conn.execute("INSERT OR IGNORE INTO play_witnesses(code, player, seen) VALUES (?,?,?)", (code, player["id"], now()))
    if conn.execute("SELECT COUNT(*) FROM play_witnesses WHERE code=?", (code,)).fetchone()[0] < WITNESSES:
        return False
    return announce(conn, code)


def remember(conn: sqlite3.Connection, code: int, version: str, notes: str, notes_en: str) -> None:
    """What we sent to Google Play with a release. Play keeps release notes only in the store
    listing's languages; while the listing has no English, the English text lives here and the
    bell and the site still get it. Notes Play gives later take the place of these."""
    t = now()
    conn.execute("INSERT INTO play_releases(code, version, notes, notes_en, tracks, first_seen) VALUES (?,?,?,?,'',?) "
                 "ON CONFLICT(code) DO UPDATE SET notes_en=CASE WHEN play_releases.notes_en='' THEN excluded.notes_en "
                 "ELSE play_releases.notes_en END", (int(code), version, (notes or "").strip(), (notes_en or "").strip(), t))
    row = conn.execute("SELECT news_id, notes_en FROM play_releases WHERE code=?", (int(code),)).fetchone()
    if row["news_id"] and row["notes_en"]:
        # already news: the English game gets the English text too
        conn.execute("UPDATE news SET text_en=? WHERE id=? AND text_en=''",
                     (news_text_en(conn.execute("SELECT * FROM play_releases WHERE code=?", (int(code),)).fetchone()), row["news_id"]))


def announce(conn: sqlite3.Connection, code: int) -> bool:
    row = conn.execute("SELECT * FROM play_releases WHERE code=?", (code,)).fetchone()
    if row is None or row["announced"]:
        return False
    # what the bell and the site already told players about the previous updates
    told = conn.execute(
        "SELECT n.text, n.text_en, r.notes, r.notes_en FROM play_releases r LEFT JOIN news n ON n.id = r.news_id AND n.deleted = 0 "
        "WHERE r.announced IS NOT NULL AND r.code < ? ORDER BY r.code DESC LIMIT 3", (code,)).fetchall()
    earlier = [r["text"] or r["notes"] for r in told]
    earlier_en = [r["text_en"] or r["notes_en"] for r in told]
    news_id = conn.execute("INSERT INTO news (text, text_en, created) VALUES (?, ?, ?)",
                           (news_text(row, earlier), news_text_en(row, earlier_en), now())).lastrowid
    conn.execute("UPDATE play_releases SET announced=?, news_id=? WHERE code=?", (now(), news_id, code))
    log.info("Google Play %s (%d) is news", row["version"], code)
    return True


def latest(conn: sqlite3.Connection, limit: int = 3) -> list[dict]:
    """The releases on the Play tracks now, newest first: Play offers each account the one of its
    track, and the bell shows the notes of exactly that code."""
    rows = conn.execute("SELECT code, version, notes, notes_en FROM play_releases WHERE tracks != '' ORDER BY code DESC LIMIT ?",
                        (limit,)).fetchall()
    return [{"code": r["code"], "version": version_name(r["version"]), "notes": r["notes"], "notes_en": r["notes_en"]}
            for r in rows]


TITLE = "Обновление в Google Play"
TITLE_EN = "Google Play update"


def _body(text: str, title: str) -> str:
    head, _, body = (text or "").partition("\n")
    return body if head.startswith(title) and body.strip() else (text or "")


def site_news(conn: sqlite3.Connection, limit: int) -> list[dict]:
    """The site says what the bell says: the text of the release's news item, as the owner may have
    corrected it (/editnews), and nothing for an item he removed (/delnews). Releases players already
    had on the first look have no item and show the Play notes. notes_en: the English text ('' =
    none, the site shows the Russian one)."""
    rows = conn.execute("SELECT r.version, r.notes, r.notes_en, r.announced, n.id AS news, n.text, n.text_en "
                        "FROM play_releases r LEFT JOIN news n ON n.id = r.news_id "
                        "WHERE r.announced IS NOT NULL AND COALESCE(n.deleted, 0) = 0 "
                        "ORDER BY r.code DESC LIMIT ?", (limit,)).fetchall()
    items = []
    for r in rows:
        notes = _body(r["text"], TITLE) if r["text"] else r["notes"]
        notes_en = (_body(r["text_en"], TITLE_EN) if r["text_en"] else "") if r["news"] else r["notes_en"]
        items.append({"version": version_name(r["version"]), "notes": (notes or "Исправления и улучшения.").strip()[:600],
                      "notes_en": (notes_en or "").strip()[:600], "ts": r["announced"]})
    return items


def unnotified(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM play_releases WHERE announced IS NOT NULL AND notified=0 ORDER BY code")]


def mark_notified(conn: sqlite3.Connection, code: int) -> None:
    conn.execute("UPDATE play_releases SET notified=1 WHERE code=?", (code,))


def read_tracks() -> dict:
    """The Play tracks of the app, read in a throwaway edit. Raises on any failure."""
    import httpx
    from . import play_publish
    from .config import get_settings
    settings = get_settings()
    with httpx.Client(timeout=60) as client:
        auth = {"Authorization": "Bearer " + play_publish.access_token(client)}
        app = play_publish.API + settings.play_package
        edit = play_publish._check(client.post(f"{app}/edits", headers=auth), "правка")["id"]
        try:
            listed = play_publish._check(client.get(f"{app}/edits/{edit}/tracks", headers=auth), "дорожки")
        finally:
            try:
                client.delete(f"{app}/edits/{edit}", headers=auth)
            except httpx.HTTPError:
                pass
    return {t.get("track", ""): t.get("releases", []) for t in listed.get("tracks", [])}


async def run() -> None:
    """The background job of the service: the Play tracks every quarter of an hour."""
    import asyncio
    from . import db
    from .config import get_settings
    while True:
        try:
            if get_settings().play_service_account_file.is_file():
                tracks = await asyncio.to_thread(read_tracks)

                def store():
                    with db.db() as conn:
                        sync(conn, tracks)
                await asyncio.to_thread(store)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Google Play tracks not read: %s", e)
        await asyncio.sleep(SYNC_EVERY)
