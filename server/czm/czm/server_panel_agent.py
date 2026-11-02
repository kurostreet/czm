"""Bounded Unix-socket control for the one configured systemd game unit."""
import argparse
import grp
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import subprocess
import threading
import time

UNIT = "czm-zm-test.service"
SOCKET = "/run/czm-server-panel/control.sock"
RCON = "/srv/czm-zm-test/private/rcon.txt"
PORT = 27016
lock = threading.Lock()


def system(*args):
    result = subprocess.run(args, capture_output=True, timeout=28, text=True, errors="replace")
    if result.returncode and args[0] != "journalctl":
        raise RuntimeError("service_operation")
    return result.stdout


def scrub(text):
    try:
        secret = Path(RCON).read_text().strip()
        if secret:
            text = text.replace(secret, "[скрыто]")
    except OSError:
        pass
    text = re.sub(r"(?im)^.*(?:rcon_password|rcon from|rcon\s+\d|password\s*[=:]).*$", "[служебная строка скрыта]", text)
    return text[-48000:]


def status():
    values = system("systemctl", "show", UNIT, "-p", "ActiveState", "-p", "SubState", "-p", "MainPID",
                    "-p", "MemoryCurrent", "-p", "MemoryMax", "-p", "CPUUsageNSec", "-p", "NRestarts",
                    "-p", "ActiveEnterTimestampMonotonic", "-p", "CPUQuotaPerSecUSec")
    raw = dict(line.split("=", 1) for line in values.splitlines() if "=" in line)
    def number(key):
        try:
            return int(raw.get(key, 0))
        except ValueError:
            return 0
    return {"state": raw.get("ActiveState", "unknown"), "substate": raw.get("SubState", "unknown"),
            "pid": number("MainPID"), "memory": number("MemoryCurrent"), "memory_limit": number("MemoryMax"),
            "cpu_ns": number("CPUUsageNSec"), "restarts": number("NRestarts"), "cpu_limit": 35,
            "uptime": max(0, int(time.monotonic() - number("ActiveEnterTimestampMonotonic") / 1e6)) if raw.get("ActiveState") == "active" else 0}


def rcon(command):
    if not command or len(command.encode()) > 512 or any(ord(c) < 32 for c in command):
        raise ValueError("command")
    if re.search(r"(?i)(?:rcon_password|rcon_users|sv_rcon_condebug)", command):
        raise ValueError("protected")
    secret = Path(RCON).read_text().strip()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(1.5)
        sock.connect(("127.0.0.1", PORT))
        sock.send(b"\xff\xff\xff\xffchallenge rcon\n")
        challenge = sock.recv(4096).decode("latin1", errors="replace")
        match = re.search(r"challenge rcon ([-0-9]+)", challenge)
        if not match:
            raise RuntimeError("game_unavailable")
        packet = f'rcon {match[1]} "{secret}" {command}\n'.encode()
        sock.send(b"\xff\xff\xff\xff" + packet)
        out = bytearray()
        deadline = time.monotonic() + 2
        while len(out) < 48000 and time.monotonic() < deadline:
            try:
                chunk = sock.recv(8192)
            except socket.timeout:
                break
            out.extend(chunk.removeprefix(b"\xff\xff\xff\xff").removeprefix(b"l"))
            sock.settimeout(.18)
    text = bytes(out).decode("utf-8", errors="replace").replace("\x00", "")
    return scrub(text)


def game_info():
    # Bounded A2S_INFO, no remote targets or credentials supplied by the browser.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(.7)
        sock.connect(("127.0.0.1", PORT))
        query = b"\xff\xff\xff\xffTSource Engine Query\x00"
        sock.send(query)
        raw = sock.recv(4096)
        if raw[:5] == b"\xff\xff\xff\xffA":
            sock.send(query + raw[5:9])
            raw = sock.recv(4096)
    if raw[:5] != b"\xff\xff\xff\xffI":
        return None
    pos = 6
    values = []
    for _ in range(4):
        end = raw.index(0, pos)
        values.append(raw[pos:end].decode("utf-8", errors="replace"))
        pos = end + 1
    pos += 2
    return {"name": values[0], "map": values[1], "players": raw[pos], "slots": raw[pos + 1], "bots": raw[pos + 2]}


def dispatch(body):
    action = body.get("action")
    if action == "status":
        result = status()
        try:
            result["game"] = game_info() if result["state"] == "active" else None
        except (OSError, ValueError, IndexError):
            result["game"] = None
        return result
    if action == "power":
        verb = body.get("verb")
        if verb not in {"start", "stop", "restart"}:
            raise ValueError("action")
        with lock:
            system("systemctl", verb, UNIT)
        return {"ok": True, **status()}
    if action == "logs":
        # Only this unit's current start, never raw system or historical credentials.
        text = system("journalctl", "-u", UNIT, "-n", "100", "--since", "-30 min", "--no-pager", "-o", "cat")
        return {"text": scrub(text)}
    if action == "console":
        with lock:
            return {"text": rcon(body.get("command", ""))}
    raise ValueError("action")


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(4)
        try:
            raw = self.rfile.readline(4097)
            if len(raw) > 4096 or not raw.endswith(b"\n"):
                raise ValueError("request")
            body = json.loads(raw)
            result = {"ok": True, "result": dispatch(body)}
        except (ValueError, TypeError, KeyError, AttributeError):
            result = {"ok": False, "error": "request"}
        except Exception:
            result = {"ok": False, "error": "game_unavailable"}
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode() + b"\n")


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    request_queue_size = 8


def main():
    os.umask(0o007)
    Path(SOCKET).unlink(missing_ok=True)
    with Server(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o660)
        server.serve_forever()


if __name__ == "__main__":
    main()
