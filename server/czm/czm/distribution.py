"""Final public migration APK and a private, account-bound development channel."""
import base64
import hashlib
import hmac
import html
import re
import secrets
import zipfile

from . import accounts, service
from .config import get_settings
from .db import now

INVITE = re.compile(r"^[A-Za-z0-9_-]{32}$")
FILE = re.compile(r"^[A-Za-z0-9._-]{1,180}$")
INVITE_LIFE = DOWNLOAD_LIFE = 86400


def allowed(conn, player):
    return bool(player is not None and conn.execute(
        "SELECT 1 FROM development_access WHERE player=?", (player["id"],)).fetchone())


def issue_invite(conn):
    token = secrets.token_urlsafe(24)
    conn.execute("INSERT INTO development_invites(token_hash,created,expires) VALUES(?,?,?)",
                 (service.hash_secret(token), now(), now() + INVITE_LIFE))
    return f"{get_settings().public_url}/api/v1/development/invite/{token}"


def invitation(conn, token):
    if not INVITE.fullmatch(token):
        return None
    return conn.execute("SELECT * FROM development_invites WHERE token_hash=? AND expires>?",
                        (service.hash_secret(token), now())).fetchone()


def activate(conn, key, token):
    # Guests cannot consume the invitation before signing in to the intended account.
    player = accounts.authenticated(conn, key)
    row = invitation(conn, token)
    if not row or (row["used"] is not None and row["player"] != player["id"]):
        raise accounts.AuthError("invite", 403)
    if row["used"] is None:
        changed = conn.execute("UPDATE development_invites SET player=?, used=? "
                               "WHERE token_hash=? AND used IS NULL AND expires>?",
                               (player["id"], now(), row["token_hash"], now())).rowcount
        if changed != 1:
            raise accounts.AuthError("invite", 403)
        conn.execute("INSERT OR IGNORE INTO development_access(player,created) VALUES(?,?)",
                     (player["id"], now()))
    return {"ok": allowed(conn, player)}


def _signature(payload):
    return hmac.new(get_settings().pepper.encode(), ("development-download:" + payload).encode(), hashlib.sha256).hexdigest()


def download_ticket(player_id, filename):
    payload = base64.urlsafe_b64encode(f"{player_id}|{now() + DOWNLOAD_LIFE}|{filename}".encode()).decode().rstrip("=")
    return payload + "." + _signature(payload)


def ticket_player(conn, ticket, filename):
    if len(ticket) > 700:
        return None
    try:
        payload, signature = ticket.split(".", 1)
        if not hmac.compare_digest(signature, _signature(payload)):
            return None
        player, expires, name = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().split("|", 2)
        if name != filename or not now() < int(expires) <= now() + DOWNLOAD_LIFE:
            return None
        return conn.execute("SELECT * FROM players WHERE id=? AND EXISTS "
                            "(SELECT 1 FROM development_access WHERE player=players.id)", (int(player),)).fetchone()
    except (ValueError, UnicodeError):
        return None


def update_for(conn, key, code, *, player=None):
    player = player if player is not None else service.player_by_key(conn, key)
    development = allowed(conn, player)
    release = service.latest_release(conn, base_code=code, channel="development" if development else "legacy")
    if not release or release["code"] <= code:
        return None
    if development:
        for field in ("url", "patch_url"):
            if release.get(field):
                filename = release[field].rsplit("/", 1)[-1]
                release[field] += "?ticket=" + download_ticket(player["id"], filename)
    return release


def download_path(conn, filename, ticket="", invite=""):
    if not FILE.fullmatch(filename) or filename.startswith("."):
        return None
    release = conn.execute("SELECT * FROM releases WHERE file=? AND published IS NOT NULL", (filename,)).fetchone()
    patch = conn.execute("SELECT r.* FROM release_patches p JOIN releases r ON r.id=p.release_id "
                         "WHERE p.file=? AND r.published IS NOT NULL", (filename,)).fetchone()
    row = release or patch
    if row is None:
        return None
    public = service.latest_release(conn)
    permitted = row["channel"] == "migration" and public and row["id"] == public["id"]
    if not permitted and ticket:
        permitted = ticket_player(conn, ticket, filename) is not None
    if not permitted and invite and release:
        latest = service.latest_release(conn, channel="development")
        permitted = invitation(conn, invite) is not None and latest and row["id"] == latest["id"]
    path = get_settings().apk_dir / filename
    return path if permitted and path.is_file() else None


def invite_page(conn, token):
    row = invitation(conn, token)
    release = service.latest_release(conn, channel="development")
    if row is None or release is None:
        return None
    filename = release["url"].rsplit("/", 1)[-1]
    link = html.escape(f"{get_settings().public_url}/dl/{filename}?invite={token}", quote=True)
    return f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CZM — личный тестовый доступ</title><style>
body{{margin:0;background:#0e1118;color:#f3f4f6;font:17px/1.6 system-ui,sans-serif}}main{{max-width:640px;margin:auto;padding:32px 22px}}
h1{{font-size:28px}}a{{color:#fff}}.button{{display:inline-block;background:#dc2028;padding:12px 24px;border-radius:24px;text-decoration:none}}
input{{box-sizing:border-box;width:100%;font:16px monospace;padding:12px;background:#202530;border:1px solid #51596b;border-radius:8px;color:white}}
small{{color:#b0b8c7}}</style><main><h1>Counter Zombie Mobile — тестовая версия</h1>
<p>Это личный канал разработки. Ссылка действует 24 часа и активирует доступ для одного игрового аккаунта.</p>
<p><a class="button" href="{link}">Скачать тестовый APK</a></p>
<ol><li>Установите APK и откройте игру.</li><li>Откройте «Аккаунт и настройки» и войдите в свой игровой аккаунт.</li>
<li>Нажмите «Тестовый доступ» и вставьте личную ссылку или код ниже.</li></ol>
<p><input aria-label="Код тестового доступа" readonly value="{html.escape(token, quote=True)}"></p>
<p>После активации новые тестовые сборки будут приходить в колокольчик. Версия из Google Play устанавливается рядом.</p>
<small>Не пересылайте эту ссылку. Для игроков установка доступна через <a href="/&#35;beta">бета-тест Google Play</a>.</small></main></html>'''


def publish_migration(conn, release_id):
    beta = conn.execute("SELECT value FROM site_counters WHERE name='play_beta_open'").fetchone()
    if not beta or not beta[0]:
        raise ValueError("Google Play beta is not marked available")
    row = conn.execute("SELECT * FROM releases WHERE id=?", (release_id,)).fetchone()
    if row is None:
        raise ValueError("Release not found")
    apk = get_settings().apk_dir / row["file"]
    with zipfile.ZipFile(apk) as z:
        menus = [n for n in z.namelist() if n.startswith("lib/") and "/libmenu_android_" in n]
        if len(menus) != 3 or any(b"retired_title" not in z.read(n) for n in menus):
            raise ValueError("APK lacks the migration screen in all three ABIs")
    conn.execute("UPDATE releases SET channel='legacy' WHERE channel='migration' AND id!=?", (release_id,))
    conn.execute("UPDATE releases SET channel='migration' WHERE id=?", (release_id,))
    service.publish_release(conn, release_id,
                            "Эта версия больше не поддерживается. Установите игру через бета-тест Google Play: counter-zombie.ru/#beta. Аккаунт и настройки можно сохранить перед переходом.")
