"""The RuStore APK: python -m czm.cli rustore-assemble <core.apk> <version>

The core comes from the RuStore workflow (.github/workflows/rustore.yml): the open part of the
game, unsigned, package ru.kurostreet.counterzombiemobile, updated by RuStore (no installer
code, no Google Play libraries). The game data is taken from the newest release APK on this
server, as for the site builds (assemble.combine). The result is signed with the RuStore key,
made once by install.sh (<data_dir>/signing/rustore.p12, password CZM_RUSTORE_KEY_PASSWORD in
/etc/czm/env, never printed), and kept in <data_dir>/rustore, which the web server does not
serve: players get the game from RuStore.

Every RuStore update must carry the same certificate as the first one, or it will not install.
CERT_SHA256 pins it: a server that made itself a new key (a new VDS without the backup of
/var/backups/czm-signing) refuses to sign instead of releasing an update nobody can install.
"""
import os
import re
from pathlib import Path

from . import db
from .assemble import BuildError, apksigner, combine, previous_release_apk, sha256_of, signer_digest
from .config import get_settings

PACKAGE = "ru.kurostreet.counterzombiemobile"
ALIAS = "rustore"
PASSWORD_ENV = "CZM_RUSTORE_KEY_PASSWORD"
# the certificate of the first RuStore release (apksigner SHA-256 digest); empty until then
CERT_SHA256 = ""
VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-]{0,63}")
MANIFEST_MARKS = ("android.permission.REQUEST_INSTALL_PACKAGES",)
DEX_MARKS = (b"com/google/android/play/core",)


def keystore_file() -> Path:
    return get_settings().data_dir / "signing" / "rustore.p12"


def output_dir() -> Path:
    return get_settings().data_dir / "rustore"


def check_core(core: Path) -> None:
    """Only the RuStore core: the site core installs APKs itself, the Play one asks Google Play."""
    import zipfile
    try:
        with zipfile.ZipFile(core) as apk:
            names = set(apk.namelist())
            manifest = apk.read("AndroidManifest.xml")
            dex = b"".join(apk.read(n) for n in names if n.startswith("classes") and n.endswith(".dex"))
    except (OSError, KeyError, zipfile.BadZipFile):
        raise BuildError("это не APK")
    for mark in MANIFEST_MARKS:
        if mark.encode("utf-16-le") in manifest or mark.encode() in manifest:
            raise BuildError("это ядро сайта, а не RuStore: оно ставит APK само")
    for mark in DEX_MARKS:
        if mark in dex:
            raise BuildError("это ядро Google Play, а не RuStore")
    if PACKAGE.encode("utf-16-le") not in manifest and PACKAGE.encode() not in manifest:
        raise BuildError("в ядре нет пакета " + PACKAGE)


def sign(unsigned: Path, out: Path) -> None:
    """The password goes to apksigner through the environment, never as an argument."""
    if not keystore_file().is_file() or not os.environ.get(PASSWORD_ENV):
        raise BuildError("нет ключа RuStore: install.sh делает его один раз")
    apksigner("sign", "--ks", str(keystore_file()), "--ks-type", "PKCS12", "--ks-pass", "env:" + PASSWORD_ENV,
              "--ks-key-alias", ALIAS, "--v4-signing-enabled", "false", "--out", str(out), str(unsigned))
    apksigner("verify", str(out))


def assemble(core: Path, version: str) -> tuple[Path, str]:
    """Makes the RuStore APK of one core; returns the file and its certificate digest."""
    if not VERSION.fullmatch(version):
        raise BuildError("неверная версия")
    if not core.is_file():
        raise BuildError("нет файла ядра")
    check_core(core)
    with db.db() as conn:
        data_apk = previous_release_apk(conn)
    if data_apk is None:
        raise BuildError("нет сборки с игровыми файлами")
    folder = output_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"CounterZombieMobile-{version}-rustore.apk"
    unsigned, signed = target.with_suffix(".unsigned"), target.with_suffix(".signing")
    try:
        combine(core, data_apk, unsigned)
        sign(unsigned, signed)
        digest = signer_digest(signed)
        if CERT_SHA256 and digest != CERT_SHA256:
            raise BuildError("ключ RuStore не тот, что у первого релиза: обновление не встанет")
        signed.replace(target)
        target.chmod(0o644)
    finally:
        unsigned.unlink(missing_ok=True)
        signed.unlink(missing_ok=True)
        Path(str(signed) + ".idsig").unlink(missing_ok=True)
    (folder / (target.name + ".sha256")).write_text(f"{sha256_of(target)}  {target.name}\n")
    return target, digest
