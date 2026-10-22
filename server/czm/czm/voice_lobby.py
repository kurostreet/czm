"""Volatile, authorized pre-match audio forwarding for CZM lobbies.

Protocol v1: binary G.711 mu-law 16-kHz, 320 samples per frame (20 ms).
Client->server: b'U' + 320 bytes mu-law.\nServer->client: b'U' + 4-byte big-endian sender player ID + 320 bytes mu-law.
Text frames and room membership IDs are never trusted from the network.
Control JSON: {"type":"talk","player":id,"active":bool}, {"type":"joined","player":id},
{"type":"left","player":id}. No recordings, no database audio data.
"""
import asyncio
import struct
import time
from dataclasses import dataclass, field
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from . import accounts, lobbies
from .db import db

VOICE_PACKET = 321
MAX_FRAMES_PER_SECOND = 60
VOICE_IDLE = 0.7
AUTH_INTERVAL = 1.0
MAX_PEERS = 6

@dataclass(eq=False)
class VoicePeer:
    player: int
    socket: WebSocket
    room: str
    outgoing: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=32))
    last_sound: float = 0.0
    talking: bool = False
    window: float = 0.0
    frames: int = 0

_rooms: dict[str, dict[int, VoicePeer]] = defaultdict(dict)


def can_transmit(conn, key, room):
    """Re-authorize every second: kicked / banned / closed / muted players stop."""
    player = lobbies._actor(conn, key)
    active_room = lobbies._room(conn, room)
    lobbies._membership(conn, room, player)
    host = active_room["owner"] == player
    row = conn.execute("SELECT host_muted FROM lobby_voice_mutes "
                       "WHERE lobby=? AND player=?", (room, player)).fetchone()
    punishment = conn.execute("SELECT mute_until FROM lobby_moderation WHERE player=?",
                              (player,)).fetchone()
    muted = (bool(row and row["host_muted"]) or
             (not host and bool(active_room["voice_mute_all"])) or
             bool(punishment and punishment["mute_until"] > lobbies.now()))
    return player, muted


def set_host_mute(conn, key, room, target, muted):
    player = lobbies._actor(conn, key)
    target_room = lobbies._room(conn, room)
    lobbies._membership(conn, room, player)
    if target_room["owner"] != player:
        raise accounts.AuthError("not_owner",403)
    if target is None:
        conn.execute("UPDATE lobbies SET voice_mute_all=? WHERE id=?",
                     (int(muted),room))
        return {"all": bool(muted)}
    if type(target) is not int or target < 1 or target == player:
        raise accounts.AuthError("bad_target",400)
    lobbies._membership(conn, room, target)
    conn.execute("INSERT INTO lobby_voice_mutes(lobby,player,host_muted) VALUES(?,?,?) "
                 "ON CONFLICT(lobby,player) DO UPDATE SET host_muted=excluded.host_muted",
                 (room,target,int(muted)))
    return {"target":target,"muted":bool(muted)}


def _enqueue(peer: VoicePeer, value):
    if peer.outgoing.full():
        try:
            peer.outgoing.get_nowait()
        except asyncio.QueueEmpty:
            pass
    peer.outgoing.put_nowait(value)


def _notify(room: str, obj: dict, except_player=None):
    for player, peer in list(_rooms.get(room,{}).items()):
        if player != except_player:
            _enqueue(peer,obj)


async def _send_loop(peer: VoicePeer):
    while True:
        item=await peer.outgoing.get()
        if isinstance(item,bytes):
            await peer.socket.send_bytes(item)
        else:
            await peer.socket.send_json(item)


async def _acl(key,room):
    def check():
        with db() as conn:
            return can_transmit(conn,key,room)
    return await asyncio.to_thread(check)


async def websocket_voice(ws: WebSocket, room: str):
    key=ws.headers.get("x-czm-key","")
    if len(room)>64 or not key:
        await ws.close(code=4401)
        return
    try:
        player,muted=await _acl(key,room)
    except (accounts.AuthError,ValueError):
        await ws.close(code=4403)
        return

    occupants = _rooms[room]
    # One speaking socket per identity. Do not allow stale sockets to broadcast.
    if player in occupants or len(occupants)>=MAX_PEERS:
        await ws.close(code=4409)
        return
    await ws.accept()
    peer=VoicePeer(player=player,socket=ws,room=room)
    occupants[player]=peer
    for other in occupants.values():
        if other.player!=player:
            _enqueue(peer,{"type":"joined","player":other.player})
    _notify(room,{"type":"joined","player":player},player)
    sender=asyncio.create_task(_send_loop(peer))
    checked=time.monotonic()
    try:
        while True:
            timestamp=time.monotonic()
            if timestamp-checked>=AUTH_INTERVAL:
                try:
                    _,muted=await _acl(key,room)
                except (accounts.AuthError,ValueError):
                    await ws.close(code=4403)
                    break
                checked=timestamp

            if peer.talking and timestamp-peer.last_sound>VOICE_IDLE:
                peer.talking=False
                _notify(room,{"type":"talk","player":player,"active":False})

            try:
                message=await asyncio.wait_for(ws.receive(),timeout=.3)
            except asyncio.TimeoutError:
                continue
            if message.get("type")=="websocket.disconnect":
                break
            audio=message.get("bytes")
            if audio is None:
                # All text payloads are invalid; close rather than interpreting
                # any client-controlled event as someone else's speaking state.
                await ws.close(code=4400)
                break
            if len(audio)!=VOICE_PACKET or audio[0:1]!=b'U':
                continue
            if timestamp-peer.window>=1.0:
                peer.window=timestamp
                peer.frames=0
            peer.frames+=1
            if peer.frames>MAX_FRAMES_PER_SECOND or muted:
                continue
            if not peer.talking:
                peer.talking=True
                _notify(room,{"type":"talk","player":player,"active":True})
            peer.last_sound=timestamp
            packet=b"U"+struct.pack("!I",player)+audio[1:]
            for other,recipient in list(_rooms.get(room,{}).items()):
                if other!=player:
                    _enqueue(recipient,packet)
    except (WebSocketDisconnect,RuntimeError):
        pass
    finally:
        sender.cancel()
        try:
            await sender
        except asyncio.CancelledError:
            pass
        if _rooms.get(room,{}).get(player) is peer:
            _rooms[room].pop(player,None)
            _notify(room,{"type":"left","player":player},player)
        if not _rooms.get(room):
            _rooms.pop(room,None)
