"""Files for one configured game root. All opens stay below directory descriptors."""
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import threading
import time


class PanelError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


TEXT_EXT = {".cfg", ".ini", ".txt", ".json", ".sma", ".inc", ".res", ".lua", ".js", ".yaml", ".yml", ".xml", ".conf", ".csv"}
RESOURCES = {"maps": {".bsp", ".res", ".txt"}, "models": {".mdl"},
             "sound": {".wav", ".mp3"}, "sprites": {".spr"},
             "gfx": {".tga", ".bmp", ".png"}, "overviews": {".txt", ".bmp", ".tga"}}
ROOT_FILES = {"server.cfg", "custom.cfg", "mapcycle.txt", "motd.txt", "banned.cfg", "listip.cfg"}
PROTECTED = {"rcon_password", "rcon_users", "sv_rcon_condebug", "sv_downloadurl"}
MAX_TEXT = 1024 * 1024
MAX_UPLOAD = 64 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(line):
    return re.split(r"\s+", line.strip(), maxsplit=1)[0].lower() if line.strip() else ""


def decode(data):
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1251"), "cp1251"


class FileStore:
    def __init__(self, root, state, fastdl):
        self.root, self.state, self.fastdl = Path(root), Path(state), Path(fastdl)
        self.backups = self.state / "backups"
        self.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.size_cache = {}

    def folder_size(self, parts):
        key = "/".join(parts)
        cached = self.size_cache.get(key)
        if cached and time.monotonic() - cached[0] < 15:
            return cached[1], cached[2]
        count = 0
        complete = True

        def visit(fd, depth=0):
            nonlocal count, complete
            total = 0
            if depth > 64:
                complete = False
                return 0
            for name in os.listdir(fd):
                count += 1
                if count > 100000:
                    complete = False
                    break
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                        total += info.st_size
                    elif stat.S_ISDIR(info.st_mode):
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        try:
                            total += visit(child, depth + 1)
                        finally:
                            os.close(child)
                except OSError:
                    complete = False
            return total

        with self.directory(parts) as fd:
            size = visit(fd)
        self.size_cache[key] = (time.monotonic(), size, complete)
        return size, complete

    def parts(self, value, directory=False):
        if not isinstance(value, str) or len(value) > 512 or "\\" in value or "\x00" in value:
            raise PanelError("path")
        if not value:
            if directory:
                return ()
            raise PanelError("path")
        if value.startswith("/") or any(p in {"", ".", ".."} or p.startswith(".") for p in value.split("/")):
            raise PanelError("path")
        parts = tuple(value.split("/"))
        if any(len(p.encode()) > 200 or any(ord(c) < 32 for c in p) for p in parts):
            raise PanelError("path")
        if not self.allowed(parts, directory):
            raise PanelError("protected", 403)
        return parts

    @staticmethod
    def allowed(parts, directory=False):
        if not parts:
            return directory
        suffix = PurePosixPath(parts[-1]).suffix.lower()
        if parts[0] in RESOURCES:
            return directory or (len(parts) > 1 and suffix in RESOURCES[parts[0]])
        if parts[0] == "addons":
            bases = (("addons", "amxmodx", "configs"), ("addons", "amxmodx", "plugins"),
                     ("addons", "amxmodx", "scripting"))
            if directory and any(tuple(parts) == b[:len(parts)] for b in bases):
                return True
            for base in bases:
                if tuple(parts[:3]) == base:
                    if directory:
                        return True
                    exts = {".amxx"} if base[-1] == "plugins" else TEXT_EXT
                    return len(parts) > 3 and suffix in exts
        return len(parts) == 1 and not directory and (parts[0] in ROOT_FILES or suffix == ".wad")

    @contextlib.contextmanager
    def directory(self, parts, root=None, create=False):
        fd = os.open(root or self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, 0o755, dir_fd=fd)
                    except FileExistsError:
                        pass
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                if create:
                    # FastDL is read by Caddy outside the game service's private umask.
                    os.fchmod(nxt, 0o755)
                os.close(fd)
                fd = nxt
            yield fd
        except (FileNotFoundError, NotADirectoryError):
            raise PanelError("missing", 404) from None
        except OSError:
            raise PanelError("path", 400) from None
        finally:
            os.close(fd)

    def read_bytes(self, parts, limit=MAX_TEXT):
        with self.directory(parts[:-1]) as parent:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise PanelError("path")
                if info.st_size > limit:
                    raise PanelError("large", 413)
                with os.fdopen(fd, "rb", closefd=False) as file:
                    data = file.read(limit + 1)
                if len(data) > limit:
                    raise PanelError("large", 413)
                return data
            finally:
                os.close(fd)

    @contextlib.contextmanager
    def open_file(self, path):
        parts = self.parts(path)
        with self.directory(parts[:-1]) as parent:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_UPLOAD:
                    raise PanelError("path")
                with os.fdopen(fd, "rb", closefd=False) as file:
                    yield file
            finally:
                os.close(fd)

    def list(self, path=""):
        parts = self.parts(path, True)
        entries = []
        with self.directory(parts) as fd:
            for name in os.listdir(fd):
                if name.startswith("."):
                    continue
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                isdir = stat.S_ISDIR(info.st_mode)
                candidate = parts + (name,)
                if not (isdir or stat.S_ISREG(info.st_mode)) or info.st_nlink > 1 and not isdir:
                    continue
                if not self.allowed(candidate, isdir):
                    continue
                size, complete = self.folder_size(candidate) if isdir else (info.st_size, True)
                entries.append({"name": name, "path": "/".join(candidate), "directory": isdir,
                                "size": size, "size_complete": complete, "modified": int(info.st_mtime),
                                "editable": not isdir and Path(name).suffix.lower() in TEXT_EXT})
        return {"path": path, "entries": sorted(entries, key=lambda x: (not x["directory"], x["name"].casefold()))}

    def read(self, path):
        parts = self.parts(path)
        if Path(path).suffix.lower() not in TEXT_EXT:
            raise PanelError("binary")
        raw = self.read_bytes(parts)
        text, encoding = decode(raw)
        protected = path == "server.cfg"
        if protected:
            text = "".join(line for line in text.splitlines(keepends=True) if command(line) not in PROTECTED)
        return {"path": path, "text": text, "encoding": encoding, "revision": digest(raw), "protected": protected}

    def metadata(self, path):
        self.parts(path)
        try:
            checksum, size = hashlib.sha256(), 0
            with self.open_file(path) as file:
                while chunk := file.read(128 * 1024):
                    checksum.update(chunk)
                    size += len(chunk)
            return {"exists": True, "revision": checksum.hexdigest(), "size": size}
        except (FileNotFoundError, PanelError) as error:
            if isinstance(error, PanelError) and error.code != "missing":
                raise
            return {"exists": False, "revision": "new", "size": 0}

    def backup(self, path, raw):
        if not raw or len(raw) > MAX_TEXT:
            return
        folder = self.backups / digest(path.encode())
        folder.mkdir(exist_ok=True, mode=0o700)
        name = str(time.time_ns()) + "-" + digest(raw)[:12]
        (folder / (name + ".bin")).write_bytes(raw)
        (folder / (name + ".json")).write_text(json.dumps({"path": path, "created": int(time.time()), "size": len(raw)}))
        for old in sorted(folder.glob("*.bin"), reverse=True)[10:]:
            old.unlink()
            old.with_suffix(".json").unlink(missing_ok=True)
        all_copies = sorted(self.backups.glob("*/*.bin"), key=lambda p: p.name, reverse=True)
        budget = 0
        for old in all_copies:
            budget += old.stat().st_size
            if budget > 64 * 1024 * 1024:
                old.unlink()
                old.with_suffix(".json").unlink(missing_ok=True)

    def _revision(self, parts, expected):
        path = "/".join(parts)
        meta = self.metadata(path)
        if expected != meta["revision"]:
            raise PanelError("conflict", 409)
        if not meta["exists"]:
            return None
        return self.read_bytes(parts) if meta["size"] <= MAX_TEXT else b""

    def publish(self, parts):
        if not (parts[0] in RESOURCES or len(parts) == 1 and parts[0].lower().endswith(".wad")):
            return
        with self.open_file("/".join(parts)) as source, self.directory(parts[:-1], self.fastdl, create=True) as fd:
            temp = ".panel-" + secrets.token_hex(12)
            out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=fd)
            os.fchmod(out, 0o644)
            try:
                with os.fdopen(out, "wb") as target:
                    while chunk := source.read(128 * 1024):
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temp, parts[-1], src_dir_fd=fd, dst_dir_fd=fd)
            finally:
                try:
                    os.unlink(temp, dir_fd=fd)
                except FileNotFoundError:
                    pass

    @staticmethod
    def atomic(fd, name, data, mode=0o640):
        temp = ".panel-" + secrets.token_hex(12)
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=fd)
        try:
            with os.fdopen(out, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass

    def write(self, path, data, revision, text=False, encoding="utf-8"):
        parts = self.parts(path)
        if len(data) > MAX_UPLOAD or not revision:
            raise PanelError("large" if len(data) > MAX_UPLOAD else "revision", 413 if len(data) > MAX_UPLOAD else 400)
        with self.lock:
            old = self._revision(parts, revision)
            if text:
                if Path(path).suffix.lower() not in TEXT_EXT or len(data) > MAX_TEXT:
                    raise PanelError("binary")
                value = data.decode("utf-8")
                if "\x00" in value or encoding not in {"utf-8", "cp1251"}:
                    raise PanelError("encoding")
                if path == "server.cfg":
                    if any(command(line) in PROTECTED for line in value.splitlines()):
                        raise PanelError("protected", 403)
                    original, _ = decode(old or b"")
                    keep = [line for line in original.splitlines() if command(line) in PROTECTED]
                    value = value.rstrip() + "\n" + "\n".join(keep) + "\n"
                try:
                    data = value.encode(encoding)
                except UnicodeEncodeError:
                    raise PanelError("encoding") from None
            elif path == "server.cfg":
                raise PanelError("use_editor", 403)
            if old is not None:
                self.backup(path, old)
            with self.directory(parts[:-1]) as fd:
                self.atomic(fd, parts[-1], data)
            self.size_cache.clear()
            try:
                self.publish(parts)
                synced = True
            except (OSError, PanelError):
                synced = False
            return {"ok": True, "revision": digest(data), "fastdl_synced": synced}

    def mkdir(self, path):
        parts = self.parts(path, True)
        if not parts or len(parts) == 1:
            raise PanelError("protected", 403)
        with self.lock, self.directory(parts[:-1]) as fd:
            os.mkdir(parts[-1], 0o750, dir_fd=fd)
            self.size_cache.clear()
        return {"ok": True}

    def delete(self, path, revision):
        parts = self.parts(path)
        if path in ROOT_FILES:
            raise PanelError("protected", 403)
        with self.lock:
            old = self._revision(parts, revision)
            if old is None:
                raise PanelError("missing", 404)
            self.backup(path, old)
            with self.directory(parts[:-1]) as fd:
                os.unlink(parts[-1], dir_fd=fd)
            self.size_cache.clear()
            if parts[0] in RESOURCES or len(parts) == 1 and parts[0].lower().endswith(".wad"):
                try:
                    with self.directory(parts[:-1], self.fastdl) as fd:
                        os.unlink(parts[-1], dir_fd=fd)
                except (FileNotFoundError, PanelError):
                    pass
        return {"ok": True}

    def history(self, path):
        self.parts(path)
        folder = self.backups / digest(path.encode())
        return [{"id": p.stem, **json.loads(p.read_text())} for p in sorted(folder.glob("*.json"), reverse=True)]

    def restore(self, path, backup_id, revision):
        self.parts(path)
        if not re.fullmatch(r"[0-9]+-[a-f0-9]{12}", backup_id):
            raise PanelError("backup")
        raw = (self.backups / digest(path.encode()) / (backup_id + ".bin")).read_bytes()
        if Path(path).suffix.lower() in TEXT_EXT:
            value, enc = decode(raw)
            if path == "server.cfg":
                value = "".join(l for l in value.splitlines(keepends=True) if command(l) not in PROTECTED)
            return self.write(path, value.encode(), revision, True, enc)
        return self.write(path, raw, revision)
