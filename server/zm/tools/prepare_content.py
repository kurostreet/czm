#!/usr/bin/env python3
"""Turns the Survival source content (maps and Kontra sounds) into files the game server can serve.

Runs on the game host, where ffmpeg is installed:

    python3 -I prepare_content.py SOURCE.zip OUT_DIR

* maps/*.bsp are copied with lowercase names;
* sounds go to sound/survival/ with lowercase names. Kontra already squeezed its mp3 files
  (64 kbit/s, 22 kHz), so they are copied as they are: the game (Xash3D) plays mp3 both as
  background music and as an effect. A wav stays a mono 22 kHz wav when it is short, a longer
  one becomes an mp3 so the first download stays small. "kind" tells a plugin whether the file
  is music for the `mp3 play` channel or an effect;
* OUT_DIR/survival_sounds.json maps the original Kontra name to the new file, its kind and
  length, so plugins and checks agree on one list.

The source archive is the owner's data: it never goes into git.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

MUSIC = re.compile(r"^(welcome_s|welcome_x_sound|s_welcome_sound|s_autoplay|s_change_map|z_song\d+|"
                   r"end_sound\d+|soud_mario_day\d*|soud_mario_menu|soud_mario_welcome|up_song\d+|drago_song\d+)$")
# Short lines Zombie Plague plays at round end with "spk": they must be wav, and they must not
# take the music channel from the end-of-round track.
FORCE_WAV = re.compile(r"^(human_wins|zombie_wins)\d+$")
MP3_RATE = "64k"
SHORT_WAV = 3.0  # seconds


def clean_name(name):
    base = os.path.basename(name).lower()
    while True:
        stem, ext = os.path.splitext(base)
        if ext in (".mp3", ".wav"):
            base = stem
            continue
        return re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout.strip()
    return round(float(out or 0), 2)


def convert(src, dst):
    if dst.endswith(".wav"):
        args = ["-ac", "1", "-ar", "22050", "-codec:a", "pcm_s16le"]
    else:
        args = ["-ac", "1", "-ar", "22050", "-codec:a", "libmp3lame", "-b:a", MP3_RATE]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-map_metadata", "-1", *args, dst], check=True)


def main(source, out):
    sound_out = os.path.join(out, "sound", "survival")
    maps_out = os.path.join(out, "maps")
    os.makedirs(sound_out, exist_ok=True)
    os.makedirs(maps_out, exist_ok=True)
    manifest = {}
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or ".." in name.split("/") or name.startswith("/"):
                continue
            top = name.split("/", 1)[0]
            if top == "maps" and name.lower().endswith(".bsp"):
                with archive.open(info) as src, open(os.path.join(maps_out, os.path.basename(name).lower()), "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif top == "sound" and re.search(r"\.(mp3|wav)$", name, re.I):
                raw = os.path.join(tmp, "in" + os.path.splitext(name)[1].lower())
                with archive.open(info) as src, open(raw, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                stem = clean_name(name)
                music = bool(MUSIC.match(stem))
                if stem in {v["file"].rsplit(".", 1)[0] for v in manifest.values()}:
                    raise SystemExit(f"two sounds become {stem}")
                if FORCE_WAV.match(stem):
                    target = stem + ".wav"
                    convert(raw, os.path.join(sound_out, target))
                elif raw.endswith(".mp3"):
                    target = stem + ".mp3"
                    shutil.copyfile(raw, os.path.join(sound_out, target))
                else:
                    target = stem + (".wav" if not music and duration(raw) <= SHORT_WAV else ".mp3")
                    convert(raw, os.path.join(sound_out, target))
                manifest[os.path.basename(name)] = {"file": target, "kind": "music" if music else "sound",
                                                    "len": duration(os.path.join(sound_out, target))}
    with open(os.path.join(out, "survival_sounds.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1, sort_keys=True)
    music = sum(1 for v in manifest.values() if v["kind"] == "music")
    print(f"maps={len(os.listdir(maps_out))} sounds={len(manifest)} music={music}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
