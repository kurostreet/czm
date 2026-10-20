"""Turns core APKs from GitHub Actions into releases: python -m czm.cli assemble

The core APK is the open part of the game built in CI. The game data (assets/bundled/
game-data.zip and .json) never goes to GitHub: it is taken from the previous release on
this server. The result is aligned, signed with the same public debug key as before
(the signer certificate must match the previous release, or Android would refuse the
update), published at once when CZM_BUILD_AUTOPUBLISH is on, and old APK files are removed.
"""
import copy
import hashlib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

from . import db, service
from .apkpatch import make_patch
from .config import get_settings
from .game_branding import game_resources

log = logging.getLogger("czm.assemble")
GAME_DATA = ("assets/bundled/game-data.zip", "assets/bundled/game-data.json")
SIGNATURE = (".RSA", ".DSA", ".EC", ".SF", ".MF")


class BuildError(Exception):
    pass


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aligned_info(info: zipfile.ZipInfo, offset: int) -> zipfile.ZipInfo:
    """Stored entries start on a 4-byte boundary (as zipalign does), padding goes in the extra field."""
    info = copy.copy(info)
    info.extra = b""
    if info.compress_type == zipfile.ZIP_STORED:
        end = offset + 30 + len(info.filename.encode("utf-8"))
        padding = (-(end + 4)) % 4
        info.extra = struct.pack("<HH", 0xCAFE, padding) + b"\0" * padding
    return info


def game_data_source(apk: Path) -> bool:
    try:
        with zipfile.ZipFile(apk) as z:
            names = set(z.namelist())
        return all(name in names for name in GAME_DATA)
    except (OSError, zipfile.BadZipFile):
        return False


def check_game_data(source: zipfile.ZipFile) -> None:
    metadata = json.loads(source.read(GAME_DATA[1]))
    digest = hashlib.sha256()
    with source.open(GAME_DATA[0]) as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != metadata.get("sha256"):
        raise BuildError("игровые файлы предыдущей сборки повреждены")


def combine(core: Path, data_apk: Path, out: Path) -> None:
    """Core entries without the old signature, then the game data as stored, aligned entries."""
    with zipfile.ZipFile(core) as source, zipfile.ZipFile(data_apk) as data, zipfile.ZipFile(out, "w") as target, \
            game_resources(data, source, out.parent) as resources:
        check_game_data(data)
        for info in source.infolist():
            upper = info.filename.upper()
            if upper.startswith("META-INF/") and upper.endswith(SIGNATURE):
                continue
            if info.filename in GAME_DATA:
                continue
            info = aligned_info(info, target.fp.tell())
            with source.open(info.filename) as src, target.open(info, "w") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        for name, path, size in resources:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.file_size = size
            info = aligned_info(info, target.fp.tell())
            with (path.open("rb") if path else data.open(name)) as src, target.open(info, "w", force_zip64=size > 0x7FFFFFFF) as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    with zipfile.ZipFile(out) as archive, out.open("rb") as raw:
        for info in archive.infolist():
            if info.compress_type == zipfile.ZIP_STORED:
                raw.seek(info.header_offset + 26)
                name_len, extra_len = struct.unpack("<HH", raw.read(4))
                if (info.header_offset + 30 + name_len + extra_len) % 4:
                    raise BuildError(f"не выровнено: {info.filename}")


def apksigner(*args: str) -> str:
    settings = get_settings()
    result = subprocess.run([settings.apksigner, *args], capture_output=True, text=True, timeout=900,
                            env={**os.environ, "JAVA_TOOL_OPTIONS": os.environ.get("JAVA_TOOL_OPTIONS", "-Xmx256m")})
    if result.returncode != 0:
        raise BuildError("apksigner: " + (result.stderr or result.stdout).strip()[-300:])
    return result.stdout


def signer_digest(apk: Path) -> str:
    out = apksigner("verify", "--print-certs", str(apk))
    found = re.search(r"Signer #1 certificate SHA-256 digest:\s*([0-9a-f]+)", out)
    if not found:
        raise BuildError("не видно сертификата подписи")
    return found.group(1)


def sign(unsigned: Path, out: Path) -> None:
    keystore = get_settings().keystore_file
    if not keystore.is_file():
        raise BuildError(f"нет ключа подписи {keystore}")
    apksigner("sign", "--ks", str(keystore), "--ks-pass", "pass:android", "--key-pass", "pass:android",
              "--ks-key-alias", "androiddebugkey", "--out", str(out), str(unsigned))
    apksigner("verify", str(out))


def previous_release_apk(conn) -> Path | None:
    """The newest release whose APK is still here and carries the game data."""
    folder = get_settings().apk_dir
    for row in conn.execute("SELECT file FROM releases ORDER BY id DESC"):
        path = folder / row["file"]
        if path.is_file() and game_data_source(path):
            return path
    return None


def remove_old_files(conn) -> None:
    """Keeps the newest CZM_BUILD_KEEP release files and the published one players download."""
    settings = get_settings()
    keep = {row["file"] for row in conn.execute("SELECT file FROM releases ORDER BY id DESC LIMIT ?", (settings.build_keep,))}
    published = service.latest_release(conn)
    if published:
        keep.add(published["url"].rsplit("/", 1)[-1])
    development = service.latest_release(conn, channel="development")
    if development:
        keep.add(development["url"].rsplit("/", 1)[-1])
    for row in conn.execute("SELECT file FROM releases"):
        if row["file"] not in keep:
            (settings.apk_dir / row["file"]).unlink(missing_ok=True)
    for row in list(conn.execute("SELECT p.file, p.release_id, r.file AS apk FROM release_patches p JOIN releases r ON r.id = p.release_id")):
        if row["apk"] not in keep:
            (settings.apk_dir / row["file"]).unlink(missing_ok=True)
            conn.execute("DELETE FROM release_patches WHERE release_id = ?", (row["release_id"],))


def release_patches(target: Path, digest: str, bases: list[dict]) -> list[dict]:
    """A broken/missing base must never stop the full APK release."""
    patches = []
    for base in bases:
        source = get_settings().apk_dir / base["file"]
        patch = target.with_name(f"czm-{digest[:16]}-from-{base['sha256'][:16]}.czmpatch")
        try:
            info = make_patch(source, target, patch, base_sha256=base["sha256"], target_sha256=digest)
            if info:
                patches.append({**info, "base_code": base["code"]})
                log.info("patch from %s: %d bytes, reused %d bytes", base["version"], info["size"], info["reused"])
        except Exception:
            log.exception("patch from %s unavailable; full APK remains available", base["version"])
    return patches


def assemble_build(build) -> int:
    """Makes the release of one received build, returns the release id."""
    settings = get_settings()
    core = settings.incoming_dir / build["file"]
    if not core.is_file():
        raise BuildError("файл сборки пропал")
    name = f"CounterZombieMobile-{build['version']}.apk"
    with db.db() as conn:
        # the same version is already here (the workflow ran again): it is not rebuilt
        same = conn.execute("SELECT id, published FROM releases WHERE file = ? ORDER BY id DESC LIMIT 1", (name,)).fetchone()
        if same and (settings.apk_dir / name).is_file():
            if settings.build_autopublish and not same["published"]:
                service.publish_release(conn, same["id"], build["notes"])
            return same["id"]
        data_apk = previous_release_apk(conn)
        bases = [dict(row) for row in conn.execute("SELECT * FROM releases WHERE code < ? ORDER BY code DESC", (build["code"],))
                 if (settings.apk_dir / row["file"]).is_file()][:3]
    if data_apk is None:
        raise BuildError("нет предыдущей сборки с игровыми файлами")

    work = settings.incoming_dir / f"{build['commit_sha'][:12]}.work"
    unsigned, signed = work.with_suffix(".unsigned.apk"), work.with_suffix(".signed.apk")
    try:
        combine(core, data_apk, unsigned)
        sign(unsigned, signed)
        if signer_digest(signed) != signer_digest(data_apk):
            raise BuildError("ключ подписи не совпадает с прошлой сборкой, обновление не встанет")
        target = settings.apk_dir / name
        settings.apk_dir.mkdir(parents=True, exist_ok=True)
        digest, size = sha256_of(signed), signed.stat().st_size
        signed.replace(target)
        target.chmod(0o644)
    finally:
        unsigned.unlink(missing_ok=True)
        signed.unlink(missing_ok=True)
        Path(str(signed) + ".idsig").unlink(missing_ok=True)   # v4 signature next to the APK, not needed

    # Verification reads APK ranges into a hash; no extra 400 MB output per patch.
    patches = release_patches(target, digest, bases)
    with db.db() as conn:
        conn.execute("DELETE FROM releases WHERE file = ? AND published IS NULL", (name,))
        release_id = conn.execute(
            "INSERT INTO releases (version, code, file, size, sha256, created, auto, channel) VALUES (?, ?, ?, ?, ?, ?, 1, 'development')",
            (build["version"], build["code"], name, size, digest, db.now()),
        ).lastrowid
        for patch in patches:
            conn.execute("INSERT INTO release_patches (release_id, base_code, base_sha256, file, size, sha256) VALUES (?, ?, ?, ?, ?, ?)",
                         (release_id, patch["base_code"], patch["base_sha256"], patch["file"], patch["size"], patch["sha256"]))
        if settings.build_autopublish:
            notes = build["notes"].strip()
            last = service.latest_release(conn, channel="development")
            if last and notes == last["notes"].strip():
                notes = ""        # the text of the previous update was not changed: a general line
            service.publish_release(conn, release_id, notes)
        remove_old_files(conn)
    return release_id


def run_pending() -> int:
    """Assembles every received build; returns how many."""
    db.init()
    with db.db() as conn:
        builds = [dict(row) for row in service.pending_builds(conn)]
    for build in builds:
        log.info("assembling %s (%s)", build["version"], build["commit_sha"][:7])
        release_id, error = None, ""
        try:
            release_id = assemble_build(build)
        except BuildError as e:
            error = str(e)
        except Exception as e:  # noqa: BLE001 — the owner gets the reason in the bot
            log.exception("build %s failed", build["id"])
            error = f"{type(e).__name__}: {e}"
        finally:
            (get_settings().incoming_dir / build["file"]).unlink(missing_ok=True)
        with db.db() as conn:
            service.finish_build(conn, build["id"], "failed" if error else "done", error, release_id)
        log.info("build %s: %s", build["version"], error or f"release {release_id}")
    return len(builds)
