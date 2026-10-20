"""Server commands:
  python -m czm.cli add-release <apk> <version> <code>
  python -m czm.cli assemble
  python -m czm.cli set-beta-testers <count-from-Play-Console>
  python -m czm.cli set-beta-open 0|1  # 1 only when Play testing links work
  python -m czm.cli create-dev-invite
  python -m czm.cli publish-migration <release-id>

add-release moves an uploaded APK into the download folder and remembers it as the
newest private development build. The owner publishes it in the bot (/release).
Only publish-migration exposes the final transition APK to existing public installs.
assemble turns the core APKs sent by GitHub Actions into releases (czm-assemble.service)
and finishes the bundles for Google Play sent by play.yml.
"""
import hashlib
import shutil
import sys
from pathlib import Path

from . import db, website, distribution
from .config import get_settings


def add_release(apk: Path, version: str, code: int) -> None:
    settings = get_settings()
    db.init()
    digest = hashlib.sha256()
    with apk.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    name = f"CounterZombieMobile-{version}.apk"
    target = settings.apk_dir / name
    settings.apk_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(apk), target)
    target.chmod(0o644)
    with db.db() as conn:
        conn.execute(
            "INSERT INTO releases (version, code, file, size, sha256, created, channel) VALUES (?, ?, ?, ?, ?, ?, 'development')",
            (version, code, name, target.stat().st_size, digest.hexdigest(), db.now()),
        )
    print(f"release {version} ({code}) ready: {target.stat().st_size // 1024 // 1024} MB, publish it in the bot with /release")


def main(argv: list[str]) -> int:
    if argv == ["create-dev-invite"]:
        db.init()
        with db.db() as conn:
            print(distribution.issue_invite(conn))
        return 0
    if len(argv) == 2 and argv[0] == "publish-migration" and argv[1].isdigit():
        db.init()
        with db.db() as conn:
            distribution.publish_migration(conn, int(argv[1]))
        print("Final public migration APK published; later APKs remain private.")
        return 0
    if len(argv) == 2 and argv[0] == "set-beta-open":
        if argv[1] not in ("0", "1"):
            print("Expected 0 (review pending) or 1 (approved and links verified)")
            return 2
        db.init()
        with db.db() as conn:
            website.set_play_beta_open(conn, argv[1] == "1")
        print("Google Play beta opt-in:", "OPEN" if argv[1] == "1" else "WAITING FOR APPROVAL")
        return 0
    if len(argv) == 2 and argv[0] == "set-beta-testers":
        if not argv[1].isdigit() or int(argv[1]) > 1000000:
            print("Expected a non-negative count from Google Play Console")
            return 2
        db.init()
        with db.db() as conn:
            website.set_play_beta_testers(conn, int(argv[1]))
        print(f"Google Play confirmed opted-in testers: {int(argv[1])}")
        return 0
    if argv == ["assemble"]:
        import logging
        from . import play
        from .assemble import run_pending
        logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
        run_pending()
        play.run_pending()          # bundles for Google Play, after the players' release
        return 0
    if len(argv) == 4 and argv[0] == "add-release" and argv[3].isdigit():
        add_release(Path(argv[1]), argv[2], int(argv[3]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
