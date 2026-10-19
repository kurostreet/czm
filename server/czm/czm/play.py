"""Builds for Google Play: POST /api/v1/play-builds, then `czm.cli assemble` finishes them.

GitHub Actions (play.yml, started by hand) sends an unsigned Android App Bundle of the open
part of the game. Its install-time asset pack `gamedata` carries only a placeholder: the game
data never goes to GitHub. The server puts the game data of the newest release into that pack
and signs the bundle with the upload key. Google Play then signs the APKs for the players with
its own app key (Play App Signing), so the upload key can be replaced through Play if lost.

The upload key and its password are made once by install.sh (`<data_dir>/signing/play-upload.p12`,
CZM_PLAY_KEY_PASSWORD in /etc/czm/env) and never printed.

When the Google Play service account key is there (play_publish.configured), every finished bundle
also goes to the testing tracks and to Google's review; the owner hears about it in the bot.
"""
import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import db, play_publish, service
from .assemble import GAME_DATA, SIGNATURE, BuildError, check_game_data, previous_release_apk, sha256_of
from .config import get_settings

log = logging.getLogger("czm.play")
PACK = "gamedata"                                   # android/gamedata, delivery: install-time
PACK_MANIFEST = f"{PACK}/manifest/AndroidManifest.xml"


def incoming_name(commit: str) -> str:
    return f"{commit[:12]}.play.aab"


def bundle_name(version: str) -> str:
    return f"CounterZombieMobile-{version}.aab"


def combine(bundle: Path, data_apk: Path, out: Path) -> None:
    """The bundle without its pack placeholder and old signature, plus the game data in the pack."""
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(data_apk) as data, \
            zipfile.ZipFile(out, "w", allowZip64=True) as target:
        names = set(source.namelist())
        if "BundleConfig.pb" not in names or PACK_MANIFEST not in names:
            raise BuildError("это не сборка для Google Play с пакетом gamedata")
        # the pack index (assets.pb) lists folders; the game data goes to assets/bundled
        if f"{PACK}/assets.pb" in names and b"assets/bundled" not in source.read(f"{PACK}/assets.pb"):
            raise BuildError("в пакете gamedata нет папки assets/bundled (заглушка должна лежать в ней)")
        if any(n.startswith("base/assets/") and n.endswith(tuple(GAME_DATA)) for n in names):
            raise BuildError("игровые данные не должны лежать в основном модуле")
        check_game_data(data)
        for info in source.infolist():
            upper = info.filename.upper()
            if upper.startswith("META-INF/") and (upper.endswith(SIGNATURE) or upper == "META-INF/MANIFEST.MF"):
                continue                                # jarsigner writes a fresh manifest
            if info.filename.startswith(f"{PACK}/assets/"):
                continue                                # the placeholder
            with source.open(info) as src, target.open(info, "w") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        for name in GAME_DATA:                          # assets/bundled/game-data.* → gamedata/assets/bundled/
            old = data.getinfo(name)
            info = zipfile.ZipInfo(f"{PACK}/{name}", (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.file_size = old.file_size
            with data.open(old) as src, target.open(info, "w", force_zip64=old.file_size > 0x7FFFFFFF) as dst:
                shutil.copyfileobj(src, dst, 1 << 20)


def jarsigner(*args: str) -> str:
    settings = get_settings()
    result = subprocess.run([settings.jarsigner, *args], capture_output=True, text=True, timeout=1800,
                            env={**os.environ, "JAVA_TOOL_OPTIONS": os.environ.get("JAVA_TOOL_OPTIONS", "-Xmx256m")})
    if result.returncode != 0:
        raise BuildError("jarsigner: " + (result.stderr or result.stdout).strip()[-300:])
    return result.stdout


def sign(unsigned: Path, out: Path) -> None:
    """The password goes to jarsigner through the environment (CZM_PLAY_KEY_PASSWORD), never as an argument."""
    settings = get_settings()
    if not settings.play_keystore_file.is_file() or not os.environ.get("CZM_PLAY_KEY_PASSWORD"):
        raise BuildError("нет ключа загрузки для Google Play (install.sh создаёт его)")
    jarsigner("-keystore", str(settings.play_keystore_file), "-storetype", "PKCS12",
              "-storepass:env", "CZM_PLAY_KEY_PASSWORD", "-sigalg", "SHA256withRSA", "-digestalg", "SHA-256",
              "-signedjar", str(out), str(unsigned), settings.play_key_alias)
    if "jar verified" not in jarsigner("-verify", str(out)):
        raise BuildError("подпись сборки для Google Play не проверилась")


def assemble(bundle: Path, version: str) -> Path:
    settings = get_settings()
    with db.db() as conn:
        data_apk = previous_release_apk(conn)
    if data_apk is None:
        raise BuildError("нет сборки с игровыми файлами")
    target = settings.play_dir / bundle_name(version)
    work = bundle.with_suffix(".work.aab")
    try:
        combine(bundle, data_apk, work)
        settings.play_dir.mkdir(parents=True, exist_ok=True)
        sign(work, target.with_suffix(".part"))
        target.with_suffix(".part").replace(target)
        target.chmod(0o644)
        Path(str(target) + ".sha256").write_text(f"{sha256_of(target)}  {target.name}\n")
    finally:
        work.unlink(missing_ok=True)
        target.with_suffix(".part").unlink(missing_ok=True)
    keep_newest(settings.play_dir, settings.play_keep)
    return target


def keep_newest(folder: Path, keep: int) -> None:
    bundles = sorted(folder.glob("CounterZombieMobile-*.aab"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in bundles[keep:]:
        old.unlink(missing_ok=True)
        Path(str(old) + ".sha256").unlink(missing_ok=True)


def run_pending() -> int:
    """Finishes every bundle in the incoming folder; a failed one is kept as *.failed for a look."""
    settings = get_settings()
    done = 0
    for bundle in sorted(settings.incoming_dir.glob("*.play.aab")):
        version_file = bundle.with_suffix(".version")
        notes_file = bundle.with_suffix(".notes")
        version = version_file.read_text().strip() if version_file.is_file() else bundle.name.split(".")[0]
        notes = notes_file.read_text().strip() if notes_file.is_file() else ""
        target = None
        try:
            target = assemble(bundle, version)
            log.info("Google Play bundle %s ready: %s (%d MB)", version, target.name, target.stat().st_size // 1048576)
            bundle.unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001 — the reason stays in the journal
            log.exception("Google Play bundle %s failed: %s", version, e)
            bundle.replace(bundle.with_suffix(".failed"))
        version_file.unlink(missing_ok=True)
        notes_file.unlink(missing_ok=True)
        if target is not None and play_publish.configured():
            send_to_testers(target, version, notes)
        done += 1
    return done


def send_to_testers(target: Path, version: str, notes: str) -> None:
    """Testing tracks and Google's review; the result goes to the bot either way."""
    settings = get_settings()
    tracks = ", ".join(settings.play_track_list)
    if not notes:
        with db.db() as conn:
            notes = service.release_notes_for(conn, version)
    try:
        code = play_publish.publish(target, version, notes)
        status, error = "sent", ""
    except Exception as e:  # noqa: BLE001 — the bundle stays on the server for a manual upload
        log.exception("Google Play bundle %s was not sent: %s", version, e)
        code, status, error = None, "failed", str(e) or type(e).__name__
    with db.db() as conn:
        service.add_play_publish(conn, version, code, tracks, status, error)

