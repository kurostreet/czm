"""Build immutable, data-only resource revisions from an operator-selected game folder.

python -m czm.resource_publish publish --source /srv/.../cstrike --pack survival --revision r1
python -m czm.resource_publish activate --slot survival --pack survival --revision r1
Publishing never activates a server and never writes into the source game folder.
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import struct
import tempfile
import zipfile
from pathlib import Path

from . import server_resources as resources


def allowed(path: str) -> bool:
    resources.asset_path(path)
    parts = path.split("/"); suffix = Path(path).suffix.lower(); top = parts[0].lower()
    return ((len(parts) == 1 and suffix == ".wad") or
            (len(parts) > 1 and ((top == "maps" and suffix == ".bsp") or
             (top == "models" and suffix == ".mdl") or (top == "sprites" and suffix == ".spr") or
             (top == "sound" and suffix in (".wav", ".mp3", ".ogg")) or
             (top in ("gfx", "textures") and suffix in (".tga", ".bmp", ".png")))))


def validate_format(path: str, head: bytes, size: int) -> None:
    """Check the actual engine format, not an extension renamed onto executable data."""
    suffix = Path(path).suffix.lower(); ok = False
    if suffix == ".bsp" and len(head) >= 124 and struct.unpack_from("<I", head)[0] == 30:
        ok = all(offset <= size and length <= size - offset for offset, length in
                 (struct.unpack_from("<II", head, 4 + i * 8) for i in range(15)))
    elif suffix == ".mdl":
        ok = len(head) >= 76 and ((head[:4] == b"IDST" and size >= 244) or (head[:4] == b"IDSQ" and size >= 76)) and struct.unpack_from("<I", head, 4)[0] == 10 and struct.unpack_from("<I", head, 72)[0] == size
    elif suffix == ".spr":
        ok = size >= 40 and head[:4] == b"IDSP" and struct.unpack_from("<I", head, 4)[0] == 2
    elif suffix == ".wad" and size >= 12 and head[:4] in (b"WAD2", b"WAD3"):
        count, offset = struct.unpack_from("<II", head, 4)
        ok = count <= 65536 and offset <= size and count * 32 <= size - offset
    elif suffix == ".wav":
        ok = size >= 44 and head[:4] == b"RIFF" and head[8:12] == b"WAVE" and struct.unpack_from("<I", head, 4)[0] + 8 == size
    elif suffix == ".mp3":
        ok = size >= 10 and (head[:3] == b"ID3" and len(head) >= 10 and all(v < 128 for v in head[6:10]) or head[0] == 0xff and head[1] & 0xe0 == 0xe0 and head[1] & 0x06 != 0)
    elif suffix == ".ogg":
        ok = size >= 27 and head[:4] == b"OggS" and head[4] == 0
    elif suffix == ".png":
        ok = size >= 33 and head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR" and all(0 < v <= 16384 for v in struct.unpack_from(">II", head, 16))
    elif suffix == ".bmp":
        ok = size >= 54 and head[:2] == b"BM" and struct.unpack_from("<I", head, 2)[0] == size
    elif suffix == ".tga" and size >= 18:
        width, height = struct.unpack_from("<HH", head, 12)
        ok = head[1] in (0, 1) and head[2] in (1, 2, 3, 9, 10, 11) and 0 < width <= 16384 and 0 < height <= 16384 and head[16] in (8, 16, 24, 32)
    if not ok:
        raise ValueError(f"invalid {suffix} format: {path}")


def _source_files(source: Path):
    if source.is_symlink() or not source.is_dir():
        raise ValueError("source must be a real game directory")
    # Only these folders and root WADs are considered. Configs, plugins and addons
    # never enter the output even when an operator points at a whole game folder.
    for item in sorted(source.iterdir(), key=lambda p: p.name):
        if item.name.lower() in ("maps", "models", "sprites", "sound", "gfx", "textures"):
            if item.is_symlink():
                raise ValueError("linked source directory")
            if not item.is_dir():
                continue
            for directory, dirs, files in os.walk(item, followlinks=False):
                for name in dirs:
                    if (Path(directory) / name).is_symlink():
                        raise ValueError("linked source directory")
                for name in sorted(files):
                    candidate = Path(directory) / name
                    relative = candidate.relative_to(source).as_posix()
                    # A bad filename with an otherwise allowed type must be reported.
                    if Path(relative).suffix.lower() in (".bsp", ".mdl", ".spr", ".wav", ".mp3", ".ogg", ".tga", ".bmp", ".png") and allowed(relative):
                        yield relative
        elif item.suffix.lower() == ".wad" and allowed(item.name):
            yield item.name


def _open_source(source: Path, relative: str):
    """O_NOFOLLOW for every component closes symlink replacement during import."""
    fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = relative.split("/")
        for component in parts[:-1]:
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = following
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        return os.fdopen(file_fd, "rb")
    finally:
        os.close(fd)


def publish(source: Path, pack_id: str, revision: str, resource_root: Path | None = None) -> dict:
    resources.identifier(pack_id); resources.identifier(revision)
    source = Path(source).absolute(); base = Path(resource_root or resources.root()).absolute()
    if source == base or source in base.parents or base in source.parents:
        raise ValueError("source and resource store must be separate")
    for parent in (base, base / "staging", base / "published", base / "published" / pack_id):
        if parent.is_symlink():
            raise ValueError("linked resource store")
        parent.mkdir(parents=True, exist_ok=True)
    destination = base / "published" / pack_id / revision
    if destination.exists() or destination.is_symlink():
        raise ValueError("revision already exists; publish a new revision")
    temporary = Path(tempfile.mkdtemp(prefix=f"{pack_id}-{revision}-", dir=base / "staging"))
    try:
        (temporary / "files").mkdir()
        records = []; seen = set(); total = 0
        for relative in sorted(_source_files(source)):
            folded = relative.casefold()
            if folded in seen:
                raise ValueError("case-insensitive duplicate asset")
            seen.add(folded)
            if len(seen) > resources.MAX_FILES:
                raise ValueError("too many assets")
            with _open_source(source, relative) as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= resources.MAX_FILE_BYTES:
                    raise ValueError(f"invalid asset size/type: {relative}")
                total += before.st_size
                if total > resources.MAX_TOTAL_BYTES:
                    raise ValueError("resource set is too large")
                head = stream.read(256); validate_format(relative, head, before.st_size); stream.seek(0)
                scratch = temporary / "copy.part"; h = hashlib.sha256(); copied = 0
                with scratch.open("wb") as out:
                    while chunk := stream.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > before.st_size:
                            raise ValueError("source changed during import")
                        h.update(chunk); out.write(chunk)
                    out.flush(); os.fsync(out.fileno())
                after = os.fstat(stream.fileno())
                if copied != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError("source changed during import")
                sha = h.hexdigest(); blob = temporary / "files" / sha
                if blob.exists():
                    scratch.unlink()
                else:
                    scratch.rename(blob)
                records.append({"path": relative, "size": copied, "sha256": sha, "url": resources.url(pack_id, revision, "files/" + sha)})
        if not records:
            raise ValueError("no supported client assets; empty packs cannot be published")
        archive = temporary / "bundle.zip"
        with zipfile.ZipFile(archive, "w", allowZip64=True, compression=zipfile.ZIP_DEFLATED, compresslevel=3) as bundle:
            for item in records:
                entry = zipfile.ZipInfo(item["path"], date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3; entry.external_attr = (stat.S_IFREG | 0o644) << 16
                entry.compress_type = zipfile.ZIP_STORED if Path(item["path"]).suffix.lower() in (".mp3", ".ogg", ".png") else zipfile.ZIP_DEFLATED
                with (temporary / "files" / item["sha256"]).open("rb") as inp, bundle.open(entry, "w", force_zip64=True) as out:
                    shutil.copyfileobj(inp, out, 1024 * 1024)
        if archive.stat().st_size > resources.MAX_TOTAL_BYTES:
            raise ValueError("archive is too large")
        manifest = {"schema": 1, "pack_id": pack_id, "revision": revision, "total_bytes": total, "files": records,
                    "archive": {"url": resources.url(pack_id, revision, "bundle.zip"), "size": archive.stat().st_size, "sha256": resources.digest(archive)}}
        encoded = (json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(encoded) > resources.MAX_MANIFEST_BYTES:
            raise ValueError("manifest is too large")
        (temporary / "manifest.json").write_bytes(encoded)
        # fsync files before the directory rename; no half-published revision exists.
        for item in (archive, temporary / "manifest.json"):
            with item.open("rb") as f:
                os.fsync(f.fileno())
        os.rename(temporary, destination)
        parent_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return {"pack_id": pack_id, "revision": revision, "files": len(records), "total_bytes": total,
                "archive_bytes": archive.stat().st_size if archive.exists() else (destination / "bundle.zip").stat().st_size,
                "manifest_sha256": hashlib.sha256(encoded).hexdigest(), "path": str(destination)}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def verify_revision(pack_id: str, revision: str, resource_root: Path) -> dict:
    manifest_file = resources.published_file(pack_id, revision, "manifest.json", resource_root)
    if not 0 < manifest_file.stat().st_size <= resources.MAX_MANIFEST_BYTES:
        raise ValueError("invalid manifest size")
    raw = manifest_file.read_bytes()
    if not 0 < len(raw) <= resources.MAX_MANIFEST_BYTES:
        raise ValueError("invalid manifest size")
    manifest = json.loads(raw)
    if type(manifest.get("schema")) is not int or manifest["schema"] != 1 or manifest.get("pack_id") != pack_id or manifest.get("revision") != revision:
        raise ValueError("manifest identity mismatch")
    records = manifest.get("files")
    if not isinstance(records, list) or not 0 < len(records) <= resources.MAX_FILES:
        raise ValueError("invalid file inventory")
    seen = set(); total = 0
    for item in records:
        path = resources.asset_path(item["path"])
        if not allowed(path) or path.casefold() in seen:
            raise ValueError("invalid or duplicate asset path")
        seen.add(path.casefold())
        if not resources.HASH.fullmatch(item["sha256"]) or item.get("url") != resources.url(pack_id, revision, "files/" + item["sha256"]):
            raise ValueError("invalid file reference")
        file = resources.published_file(pack_id, revision, "files/" + item["sha256"], resource_root)
        size = file.stat().st_size
        if type(item["size"]) is not int or not 0 < size == item["size"] <= resources.MAX_FILE_BYTES:
            raise ValueError("invalid file size")
        total += size
        if total > resources.MAX_TOTAL_BYTES or resources.digest(file) != item["sha256"]:
            raise ValueError("file integrity failure")
        with file.open("rb") as stream:
            validate_format(path, stream.read(256), size)
    if type(manifest.get("total_bytes")) is not int or manifest["total_bytes"] != total:
        raise ValueError("invalid total size")
    archive_info = manifest["archive"]; archive = resources.published_file(pack_id, revision, "bundle.zip", resource_root)
    if type(archive_info.get("size")) is not int or not 0 < archive_info["size"] <= resources.MAX_TOTAL_BYTES or archive_info.get("url") != resources.url(pack_id, revision, "bundle.zip") or archive_info["size"] != archive.stat().st_size or archive_info["sha256"] != resources.digest(archive):
        raise ValueError("archive integrity failure")
    # The ZIP must contain exactly the manifest's regular, bounded entries.
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) != len(records):
            raise ValueError("archive inventory mismatch")
        for entry, item in zip(entries, records):
            if entry.filename != item["path"] or entry.file_size != item["size"] or entry.flag_bits & 1 or entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("unsafe archive entry")
            h = hashlib.sha256()
            with bundle.open(entry) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest() != item["sha256"]:
                raise ValueError("archive entry integrity failure")
    return {"pack_id": pack_id, "revision": revision, "files": len(records), "total_bytes": total,
            "archive_bytes": archive.stat().st_size, "manifest_sha256": hashlib.sha256(raw).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("publish"); build.add_argument("--source", required=True, type=Path)
    build.add_argument("--pack", required=True); build.add_argument("--revision", required=True)
    for name in ("verify", "activate"):
        command = commands.add_parser(name); command.add_argument("--pack", required=True); command.add_argument("--revision", required=True)
        if name == "activate":
            command.add_argument("--slot", required=True, choices=("survival", "escape"))
    commands.add_parser("disable").add_argument("--slot", required=True, choices=("survival", "escape"))
    args = parser.parse_args()
    if args.command == "publish":
        result = publish(args.source, args.pack, args.revision)
    elif args.command == "verify":
        result = verify_revision(args.pack, args.revision, resources.root())
    else:
        from .db import db
        with db() as conn:
            result = resources.activate(conn, args.slot, args.pack, args.revision) if args.command == "activate" else resources.disable(conn, args.slot)
    print(json.dumps(result or {"resources_enabled": False}, sort_keys=True))


if __name__ == "__main__":
    main()
