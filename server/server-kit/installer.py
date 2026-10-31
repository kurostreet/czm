#!/usr/bin/env python3
"""CZM Server installer and local controls. Python 3.10+, standard library only.

SPDX-License-Identifier: GPL-3.0-or-later
Upstream components are downloaded separately, with their original licenses.
"""
import argparse
import configparser
import contextlib
import ctypes
import getpass
import hashlib
import json
import os
import pathlib
import platform
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import wave
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
SYSTEM = 'windows' if os.name == 'nt' else 'linux'
MAP = 'zm_czm_start'
RESOURCE_DIRS = ('maps', 'models', 'sound', 'sprites', 'gfx/env')
RESOURCE_TYPES = {'.bsp', '.mdl', '.wav', '.mp3', '.spr', '.tga', '.res', '.wad'}


def sha256(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open('rb') as src:
        for chunk in iter(lambda: src.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write(path, text, private=False):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    with temporary.open('w', encoding='utf-8', newline='\n') as dst:
        dst.write(text)
    temporary.chmod(0o600 if private else 0o644)
    temporary.replace(path)


def safe_path(root, name):
    # Reject Windows paths on Linux too. Never follow a pre-existing link outside root.
    if '\\' in name or ':' in name or '\0' in name:
        raise ValueError('Unsafe archive path')
    relative = pathlib.PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe archive path')
    target = root.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Archive path escapes destination')
    return target


def extract(archive, destination, strip=0):
    destination = pathlib.Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    total = 0

    def put(name, size, mode, src):
        nonlocal total
        # Validate even the parts stripped from a source archive's enclosing directory.
        safe_path(destination, name)
        parts = pathlib.PurePosixPath(name).parts[strip:]
        if not parts:
            return
        total += size
        if total > 300000000:
            raise ValueError('Archive uncompressed size exceeds limit')
        target = safe_path(destination, '/'.join(parts))
        target.parent.mkdir(parents=True, exist_ok=True)
        with src, target.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        target.chmod(0o755 if mode & 0o111 else 0o644)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                mode = entry.external_attr >> 16
                if not entry.is_dir() and not stat.S_ISLNK(mode):
                    put(entry.filename, entry.file_size, mode, package.open(entry))
    else:
        with tarfile.open(archive) as package:
            for entry in package:
                # No devices, hardlinks or symlinks, regardless of tarfile defaults.
                if entry.isfile():
                    put(entry.name, entry.size, entry.mode, package.extractfile(entry))


def download(package, cache, name):
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / name
    expected = package['sha256']
    if not re.fullmatch('[a-f0-9]{64}', expected):
        raise ValueError('Missing pinned checksum: ' + name)
    if target.exists() and sha256(target) == expected:
        return target
    url = package['url']
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise ValueError('Only verified HTTPS package downloads are supported')
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'CZM-Server-Setup/1.0'})
            with urllib.request.urlopen(request, timeout=40) as source, target.with_suffix('.part').open('wb') as dst:
                if urllib.parse.urlsplit(source.url).scheme != 'https':
                    raise ValueError('Insecure download redirect')
                received = 0
                for chunk in iter(lambda: source.read(1048576), b''):
                    received += len(chunk)
                    if received > 100000000:
                        raise ValueError('Package exceeds download limit')
                    dst.write(chunk)
            temporary = target.with_suffix('.part')
            if sha256(temporary) != expected:
                raise ValueError('Package checksum mismatch: ' + name)
            temporary.replace(target)
            return target
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2)


def settings(root):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(root / 'server.ini', encoding='utf-8-sig')
    section = parser['server']
    result = dict(section)
    for name, low, high in [('port', 1024, 65535), ('players', 2, 32), ('bots', 0, 8)]:
        result[name] = int(section[name])
        if not low <= result[name] <= high:
            raise ValueError(f'{name}: allowed range {low}–{high}')
    if result['bots'] >= result['players']:
        raise ValueError('Leave at least one slot for a human player')
    for name, maximum in [('name', 100), ('join_password', 64)]:
        value = result.get(name, '')
        if len(value.encode('utf-8')) > maximum or any(c in value for c in '\\";\r\n\0'):
            raise ValueError('Invalid server setting: ' + name)
    if not result['name'].strip():
        raise ValueError('Server name is required')
    url = result.get('fastdl_url', '').strip()
    if url:
        parts = urllib.parse.urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or
                parts.query or parts.fragment or re.search(r'[\s"\\;\x00-\x1f]', url)):
            raise ValueError('fastdl_url must be a public HTTPS directory URL')
        url = url.rstrip('/') + '/'
    result['fastdl_url'] = url
    return result


@contextlib.contextmanager
def installation_lock(root):
    with (root / 'setup.lock').open('a+b') as lock:
        lock.seek(0)
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


class ServerKit:
    def __init__(self, root=ROOT, system=SYSTEM):
        self.root = pathlib.Path(root).resolve()
        self.system = system
        self.game = self.root / 'game'
        self.cs = self.game / 'cstrike'
        self.manifest = json.loads((self.root / 'packages.json').read_text(encoding='utf-8'))
        self.cache = self.root / 'cache'
        self.staging = self.root / 'components'
        self.steam = self.root / 'steamcmd'
        self.logs = self.root / 'logs'
        self.binary = self.game / ('hlds.exe' if system == 'windows' else 'hlds_linux')

    def package(self, name):
        item = self.manifest['packages'][name]
        print('Получаем компонент: ' + name, flush=True)
        archive = download(item, self.cache, name + '.package')
        folder = self.staging / name
        extract(archive, folder, item.get('strip', 0))
        return folder

    def wizard(self):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(self.root / 'server.ini', encoding='utf-8-sig')
        for name, label in [('name', 'Название'), ('port', 'Порт UDP'), ('players', 'Мест'), ('bots', 'Ботов')]:
            value = input(label + ' [' + parser['server'][name] + ']: ').strip()
            if value:
                parser['server'][name] = value
        value = getpass.getpass('Пароль входа (Enter — оставить текущее значение): ')
        if value:
            parser['server']['join_password'] = value
        value = input('URL вашего HTTPS FastDL (Enter — настроить позднее): ').strip()
        if value:
            parser['server']['fastdl_url'] = value
        import io
        output = io.StringIO()
        parser.write(output)
        write(self.root / 'server.ini', output.getvalue(), private=True)
        settings(self.root)

    def command(self, command, cwd, env=None, timeout=1800):
        self.logs.mkdir(exist_ok=True)
        with (self.logs / 'install.log').open('ab') as log:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=os.name != 'nt')
            started = time.monotonic()
            last = started
            try:
                while process.poll() is None:
                    now = time.monotonic()
                    if now - started > timeout:
                        raise TimeoutError('Component setup timed out; see logs/install.log')
                    if now - last > 15:
                        print('Установка продолжается… Подробности: logs/install.log', flush=True)
                        last = now
                    time.sleep(.3)
            except BaseException:
                if os.name != 'nt':
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=20)
                raise
            if process.returncode:
                raise RuntimeError('Component setup failed; see logs/install.log')

    def install(self, yes=False):
        if (self.root / 'installed.json').exists():
            print('Уже установлено. Настройки — server.ini, затем configure; запуск — start.')
            return
        if self.system == 'linux' and hasattr(os, 'geteuid') and os.geteuid() == 0:
            raise ValueError('Install and run as a normal user, not root. See the VDS instructions.')
        if platform.machine().lower() not in ('amd64', 'x86_64', 'x86', 'i386', 'i686'):
            raise ValueError('This kit requires an Intel/AMD x86 or x86-64 computer, not ARM.')
        if re.search(r'[^A-Za-z0-9_./:\\-]', str(self.root)):
            raise ValueError('Extract into an ASCII path without spaces, e.g. C:\\CZM-Server-Windows or ~/CZM-Server-Linux.')
        if shutil.disk_usage(self.root).free < 3000000000:
            raise ValueError('At least 3 GB free space is required for the initial installation.')
        settings(self.root)
        if not yes:
            self.wizard()
        marker = self.root / 'installation-started'
        if self.game.exists() and any(self.game.iterdir()) and not marker.exists():
            raise ValueError('Existing game directory found. Use a NEW empty kit directory.')
        with installation_lock(self.root):
            marker.touch()
            self.game.mkdir(exist_ok=True)
            self.logs.mkdir(exist_ok=True)
            steam = self.package('steam-' + self.system)
            shutil.copytree(steam, self.steam, dirs_exist_ok=True)
            steam_exe = self.steam / ('steamcmd.exe' if self.system == 'windows' else 'steamcmd.sh')
            steam_exe.chmod(0o755)
            print('SteamCMD получает игровые данные. Нужен интернет; это может занять несколько минут.', flush=True)
            # HLDS occasionally needs a repeated app_update to populate all depots.
            for attempt in range(3):
                try:
                    self.command([str(steam_exe), '+@sSteamCmdForcePlatformType', self.system,
                                  '+force_install_dir', str(self.game), '+login', 'anonymous',
                                  '+app_set_config', '90', 'mod', 'cstrike',
                                  '+app_update', '90', '-beta', 'steam_legacy', 'validate', '+quit'], self.steam)
                except RuntimeError:
                    if attempt == 2:
                        raise
                    print('SteamCMD не завершил установку. Повторяем попытку…', flush=True)
                    time.sleep(3)
                    continue
                if self.binary.exists() and (self.cs / 'maps/de_dust2.bsp').exists():
                    break
            else:
                raise RuntimeError('SteamCMD did not install the required game data; see logs/install.log')
            self.install_components()
            self.configure()
            self.export_fastdl()
            self.service_template()
            write(self.root / 'installed.json', json.dumps({'version': self.manifest['version'],
                  'platform': self.system, 'time': int(time.time())}, indent=2))
        print('Готово. Запусти сервер через 2-START.cmd или ./start.sh. Остановка — Ctrl+C.', flush=True)

    def install_components(self):
        family = 'win32' if self.system == 'windows' else 'linux32'
        shutil.copytree(self.package('rehlds') / 'bin' / family, self.game, dirs_exist_ok=True)
        shutil.copytree(self.package('regamedll') / 'bin' / family / 'cstrike', self.cs, dirs_exist_ok=True)
        for name in ('metamod', 'amxx-base-' + self.system, 'amxx-cstrike-' + self.system, 'reapi'):
            shutil.copytree(self.package(name) / 'addons', self.cs / 'addons', dirs_exist_ok=True)
        reunion = self.package('reunion')
        library = 'reunion_mm.dll' if self.system == 'windows' else 'reunion_mm_i386.so'
        matches = list(reunion.rglob(library))
        if len(matches) != 1:
            raise RuntimeError('Unexpected Reunion package layout')
        destination = self.cs / 'addons/reunion'
        destination.mkdir(exist_ok=True)
        shutil.copy2(matches[0], destination / library)
        config = next(reunion.rglob('reunion.cfg')).read_text(encoding='utf-8-sig')
        config, count = re.subn(r'(?m)^SteamIdHashSalt\s*=.*$', 'SteamIdHashSalt = ' + secrets.token_hex(24), config)
        if count != 1:
            raise RuntimeError('Reunion salt setting not found')
        write(self.cs / 'reunion.cfg', config, private=True)
        zombie = self.package('zombie')
        shutil.copytree(zombie / 'addons', self.cs / 'addons', dirs_exist_ok=True)
        shutil.copytree(zombie / 'zp_resources', self.cs, dirs_exist_ok=True)
        shutil.copytree(self.package('yapb-' + self.system), self.cs, dirs_exist_ok=True)
        graph = download(self.manifest['packages']['graph'], self.cache, 'de_dust2.graph')
        target = self.cs / 'addons/yapb/data/graph' / (MAP + '.graph')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(graph, target)
        for relative in ('addons/amxmodx/logs', 'addons/amxmodx/data', 'addons/amxmodx/data/vault',
                         'addons/yapb/data/train', 'addons/yapb/data/vistable', 'logs', 'SAVE'):
            directory = self.cs / relative
            if directory.is_file() and directory.stat().st_size == 0:
                directory.unlink()
            directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.cs / 'maps/de_dust2.bsp', self.cs / 'maps' / (MAP + '.bsp'))
        probe = self.cs / 'sound/czm_server/network_probe_v1.wav'
        probe.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(probe), 'wb') as sound:
            sound.setnchannels(1)
            sound.setsampwidth(2)
            sound.setframerate(22050)
            sound.writeframes(b'\0' * 524288)
        script = self.cs / 'addons/amxmodx/scripting'
        write(script / 'czm_server_probe.sma', '#include <amxmodx>\n'
              'public plugin_precache(){precache_sound("czm_server/network_probe_v1.wav");}\n'
              'public plugin_init(){register_plugin("CZM Server", "1.0.0", "kurostreet");}\n')
        compiler = script / ('amxxpc.exe' if self.system == 'windows' else 'amxxpc')
        compiler.chmod(0o755)
        env = dict(os.environ)
        if self.system == 'linux':
            env['LD_LIBRARY_PATH'] = str(script)
        for name in ('zombie_plague40', 'zp_zclasses40', 'czm_server_probe'):
            self.command([str(compiler), str(script / (name + '.sma')), '-i' + str(script / 'include'),
                          '-o' + str(self.cs / 'addons/amxmodx/plugins' / (name + '.amxx'))], script, env)
        kind = 'win32' if self.system == 'windows' else 'linux'
        meta = 'addons/metamod/metamod.dll' if self.system == 'windows' else 'addons/metamod/metamod_i386.so'
        amxx = 'addons/amxmodx/dlls/amxmodx_mm.dll' if self.system == 'windows' else 'addons/amxmodx/dlls/amxmodx_mm_i386.so'
        bot = 'addons/yapb/bin/yapb.dll' if self.system == 'windows' else 'addons/yapb/bin/yapb.so'
        write(self.cs / 'addons/metamod/plugins.ini', f'{kind} addons/reunion/{library}\n{kind} {amxx}\n{kind} {bot}\n')
        write(self.cs / 'liblist.gam', 'game "CZM Zombie Server"\nversion "1.0"\n'
              'type "multiplayer_only"\nsecure "0"\ncldll "1"\n'
              f'gamedll "addons/metamod/metamod.dll"\ngamedll_linux "addons/metamod/metamod_i386.so"\n')
        for relative in (meta, amxx, bot, 'addons/reunion/' + library):
            if not (self.cs / relative).is_file():
                raise RuntimeError('Missing server component: ' + relative)
        plugins = ['admin', 'admincmd', 'adminhelp', 'menufront', 'cmdmenu', 'plmenu', 'mapsmenu', 'adminchat', 'adminvote',
                   'zombie_plague40', 'zp_zclasses40', 'czm_server_probe']
        write(self.cs / 'addons/amxmodx/configs/plugins.ini', '\n'.join(x + '.amxx' for x in plugins) + '\n')
        write(self.cs / 'addons/amxmodx/configs/users.ini', '; No preset administrators. Use installer.py admin STEAM_ID.\n', private=True)
        cfg = self.cs / 'addons/amxmodx/configs/zombieplague.cfg'
        existing = cfg.read_text(encoding='utf-8-sig') if cfg.exists() else ''
        write(cfg, existing + '\n// CZM starter defaults\nzp_lighting "i"\nzp_delay 8\n')
        write(self.cs / 'mapcycle.txt', MAP + '\n')
        write(self.cs / 'motd.txt', '<html><body><h2>CZM Zombie Server</h2></body></html>\n')
        for path in (self.game.rglob('*') if self.system == 'linux' else []):
            if path.is_file() and (path.suffix == '.so' or path.name in ('hlds_linux', 'hltv', 'amxxpc')):
                path.chmod(0o755)
        if self.system == 'linux':
            sdk = self.steam / 'linux32/steamclient.so'
            if not sdk.is_file():
                raise RuntimeError('SteamCMD did not install the 32-bit Steam runtime')
            shutil.copy2(sdk, self.game / 'steamclient.so')
            user_sdk = pathlib.Path.home() / '.steam/sdk32/steamclient.so'
            if not user_sdk.exists() and not user_sdk.is_symlink():
                user_sdk.parent.mkdir(parents=True, exist_ok=True)
                user_sdk.symlink_to(sdk)

    def configure(self):
        cfg = settings(self.root)
        if not self.binary.exists():
            raise ValueError('Install the server first')
        text = (f'hostname "{cfg["name"]}"\nsv_password "{cfg["join_password"]}"\n'
                f'sv_downloadurl "{cfg["fastdl_url"]}"\n'
                'rcon_password ""\nsv_rcon_condebug 0\nrcon_adduser 127.0.0.1\n'
                'sv_lan 0\nsv_allowdownload 1\nsv_allowupload 0\nsv_maxrate 100000\nsv_minrate 5000\n'
                'sv_maxupdaterate 60\nsv_minupdaterate 20\nsv_voiceenable 1\nsv_alltalk 1\nsv_timeout 90\n'
                'sv_consistency 0\nmp_timelimit 0\nmp_autoteambalance 0\nmp_limitteams 0\n'
                'mp_friendlyfire 0\nmp_freezetime 1\nmp_roundtime 4\nmp_flashlight 1\nsys_ticrate 100\n'
                f'yb_quota_mode normal\nyb_quota {cfg["bots"]}\nyb_join_after_player 0\nyb_difficulty 1\n'
                'yb_chat 0\nyb_autovacate 0\nlog on\nexec custom.cfg\n')
        write(self.cs / 'server.cfg', text, private=True)
        if not (self.cs / 'custom.cfg').exists():
            write(self.cs / 'custom.cfg', '// Your advanced overrides. Preserved by configure.\n', private=True)
        print('Настройки сохранены. Для их применения перезапусти сервер.', flush=True)
        if not cfg['fastdl_url']:
            print('FastDL пока не настроен: загрузка файлов будет медленной. Инструкция: https://counter-zombie.ru/create-server#fastdl', flush=True)

    def export_fastdl(self):
        destination = self.root / 'fastdl'
        count = 0
        for folder in RESOURCE_DIRS:
            base = self.cs / folder
            if not base.is_dir():
                continue
            for source in base.rglob('*'):
                if (not source.is_file() or source.is_symlink() or source.suffix.lower() not in RESOURCE_TYPES or
                        not source.resolve().is_relative_to(self.cs.resolve())):
                    continue
                target = destination / source.relative_to(self.cs)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                target.chmod(0o644)
                count += 1
        # WAD textures may be referenced from custom maps at the mod root.
        for source in self.cs.glob('*.wad'):
            if source.is_file() and not source.is_symlink():
                destination.mkdir(exist_ok=True)
                shutil.copy2(source, destination / source.name)
        print(f'FastDL: подготовлено {count} файлов. Папка: fastdl/', flush=True)
        return count

    def service_template(self):
        if self.system != 'linux':
            return
        import pwd
        owner = pwd.getpwuid(self.root.stat().st_uid)
        if owner.pw_uid == 0:
            raise ValueError('The kit directory must belong to a normal server user')
        text = ('[Unit]\nDescription=CZM Zombie Server\nAfter=network-online.target\nWants=network-online.target\n'
                '[Service]\nType=simple\n'
                f'User={owner.pw_name}\nGroup={owner.pw_gid}\nWorkingDirectory={self.root}\n'
                f'ExecStart=/usr/bin/python3 {self.root}/installer.py run\n'
                'Restart=on-failure\nRestartSec=8\nKillSignal=SIGINT\nTimeoutStopSec=20\n'
                'NoNewPrivileges=yes\nPrivateTmp=yes\nProtectSystem=strict\nProtectHome=read-only\n'
                f'ReadWritePaths={self.root}\n'
                'CPUQuota=100%\nMemoryMax=768M\nTasksMax=128\nLimitCORE=0\n'
                '[Install]\nWantedBy=multi-user.target\n')
        write(self.root / 'czm-zombie.service', text)

    def run(self):
        if not (self.root / 'installed.json').exists():
            raise ValueError('Run install first')
        cfg = settings(self.root)
        self.configure()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0', cfg['port']))
        args = [str(self.binary), '-console', '-game', 'cstrike', '-ip', '0.0.0.0', '-port', str(cfg['port']),
                '-insecure', '-nomaster', '-nobreakpad', '+maxplayers', str(cfg['players']), '+map', MAP, '+exec', 'server.cfg']
        env = dict(os.environ, SteamAppId='10', SteamGameId='10')
        if self.system == 'linux':
            env['LD_LIBRARY_PATH'] = str(self.steam / 'linux32') + ':' + str(self.game)
        print(f'Сервер запускается, порт UDP {cfg["port"]}. В одной Wi-Fi сети используй IP компьютера. Остановка: Ctrl+C.', flush=True)
        child = subprocess.Popen(args, cwd=self.game, env=env)
        write(self.root / 'running.json', json.dumps({'pid': child.pid, 'executable': str(self.binary), 'time': int(time.time())}))
        try:
            return child.wait()
        except KeyboardInterrupt:
            # The same console/process group receives Ctrl+C, then allow a graceful exit.
            try:
                return child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.terminate()
                return child.wait(timeout=10)
        finally:
            (self.root / 'running.json').unlink(missing_ok=True)

    def stop(self):
        record = self.root / 'running.json'
        if not record.exists():
            print('Нет запущенного через этот комплект сервера. Для службы: sudo systemctl stop czm-zombie.')
            return
        pid = int(json.loads(record.read_text())['pid'])
        if self.system == 'linux':
            actual = pathlib.Path('/proc') / str(pid) / 'exe'
            if not actual.exists() or actual.resolve() != self.binary.resolve():
                raise ValueError('PID no longer belongs to this server; refusing to stop another process')
            os.kill(pid, signal.SIGINT)
        else:
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000 | 0x0001, False, pid)
            if not handle:
                raise ValueError('Server process is not running')
            try:
                buffer = ctypes.create_unicode_buffer(32768)
                length = wintypes.DWORD(len(buffer))
                if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                    raise OSError('Cannot verify the server process')
                if os.path.normcase(buffer.value) != os.path.normcase(str(self.binary)):
                    raise ValueError('PID belongs to another process; refusing to stop it')
                # Prefer Ctrl+C in the server window; this button is an emergency stop.
                if not kernel.TerminateProcess(handle, 0):
                    raise OSError('Cannot stop the server')
            finally:
                kernel.CloseHandle(handle)
        print('Остановка отправлена только процессу этого сервера.')

    def admin(self, identifier):
        if not re.fullmatch(r'(?:STEAM|VALVE)_[0-5]:[01]:[0-9]{1,12}', identifier):
            raise ValueError('Use the unique STEAM_x:x:number or VALVE_x:x:number shown by status')
        target = self.cs / 'addons/amxmodx/configs/users.ini'
        old = target.read_text(encoding='utf-8')
        line = f'"{identifier}" "" "abcdefghijklmnopqrstu" "ce"\n'
        if line not in old:
            write(target, old + line, private=True)
        print('Администратор добавлен. Перезапусти сервер и введи amxmodmenu в консоли игры.')


def main():
    parser = argparse.ArgumentParser(description='CZM Server: install, configure, run, stop, FastDL export and admin setup')
    parser.add_argument('action', choices=['install', 'configure', 'run', 'stop', 'export-fastdl', 'admin'])
    parser.add_argument('identifier', nargs='?')
    parser.add_argument('--yes', action='store_true', help='Install from server.ini without interactive prompts')
    args = parser.parse_args()
    kit = ServerKit()
    try:
        if args.action == 'install':
            kit.install(args.yes)
        elif args.action == 'configure':
            kit.configure()
        elif args.action == 'run':
            return kit.run()
        elif args.action == 'stop':
            kit.stop()
        elif args.action == 'export-fastdl':
            kit.export_fastdl()
        else:
            kit.admin(args.identifier or '')
        return 0
    except Exception as error:
        print('Ошибка: ' + str(error), file=sys.stderr, flush=True)
        print('Инструкция: https://counter-zombie.ru/create-server — журнал: logs/install.log', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
