#!/usr/bin/env python3
"""Create deterministic resource ZIPs and integrity metadata using the standard library."""
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

def make_pack(output, entries, required=()):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + "." + str(os.getpid()) + ".tmp")
    count, size = 0, 0
    inventory = {}
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, content in sorted(entries.items()):
                path = Path(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                    raise ValueError("Unsafe resource path: " + name)
                data = content() if callable(content) else content
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
                count += 1
                size += len(data)
                inventory[name] = len(data)
        digest = hashlib.file_digest(temporary.open("rb"), "sha256").hexdigest()
        os.replace(temporary, output)
        metadata = {"format": 1, "sha256": digest, "files": count, "unpacked_bytes": size,
                    "required": [{"path": name, "bytes": inventory[name]} for name in required]}
        output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(output.name, count, "files,", size, "bytes,", digest)
    finally:
        temporary.unlink(missing_ok=True)

def from_directories(output, directories, overrides=None):
    entries = {}
    for directory in directories:
        root = Path(directory)
        if not root.is_dir():
            raise FileNotFoundError(root)
        for path in root.rglob("*"):
            if path.is_file() and ".git" not in path.parts and path.name not in {".gitignore", "README.md", "LICENSE"}:
                if path.is_symlink():
                    raise ValueError("Symlink in resource pack: " + str(path))
                entries[path.relative_to(root).as_posix()] = path.read_bytes
    for name, path in (overrides or {}).items():
        entries[name] = Path(path).read_bytes
    make_pack(output, entries)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: create_resource_pack.py OUTPUT.zip DIRECTORY ...")
    from_directories(sys.argv[1], sys.argv[2:])
