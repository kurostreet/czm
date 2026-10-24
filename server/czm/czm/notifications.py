"""Account-scoped unread events. Acknowledgements name only displayed events."""
from .db import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_clock(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
INSERT OR IGNORE INTO notification_clock VALUES(1,0);
CREATE TABLE IF NOT EXISTS social_notices(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 player INTEGER NOT NULL REFERENCES accounts(player),
 peer INTEGER NOT NULL REFERENCES accounts(player),
 kind TEXT NOT NULL CHECK(kind IN ('friends','followers','following')),
 seen INTEGER NOT NULL DEFAULT 0,
 created INTEGER NOT NULL,
 UNIQUE(player,peer,kind)
);
CREATE INDEX IF NOT EXISTS social_notices_unread ON social_notices(player,kind,seen);
CREATE TABLE IF NOT EXISTS chat_reads(
 player INTEGER NOT NULL REFERENCES accounts(player), room TEXT NOT NULL,
 through INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player,room)
);
CREATE TABLE IF NOT EXISTS chat_message_sequence(id INTEGER PRIMARY KEY CHECK(id=1), last_id INTEGER NOT NULL);
INSERT OR IGNORE INTO chat_message_sequence SELECT 1,COALESCE(MAX(id),0) FROM messages;
CREATE TRIGGER IF NOT EXISTS chat_message_sequence_insert AFTER INSERT ON messages
BEGIN UPDATE chat_message_sequence SET last_id=MAX(last_id,NEW.id) WHERE id=1; END;
UPDATE chat_message_sequence SET last_id=MAX(last_id,(SELECT COALESCE(MAX(id),0) FROM messages)) WHERE id=1;
"""
for _table in ('social_follows', 'social_notices', 'private_messages', 'private_dialogs', 'messages', 'chat_reads'):
    for _operation in ('INSERT', 'UPDATE', 'DELETE'):
        SCHEMA += (f'CREATE TRIGGER IF NOT EXISTS notice_clock_{_table}_{_operation} AFTER {_operation} ON {_table} '
                   'BEGIN UPDATE notification_clock SET revision=revision+1 WHERE id=1; END;\n')


def add(conn, player, peer, kind):
    conn.execute('DELETE FROM social_notices WHERE player=? AND peer=? AND kind=?', (player, peer, kind))
    conn.execute('INSERT INTO social_notices(player,peer,kind,created) VALUES(?,?,?,?)', (player, peer, kind, now()))


def clear_pair(conn, a, b):
    conn.execute('DELETE FROM social_notices WHERE (player=? AND peer=?) OR (player=? AND peer=?)', (a, b, b, a))


def baseline(conn, player, rooms):
    # An account's first poll starts at today's messages rather than flagging
    # its entire retained chat history. Existing read positions never advance.
    for room in rooms:
        conn.execute('INSERT OR IGNORE INTO chat_reads(player,room,through) '
                     'VALUES(?,?,(SELECT COALESCE(MAX(id),0) FROM messages WHERE room=?))', (player, room, room))


def counts(conn, player, rooms):
    result = {'new_friends': 0, 'following_updates': 0}
    for row in conn.execute('SELECT kind,COUNT(*) AS n FROM social_notices WHERE player=? AND seen=0 GROUP BY kind', (player,)):
        if row['kind'] == 'friends': result['new_friends'] = row['n']
        if row['kind'] == 'following': result['following_updates'] = row['n']
    for room in rooms:
        result['chat_' + room] = conn.execute(
            'SELECT COUNT(*) FROM messages m JOIN chat_reads r ON r.room=m.room AND r.player=? '
            'WHERE m.room=? AND m.id>r.through AND m.player!=? AND m.deleted=0', (player, room, player)).fetchone()[0]
    result['revision'] = conn.execute('SELECT revision FROM notification_clock WHERE id=1').fetchone()[0]
    return result


def event_id(conn, player, peer, kind):
    row = conn.execute('SELECT id FROM social_notices WHERE player=? AND peer=? AND kind=? AND seen=0', (player, peer, kind)).fetchone()
    return row['id'] if row else 0


def read_events(conn, player, kind, ids):
    # Other accounts' IDs, another tab, late responses and unseen later events
    # cannot be acknowledged by a stale page.
    ids = list(set(ids))
    if not ids: return
    marks = ','.join('?' for _ in ids)
    args = (player, kind, *ids)
    if kind == 'followers':
        conn.execute(f'UPDATE social_follows SET seen=1 WHERE target=? AND source IN '
                     f'(SELECT peer FROM social_notices WHERE player=? AND kind=? AND id IN ({marks}))', (player, *args))
    conn.execute(f'UPDATE social_notices SET seen=1 WHERE player=? AND kind=? AND id IN ({marks}) AND seen=0', args)


def read_chat(conn, player, room, through):
    # Clamp to a real message of this room, not a client-supplied global ID.
    actual = conn.execute('SELECT COALESCE(MAX(id),0) FROM messages WHERE room=? AND id<=?', (room, through)).fetchone()[0]
    conn.execute('INSERT INTO chat_reads VALUES(?,?,?) ON CONFLICT(player,room) '
                 'DO UPDATE SET through=MAX(through,excluded.through)', (player, room, actual))
