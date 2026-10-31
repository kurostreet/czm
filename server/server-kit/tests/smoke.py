"""Install the actual release archive and query a real native server on loopback."""
import argparse
import configparser
import importlib.util
import json
import os
import pathlib
import re
import secrets
import signal
import socket
import subprocess
import sys
import time

SOURCE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import installer
from build_kits import build


def rcon(password, port, command):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(2)
        sock.connect(('127.0.0.1', port))
        sock.send(b'\xff' * 4 + b'challenge rcon\n')
        challenge = re.search(rb'challenge rcon (-?\d+)', sock.recv(65535))
        if not challenge:
            raise ValueError('Missing RCON challenge')
        message = 'rcon ' + challenge.group(1).decode() + ' "' + password + '" ' + command + '\n'
        sock.send(b'\xff' * 4 + message.encode())
        parts = []
        while True:
            try:
                parts.append(sock.recv(65535)[5:].decode('utf-8', 'replace').rstrip('\0'))
                sock.settimeout(.2)
            except socket.timeout:
                break
        output = ''.join(parts)
        if password in output:
            raise ValueError('RCON response contains a credential')
        return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--work', type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    archive = build(installer.SYSTEM, args.output, args.work / 'build-cache')
    unpacked = args.work / 'unpacked'
    installer.extract(archive, unpacked)
    root = unpacked / ('CZM-Server-' + installer.SYSTEM.title())
    python = str(root / 'runtime/python.exe') if os.name == 'nt' else sys.executable
    subprocess.run([python, str(root / 'installer.py'), 'install', '--yes'], check=True)
    spec = importlib.util.spec_from_file_location('packaged_installer', root / 'installer.py')
    packaged = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packaged)
    kit = packaged.ServerKit(root)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = configparser.ConfigParser(interpolation=None)
    config.read(root / 'server.ini')
    config['server']['port'] = str(port)
    config['server']['players'] = '8'
    config['server']['name'] = 'CZM Starter Smoke'
    with (root / 'server.ini').open('w') as stream:
        config.write(stream)
    kit.configure()
    password = secrets.token_urlsafe(32)
    cfg = kit.cs / 'server.cfg'
    with cfg.open('a') as stream:
        stream.write('\nsv_rcon_condebug 0\nrcon_password "' + password + '"\n')
    env = dict(os.environ, SteamAppId='10', SteamGameId='10')
    if os.name != 'nt':
        env['LD_LIBRARY_PATH'] = str(kit.steam / 'linux32') + ':' + str(kit.game)
    log = args.work / 'native-server.log'
    commands = [str(kit.binary), '-console', '-game', 'cstrike', '-ip', '127.0.0.1', '-port', str(port),
                '-insecure', '-nomaster', '-nobreakpad', '+maxplayers', '8', '+map', installer.MAP, '+exec', 'server.cfg']
    receipt = {'platform': installer.SYSTEM, 'archive_sha256': installer.sha256(archive), 'commands': {}, 'ok': False}
    with log.open('wb') as stream:
        child = subprocess.Popen(commands, cwd=kit.game, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError('Native server exited before responding')
                try:
                    plugins = rcon(password, port, 'amxx plugins')
                    bot = rcon(password, port, 'yb list')
                    if ('Zombie Plague' in plugins and 'CZM Server' in plugins and
                            'bad load' not in plugins.lower() and '1 bots' in bot):
                        receipt['commands'].update({'amxx plugins': plugins, 'yb list': bot})
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('Zombie plugins or test bot did not become ready')
            for command in ['version', 'status', 'meta list', 'amxx modules', 'sv_rcon_condebug']:
                receipt['commands'][command] = rcon(password, port, command)
            if '12 plugins, 12 running' not in receipt['commands']['amxx plugins']:
                raise RuntimeError('Not all starter plugins loaded')
            if installer.MAP not in receipt['commands']['status']:
                raise RuntimeError('Wrong initial map')
            if password in log.read_text(encoding='utf-8', errors='replace'):
                raise RuntimeError('Console unexpectedly exposed the temporary test credential')
            # The public export must not contain any administrative configuration.
            if any(p.suffix.lower() in {'.cfg', '.ini', '.dll', '.so'} for p in (root / 'fastdl').rglob('*') if p.is_file()):
                raise RuntimeError('Private file present in FastDL export')
            receipt['ok'] = True
        finally:
            if child.poll() is None:
                try:
                    rcon(password, port, 'quit')
                    child.wait(timeout=15)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    child.terminate()
                    child.wait(timeout=15)
            # Only sanitized diagnostics may leave the test worker.
            diagnostic = log.read_text(encoding='utf-8', errors='replace').replace(password, '[REDACTED]')
            (args.output / (installer.SYSTEM + '-server.log')).write_text(diagnostic, encoding='utf-8')
            (args.output / (installer.SYSTEM + '-smoke.json')).write_text(json.dumps(receipt, indent=2))
            print(json.dumps(receipt), flush=True)
            if not receipt['ok']:
                print('\n'.join(diagnostic.splitlines()[-45:]), flush=True)
    if not receipt['ok']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
