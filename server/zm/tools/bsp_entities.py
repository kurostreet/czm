#!/usr/bin/env python3
"""Small, reviewable edits to the entity list of a GoldSrc (v30) map.

    python3 -I bsp_entities.py IN.bsp OUT.bsp [--drop PREFIX]... [--sky NAME]

--drop PREFIX  removes every entity whose "model" starts with PREFIX (decorations whose model or
               sprite was never published with the map: the server would refuse to load it);
--sky NAME     sets the sky of worldspawn to one the game already has.

Everything except the entity lump is copied byte for byte; the lumps are laid out again so the
new entity text may be shorter or longer.
"""
import argparse
import re
import struct

LUMPS = 15


def read(path):
    data = open(path, "rb").read()
    version = struct.unpack_from("<i", data, 0)[0]
    if version != 30:
        raise SystemExit(f"{path}: not a GoldSrc map (version {version})")
    lumps = [struct.unpack_from("<ii", data, 4 + 8 * i) for i in range(LUMPS)]
    return data, lumps


def blocks(text):
    """Splits the entity text into "{ ... }" blocks the way the engine reads it: braces inside
    quoted values (decal names such as "{bloodhand2") belong to the value."""
    out, depth, start, quoted = [], 0, 0, False
    for i, c in enumerate(text):
        if c == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                out.append(text[start:i + 1])
    if depth or quoted:
        raise SystemExit("entity text does not close its braces or quotes")
    return out


def check(data: bytes) -> str:
    """Reads the entity text as the server does (COM_Parse / ED_ParseEdict); "" when it loads."""
    off, length = struct.unpack_from("<ii", data, 4)
    text = data[off:off + length]
    end = text.find(b"\0")
    text = text[:end] if end >= 0 else text
    single = b"{})(',"
    pos, n = 0, len(text)

    def token():
        nonlocal pos
        while True:
            while pos < n and (text[pos] <= 32 or text[pos] >= 128):  # signed char <= ' '
                pos += 1
            if pos >= n:
                return None
            if text.startswith(b"//", pos):
                while pos < n and text[pos] != 10:
                    pos += 1
                continue
            break
        c = text[pos]
        if c == 34:
            close = text.find(b'"', pos + 1)
            close = n if close < 0 else close
            value, pos = text[pos + 1:close], close + 1
            return value if len(value) < 1023 else b"\xff" * 1024
        if c in single:
            pos += 1
            return bytes([c])
        start = pos
        while pos < n and 32 < text[pos] < 128:
            pos += 1
            if pos < n and text[pos] in single:
                break
        return text[start:pos]

    count = 0
    while (tok := token()) is not None:
        if tok != b"{":
            return f"entity {count}: expected {{"
        count += 1
        while True:
            key = token()
            if key is None:
                return f"entity {count}: no closing brace"
            if key == b"}":
                break
            value = token()
            if value is None:
                return f"entity {count}: no closing brace"
            if value[:1] == b"}":
                return f"entity {count}: closing brace without data after {key[:30]!r}"
            if len(value) >= 1023:
                return f"entity {count}: a value longer than the server reads"
    return ""


def edit(text, drop, sky):
    kept, removed = [], 0
    for block in blocks(text):
        model = re.search(r'"model"\s*"([^"]*)"', block)
        if model and any(model.group(1).lower().startswith(p.lower()) for p in drop):
            removed += 1
            continue
        if sky and re.search(r'"classname"\s*"worldspawn"', block):
            if re.search(r'"skyname"\s*"[^"]*"', block):
                block = re.sub(r'"skyname"\s*"[^"]*"', f'"skyname" "{sky}"', block)
            else:
                block = block[:-1] + f'"skyname" "{sky}"\n}}'
        kept.append(block)
    return "\n".join(kept) + "\n", removed


def write(path, data, lumps, entities):
    order = sorted(range(LUMPS), key=lambda i: lumps[i][0])
    body = bytearray()
    table = [None] * LUMPS
    base = 4 + 8 * LUMPS
    for i in order:
        chunk = entities if i == 0 else data[lumps[i][0]:lumps[i][0] + lumps[i][1]]
        table[i] = (base + len(body), len(chunk))
        body += chunk
        body += b"\0" * (-len(body) % 4)
    header = struct.pack("<i", 30) + b"".join(struct.pack("<ii", *t) for t in table)
    open(path, "wb").write(header + body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--drop", action="append", default=[])
    parser.add_argument("--sky")
    args = parser.parse_args()
    data, lumps = read(args.source)
    off, length = lumps[0]
    text = data[off:off + length].rstrip(b"\0").decode("latin1")
    text, removed = edit(text, args.drop, args.sky)
    write(args.target, data, lumps, text.encode("latin1") + b"\0")
    problem = check(open(args.target, "rb").read())
    if problem:
        raise SystemExit(f"{args.target}: {problem}")
    print(f"{args.target}: removed {removed} entities" + (f", sky {args.sky}" if args.sky else ""))


if __name__ == "__main__":
    main()
