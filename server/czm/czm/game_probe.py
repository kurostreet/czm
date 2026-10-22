"""Bounded, public-IP-only GoldSrc/Source A2S_INFO probe.

Status is advisory: an independent game server may fill up before players connect.
No slot reservation is implied.
"""
import ipaddress
import socket
import struct

REQUEST=b"\xff\xff\xff\xffTSource Engine Query\x00"
TIMEOUT=1.8

class ProbeError(Exception):
    pass

def _string(packet, pos):
    end=packet.find(b"\x00",pos)
    if end<pos or end<0 or end-pos>256:
        raise ProbeError("bad_info")
    return packet[pos:end].decode("latin-1","replace"),end+1

def decode(packet):
    """Decode unfragmented Source (I) or legacy GoldSrc (m) response."""
    if len(packet)<8 or packet[:4]!=b"\xff"*4:
        raise ProbeError("bad_info")
    tag=packet[4]
    pos=5
    if tag==0x49:
        pos+=1 # protocol
        name,pos=_string(packet,pos)
        map_name,pos=_string(packet,pos)
        folder,pos=_string(packet,pos)
        game,pos=_string(packet,pos)
        if len(packet)<pos+5:
            raise ProbeError("bad_info")
        appid,players,maximum,bots=struct.unpack_from("<HBBB",packet,pos)
    elif tag==0x6d:
        addr,pos=_string(packet,pos)
        name,pos=_string(packet,pos)
        map_name,pos=_string(packet,pos)
        folder,pos=_string(packet,pos)
        game,pos=_string(packet,pos)
        if len(packet)<pos+3:
            raise ProbeError("bad_info")
        players,maximum,_protocol=struct.unpack_from("<BBB",packet,pos)
        appid=10
    else:
        raise ProbeError("bad_info")
    if folder.lower()!="cstrike" or maximum<1 or maximum>64 or players>maximum:
        raise ProbeError("bad_game")
    return {"players":players,"max_players":maximum,"map":map_name,"name":name}

def probe(address):
    try:
        host,raw_port=address.split(":",1)
        ip=ipaddress.IPv4Address(host)
        port=int(raw_port)
        if not ip.is_global or not 1<=port<=65535:
            raise ValueError("nonpublic")
    except (ValueError,ipaddress.AddressValueError) as exc:
        raise ProbeError("invalid_server") from exc
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(TIMEOUT)
            sock.connect((str(ip),port))
            sock.send(REQUEST)
            packet=sock.recv(1500)
            if packet[:5]==b"\xff"*4+b"A":
                if len(packet)<9:
                    raise ProbeError("bad_challenge")
                sock.send(REQUEST+packet[5:9])
                packet=sock.recv(1500)
            return decode(packet)
    except (socket.error,TimeoutError) as exc:
        raise ProbeError("unavailable") from exc
