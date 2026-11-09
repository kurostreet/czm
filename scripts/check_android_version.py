#!/usr/bin/env python3
"""Check compiled Android metadata against the release's single version file."""
import argparse
from pathlib import Path
import re


def check(version, code, package, flavor):
    path = Path(__file__).resolve().parents[1] / "android/version.properties"
    values = dict(line.strip().split("=", 1) for line in path.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#"))
    public = values["versionName"]
    expected_code = int(values["versionCode"])
    if not re.fullmatch(r"\d+\.\d+\.\d+", public) or not 40281373 < expected_code <= 2100000000:
        raise ValueError("Invalid release version configuration")
    expected_version = public + (f"-test.{expected_code}" if flavor == "test" else "")
    expected_package = {"play": "dev.gaming.czm",
                        "test": "ru.kurostreet.counterzombiemobile.test",
                        "rustore": "ru.kurostreet.counterzombiemobile"}[flavor]
    actual = (version.strip(), int(code), package.strip())
    expected = (expected_version, expected_code, expected_package)
    if actual != expected:
        raise ValueError(f"Compiled Android metadata {actual!r} differs from release configuration {expected!r}")
    print(f"Release metadata verified: {expected_package} {expected_version} ({expected_code})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flavor", choices=("play", "test", "rustore"), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--code", required=True)
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    check(args.version, args.code, args.package, args.flavor)
