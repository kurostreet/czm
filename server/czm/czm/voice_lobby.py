"""Volatile, authorized pre-match audio forwarding for CZM lobbies.

Protocol v1: binary G.711 mu-law 16-kHz, 320 samples per frame (20 ms).
Client->server: b'U' + 320 bytes mu-law.\nServer->client: b'U' + 4-byte big-endian sender player ID + 320 bytes mu-law.
Text frames and room membership IDs are never trusted from the network.
Control JSON: {"type":"talk","player":id,"active":bool}, {"type":"joined","player":id},
{"type":"left","player":id}. A client may announce only its own mic enabled
flag and sensitivity; the relay assigns the sender ID. No stored audio data.
"""
import asyncio
import struct
import time
import json
from dataclasses import dataclass, field
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from . import accounts, lobbies, moderation, rules
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
    mic_enabled: bool = False
    explicit_mic: bool = False
    control_window: float = 0.0
    controls: int = 0
    sensitivity: int = 50
    # players this one blocked or was blocked by: no audio either way
    blocked: frozenset = frozenset()

_rooms: dict[str, dict[int, VoicePeer]] = defaultdict(dict)


def _ulaw_energy(value):
    value = (~value) & 255
    amplitude = ((((value & 15) << 3) + 132) << ((value >> 4) & 7)) - 132
    return amplitude * amplitude


_ENERGY = tuple(_ulaw_energy(i) for i in range(256))


def has_sound(audio, sensitivity=50):
    threshold=max(100,900-sensitivity*11)
    return bool(audio) and sum(_ENERGY[value] for value in audio) >= len(audio) * threshold * threshold


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
    # Without accepted community rules a player may listen but not speak.
    terms = conn.execute("SELECT rules_version, rules_client FROM players WHERE id=?", (player,)).fetchone()
    muted = (bool(row and row["host_muted"]) or
             (not host and bool(active_room["voice_mute_all"])) or
             bool(punishment and punishment["mute_until"] > lobbies.now()) or
             rules.required(terms) or
             moderation.sanction(conn, player, "voice") is not None)
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


def blocked_peers(conn, player):
    rows = conn.execute("SELECT target AS other FROM social_blocks WHERE source=? "
                        "UNION SELECT source FROM social_blocks WHERE target=?", (player, player)).fetchall()
    return frozenset(row["other"] for row in rows)


async def _acl(key,room):
    """(player, muted, blocked) — rechecked every second."""
    def check():
        with db() as conn:
            player,muted=can_transmit(conn,key,room)
            return player,muted,blocked_peers(conn,player)
    return await asyncio.to_thread(check)


async def websocket_voice(ws: WebSocket, room: str):
    key=ws.headers.get("x-czm-key","")
    if len(room)>64 or not key:
        await ws.close(code=4401)
        return
    try:
        player,muted,blocked=await _acl(key,room)
    except (accounts.AuthError,ValueError):
        await ws.close(code=4403)
        return

    occupants = _rooms[room]
    # One speaking socket per identity. Do not allow stale sockets to broadcast.
    if player in occupants or len(occupants)>=MAX_PEERS:
        await ws.close(code=4409)
        return
    await ws.accept()
    peer=VoicePeer(player=player,socket=ws,room=room,blocked=blocked)
    occupants[player]=peer
    for other in occupants.values():
        if other.player!=player:
            _enqueue(peer,{"type":"joined","player":other.player})
            if other.explicit_mic:
                _enqueue(peer,{"type":"mic","player":other.player,"enabled":other.mic_enabled,"sensitivity":other.sensitivity})
    _notify(room,{"type":"joined","player":player},player)
    sender=asyncio.create_task(_send_loop(peer))
    checked=time.monotonic()
    try:
        while True:
            timestamp=time.monotonic()
            if timestamp-checked>=AUTH_INTERVAL:
                try:
                    _,muted,peer.blocked=await _acl(key,room)
                except (accounts.AuthError,ValueError):
                    await ws.close(code=4403)
                    break
                checked=timestamp
                if muted and peer.mic_enabled:
                    peer.mic_enabled=False
                    _notify(room,{"type":"mic","player":player,"enabled":False},player)

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
                # A peer may announce only its own on/off intent. Player IDs,
                # host controls and speaking events remain server-assigned.
                text=message.get("text","")
                try:
                    control=json.loads(text) if len(text)<=100 else None
                except (TypeError,ValueError): control=None
                if (not isinstance(control,dict) or not {"type","enabled"}<=set(control) or
                        set(control)-{"type","enabled","sensitivity"} or
                        control["type"]!="mic" or type(control["enabled"]) is not bool or
                        type(control.get("sensitivity",50)) is not int or not 0<=control.get("sensitivity",50)<=100):
                    await ws.close(code=4400)
                    break
                if timestamp-peer.control_window>=1.0: peer.control_window=timestamp;peer.controls=0
                peer.controls+=1
                if peer.controls>10:
                    await ws.close(code=4408)
                    break
                if control["enabled"]:
                    try:
                        _,muted,peer.blocked=await _acl(key,room)
                    except (accounts.AuthError,ValueError):
                        await ws.close(code=4403)
                        break
                    checked=timestamp
                peer.explicit_mic=True;peer.mic_enabled=control["enabled"] and not muted;peer.sensitivity=control.get("sensitivity",50)
                _notify(room,{"type":"mic","player":player,"enabled":peer.mic_enabled,"sensitivity":peer.sensitivity},player)
                if not peer.mic_enabled and peer.talking:
                    peer.talking=False
                    _notify(room,{"type":"talk","player":player,"active":False})
                continue
            if len(audio)!=VOICE_PACKET or audio[0:1]!=b'U':
                continue
            if timestamp-peer.window>=1.0:
                peer.window=timestamp
                peer.frames=0
            peer.frames+=1
            if peer.frames>MAX_FRAMES_PER_SECOND or muted or (peer.explicit_mic and not peer.mic_enabled):
                continue
            if has_sound(audio[1:],peer.sensitivity):
                if not peer.talking:
                    peer.talking=True
                    _notify(room,{"type":"talk","player":player,"active":True})
                peer.last_sound=timestamp
            packet=b"U"+struct.pack("!I",player)+audio[1:]
            for other,recipient in list(_rooms.get(room,{}).items()):
                if other!=player and other not in peer.blocked and player not in recipient.blocked:
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
