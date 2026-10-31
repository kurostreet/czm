#!/usr/bin/env python3
"""Build reproducible public starter archives; never package an installed server."""
import argparse
import gzip
import io
import json
import pathlib
import stat
import tarfile
import zipfile
from installer import ROOT, download, sha256


def files(system, cache):
    common = ['installer.py', 'packages.json', 'server.ini', 'README_RU.txt', 'THIRD_PARTY.txt']
    content = {name: ((ROOT / name).read_bytes(), 0o644) for name in common}
    if system == 'windows':
        for filename, action in [('1-INSTALL.cmd', 'install'), ('2-START.cmd', 'run'), ('4-STOP.cmd', 'stop')]:
            text = ('@echo off\nsetlocal\nchcp 65001 >nul\ncd /d "%~dp0"\nset PYTHONUTF8=1\n'
                    f'"%~dp0runtime\\python.exe" "%~dp0installer.py" {action}\npause\n')
            content[filename] = (text.replace('\n', '\r\n').encode(), 0o644)
        text = ('@echo off\nsetlocal\nchcp 65001 >nul\ncd /d "%~dp0"\nset PYTHONUTF8=1\n'
                'start /wait "" notepad.exe "%~dp0server.ini"\n'
                '"%~dp0runtime\\python.exe" "%~dp0installer.py" configure\npause\n')
        content['3-SETTINGS.cmd'] = (text.replace('\n', '\r\n').encode(), 0o644)
        manifest = json.loads((ROOT / 'packages.json').read_text())
        archive = download(manifest['packages']['python-windows'], cache, 'python-windows.zip')
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                if not member.is_dir():
                    from installer import safe_path
                    safe_path(pathlib.Path('/runtime'), member.filename)
                    content['runtime/' + member.filename] = (package.read(member), 0o644)
    else:
        for filename, action in [('install.sh', 'install'), ('start.sh', 'run'), ('stop.sh', 'stop'), ('configure.sh', 'configure')]:
            content[filename] = (('#!/usr/bin/env bash\nset -euo pipefail\n'
                                 'cd -- "$(dirname -- "${BASH_SOURCE[0]}")"\n'
                                 f'exec python3 installer.py {action} "$@"\n').encode(), 0o755)
    return content


def build(system, destination, cache):
    version = json.loads((ROOT / 'packages.json').read_text())['version']
    folder = 'CZM-Server-' + system.title()
    content = files(system, cache)
    destination.mkdir(parents=True, exist_ok=True)
    suffix = '.zip' if system == 'windows' else '.tar.gz'
    output = destination / f'{folder}-v{version}{suffix}'
    if system == 'windows':
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for name, (body, mode) in sorted(content.items()):
                member = zipfile.ZipInfo(folder + '/' + name, (2026, 10, 31, 0, 0, 0))
                member.create_system = 3
                member.external_attr = (stat.S_IFREG | mode) << 16
                member.compress_type = zipfile.ZIP_DEFLATED
                package.writestr(member, body)
    else:
        with output.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as package:
                for name, (body, mode) in sorted(content.items()):
                    member = tarfile.TarInfo(folder + '/' + name)
                    member.size, member.mode = len(body), mode
                    member.uid = member.gid = member.mtime = 0
                    package.addfile(member, io.BytesIO(body))
    receipt = {'version': version, 'platform': system, 'file': output.name,
               'bytes': output.stat().st_size, 'sha256': sha256(output), 'files': len(content)}
    (destination / (system + '-receipt.json')).write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt), flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=['linux', 'windows'], required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--cache', type=pathlib.Path, required=True)
    args = parser.parse_args()
    build(args.platform, args.output, args.cache)
