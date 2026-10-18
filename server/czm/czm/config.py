"""Settings of the Counter Zombie Mobile service, read from /etc/czm/env (CZM_*)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CZM_", extra="ignore")

    data_dir: Path = Path("/var/lib/czm")       # database, avatars, APK files, server list
    public_url: str = "https://counter-zombie.ru"   # where players reach the service
    pepper: str = "change-me"                  # mixed into stored key and device hashes

    # Telegram bot of the owner: complaints, bans, news, releases
    bot_token: str = ""
    bot_api_url: str = ""                      # relay for the Bot API, Telegram is blocked from the server
    bot_owner_ids: str = ""                    # comma-separated Telegram user IDs
    bot_polling_timeout_seconds: int = 25

    # world server list from Steam (IGameServersService/GetServerList, appid 10)
    steam_key: str = ""
    steam_refresh_seconds: int = 300

    # automatic updates: GitHub Actions sends each new core APK (proved by its OIDC token),
    # the server adds the game data of the previous release, signs it and publishes it
    build_repository_id: int = 1413538918       # kurostreet/czm
    build_repository: str = "kurostreet/czm"
    build_ref: str = "refs/heads/feature/mobile-launcher"
    build_workflow: str = ".github/workflows/build.yml"
    build_audience: str = "kontrafps.ru"
    build_autopublish: bool = True              # players get every build at once
    build_max_mb: int = 700
    build_keep: int = 3                         # release APK files kept on disk
    apksigner: str = "apksigner"
    keystore: str = ""                          # default: <data_dir>/signing/debug.keystore (public upstream debug key)

    # chat rules
    rooms: str = "global,ru,en"
    message_max_chars: int = 200
    message_interval_seconds: float = 3.0
    room_history: int = 100
    keep_days: int = 7

    # Codes by mail. Resend (HTTP API) goes first when its key is set, an authenticated TLS
    # SMTP sender is the fallback. Without either, mail forms are not offered.
    resend_key: str = ""
    resend_url: str = "https://api.resend.com/emails"
    mail_from: str = "Counter Zombie Mobile <noreply@counter-zombie.ru>"
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = False

    @property
    def resend_ready(self) -> bool:
        return bool(self.resend_key and self.mail_from)

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.smtp_from)

    @property
    def mail_ready(self) -> bool:
        return self.resend_ready or self.smtp_ready

    @property
    def owner_ids(self) -> set[int]:
        ids = set()
        for part in self.bot_owner_ids.replace(" ", "").split(","):
            if part.lstrip("-").isdigit():
                ids.add(int(part))
        return ids

    @property
    def room_list(self) -> list[str]:
        return [r.strip() for r in self.rooms.split(",") if r.strip()]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "czm.sqlite3"

    @property
    def avatar_dir(self) -> Path:
        return self.data_dir / "avatars"

    @property
    def mappic_dir(self) -> Path:
        return self.data_dir / "mappics"

    @property
    def apk_dir(self) -> Path:
        return self.data_dir / "apk"

    @property
    def incoming_dir(self) -> Path:
        return self.data_dir / "incoming"

    @property
    def keystore_file(self) -> Path:
        return Path(self.keystore) if self.keystore else self.data_dir / "signing" / "debug.keystore"

    @property
    def serverlist_file(self) -> Path:
        return self.data_dir / "server-list" / "v1" / "servers" / "cstrike"


@lru_cache
def get_settings() -> Settings:
    return Settings()
