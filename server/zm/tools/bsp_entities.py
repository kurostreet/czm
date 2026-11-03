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


def edit(text, drop, sky):
    blocks = re.findall(r"\{[^{}]*\}", text)
    kept, removed = [], 0
    for block in blocks:
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
    print(f"{args.target}: removed {removed} entities" + (f", sky {args.sky}" if args.sky else ""))


if __name__ == "__main__":
    main()
