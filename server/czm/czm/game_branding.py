"""Replace legacy UI artwork inside private game data before signing a release.

Gameplay assets and font lumps are preserved. This is an interface-artwork
replacement, not a conversion of the game data into an independent asset set.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
from contextlib import contextmanager
import zipfile
import PIL
from PIL import Image

from .ui_art import ART_REVISION, make_entries

OVERLAY = "gfx/czm/legacy-ui.json"
ART = {"background": "gfx/czm/loading_3.png", "title": "gfx/czm/title.png", "logo": "logos/czm_logo.png"}
DATA = "assets/bundled/game-data.zip"
META = "assets/bundled/game-data.json"
WAD_ENTRY = struct.Struct("<iiiBBBB16s")


def replace_wad_logos(data: bytes, replacements: dict[str, bytes], game: str) -> bytes:
    """Keep every non-logo lump byte-for-byte, including console and UI fonts."""
    if len(data) < 12:
        raise ValueError("invalid UI WAD header")
    magic, count, directory = struct.unpack_from("<4sii", data)
    if magic not in (b"WAD2", b"WAD3") or count < 0 or directory < 12 or directory + count * WAD_ENTRY.size > len(data):
        raise ValueError("invalid UI WAD directory")
    body, entries = bytearray(), bytearray()
    for i in range(count):
        offset, disk_size, size, kind, compression, pad1, pad2, raw_name = WAD_ENTRY.unpack_from(data, directory + i * WAD_ENTRY.size)
        if offset < 12 or disk_size < 0 or offset + disk_size > len(data):
            raise ValueError("invalid UI WAD lump")
        name = raw_name.split(b"\0", 1)[0].decode("ascii").lower()
        replacement = replacements.get(f"{game}/gfx/{name}.lmp") if name in ("lambda", "lambda64", "lambda32") else None
        payload = replacement if replacement is not None else data[offset:offset + disk_size]
        entries.extend(WAD_ENTRY.pack(12 + len(body), len(payload), len(payload) if replacement is not None else size,
                                      66 if replacement is not None else kind, 0 if replacement is not None else compression,
                                      pad1, pad2, raw_name))
        body.extend(payload)
    return struct.pack("<4sii", magic, count, 12 + len(body)) + body + entries


def _overlay(core: zipfile.ZipFile, prefix: str) -> tuple[str, dict[str, bytes]] | None:
    path = prefix + OVERLAY
    if path not in core.namelist():
        return None  # compatible with older, already-built cores and rollback tools
    marker = json.loads(core.read(path))
    if marker != {"format": 1, "art_revision": ART_REVISION}:
        raise ValueError("unsupported UI artwork revision")
    digest = hashlib.sha256()
    digest.update(Path(__file__).with_name("ui_art.py").read_bytes())
    digest.update(PIL.__version__.encode())
    artwork = {}
    for key, name in ART.items():
        info = core.getinfo(prefix + name)
        if info.file_size > 16 * 1024 * 1024:
            raise ValueError("UI source image is too large")
        artwork[key] = core.read(info)
        digest.update(name.encode() + b"\0" + hashlib.sha256(artwork[key]).digest())
    return digest.hexdigest(), artwork


@contextmanager
def game_resources(data: zipfile.ZipFile, core: zipfile.ZipFile, folder: Path, prefix="assets/"):
    """Yield game-data entries as (APK path, file object or path, byte count)."""
    overlay = _overlay(core, prefix)
    if overlay is None:
        yield [(name, None, data.getinfo(name).file_size) for name in (DATA, META)]
        return
    brand, artwork = overlay
    old_meta = json.loads(data.read(META))
    if old_meta.get("ui_branding") == brand:
        yield [(name, None, data.getinfo(name).file_size) for name in (DATA, META)]
        return

    images = {}
    for key, contents in artwork.items():
        with Image.open(io.BytesIO(contents)) as image:
            images[key] = image.convert("RGB" if key == "background" else "RGBA")
    replacements = {name.lower(): contents for name, contents in make_entries(**images).items()}

    with tempfile.TemporaryDirectory(prefix="czm-ui-", dir=folder) as temp:
        pack = Path(temp) / "game-data.zip"
        inventory = {}
        with data.open(DATA) as raw, zipfile.ZipFile(raw) as old, zipfile.ZipFile(pack, "w", zipfile.ZIP_DEFLATED) as new:
            seen = set()
            for info in old.infolist():
                key = info.filename.lower()
                if info.is_dir():
                    continue
                if key in seen:
                    raise ValueError("duplicate game resource")
                seen.add(key)
                if key in replacements:
                    continue
                contents = None
                if key in ("valve/gfx.wad", "cstrike/gfx.wad"):
                    contents = replace_wad_logos(old.read(info), replacements, key.split("/")[0])
                elif key in ("valve/liblist.gam", "cstrike/liblist.gam"):
                    contents = re.sub(rb'(?mi)^game\s+"[^"\r\n]*"', b'game "Counter Zombie Mobile"', old.read(info))
                entry = zipfile.ZipInfo(info.filename, (2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                with new.open(entry, "w") as dst:
                    if contents is not None:
                        dst.write(contents)
                    else:
                        with old.open(info) as src:
                            shutil.copyfileobj(src, dst, 1 << 20)
                inventory[info.filename] = len(contents) if contents is not None else info.file_size
            for name, contents in sorted(replacements.items()):
                entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                new.writestr(entry, contents)
                inventory[name] = len(contents)
        with pack.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        required = old_meta.get("required", [])
        for entry in required:
            key = entry["path"]
            if key not in inventory:
                raise ValueError("required game resource is missing")
            entry["bytes"] = inventory[key]
        metadata = Path(temp) / "game-data.json"
        metadata.write_text(json.dumps({**old_meta, "sha256": digest, "files": len(inventory),
                                        "unpacked_bytes": sum(inventory.values()), "required": required,
                                        "ui_branding": brand}, indent=2) + "\n")
        yield [(DATA, pack, pack.stat().st_size), (META, metadata, metadata.stat().st_size)]
