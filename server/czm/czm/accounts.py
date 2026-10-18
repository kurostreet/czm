"""CZM accounts. Existing profile IDs, photos, messages and bans stay in place."""
import hashlib
import hmac
import html
import logging
import re
import secrets
import smtplib
import ssl
import unicodedata
from email.message import EmailMessage

import httpx

from . import service
from .config import get_settings
from .db import now

log = logging.getLogger("czm.mail")

SESSION_PREFIX = "czms1_"
SESSION_IDLE = 30 * 86400
SESSION_LIFE = 180 * 86400


class AuthError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


def nick_key(value):
    return unicodedata.normalize("NFKC", value).strip().casefold()


def valid_login(value):
    value = unicodedata.normalize("NFKC", value).strip()
    if not 2 <= len(value) <= 24 or any(unicodedata.category(c)[0] == "C" or c in '\\";^' for c in value):
        raise AuthError("nick")
    return value


def valid_password(password):
    try:
        encoded = password.encode("utf-8")
    except UnicodeError:
        raise AuthError("password") from None
    if not 8 <= len(password) <= 128 or len(encoded) > 512 or "\x00" in password:
        raise AuthError("password")


def password_hash(password, salt=None):
    valid_password(password)
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)
    return f"scrypt1${salt}${value.hex()}"


def password_matches(password, stored):
    # The dummy hash uses the same cost for missing accounts; never short-circuit by login.
    try:
        kind, salt, expected = (stored or ("scrypt1$" + "00" * 16 + "$" + "00" * 64)).split("$")
        if kind != "scrypt1":
            return False
        candidate = password_hash(password, salt).rsplit("$", 1)[1]
        return hmac.compare_digest(candidate, expected)
    except (AuthError, ValueError):
        return False


def rate(conn, scope, value, limit=8, seconds=900):
    t = now()
    conn.execute("DELETE FROM auth_limits WHERE expires <= ?", (t,))
    bucket = service.hash_secret(scope + ":" + value)
    row = conn.execute("SELECT count FROM auth_limits WHERE bucket = ?", (bucket,)).fetchone()
    if row and row[0] >= limit:
        raise AuthError("slow", 429)
    conn.execute("INSERT INTO auth_limits VALUES (?, 1, ?) ON CONFLICT(bucket) DO UPDATE SET count=count+1", (bucket, t + seconds))


def player_for_session(conn, token):
    row = conn.execute(
        "SELECT p.* FROM players p JOIN account_sessions s ON s.player=p.id "
        "WHERE s.token_hash=? AND s.expires>? AND s.seen>?",
        (service.hash_secret(token), now(), now() - SESSION_IDLE),
    ).fetchone()
    if row:
        conn.execute("UPDATE account_sessions SET seen=? WHERE token_hash=?", (now(), service.hash_secret(token)))
    return row


def account_info(conn, player):
    row = conn.execute("SELECT login, email FROM accounts WHERE player=?", (player["id"],)).fetchone()
    return {"id": player["id"], "nick": player["nick"], "avatar": service.avatar_ref(player),
            "login": row["login"] if row else "", "email": (row["email"] or "") if row else "",
            "mail_ready": get_settings().mail_ready}


def new_session(conn, player):
    t = now()
    conn.execute("DELETE FROM account_sessions WHERE expires<=? OR seen<=?", (t, t - SESSION_IDLE))
    token = SESSION_PREFIX + secrets.token_urlsafe(32)
    conn.execute("INSERT INTO account_sessions VALUES (?, ?, ?, ?, ?)",
                 (service.hash_secret(token), player["id"], t, t, t + SESSION_LIFE))
    conn.execute("DELETE FROM account_sessions WHERE player=? AND token_hash NOT IN "
                 "(SELECT token_hash FROM account_sessions WHERE player=? ORDER BY created DESC, rowid DESC LIMIT 5)",
                 (player["id"], player["id"]))
    return {"token": token, "profile": account_info(conn, player)}


def register(conn, legacy_key, nick, password, repeat, ip):
    rate(conn, "register", ip, 5, 3600)
    login = valid_login(nick)
    valid_password(password)
    if password != repeat:
        raise AuthError("repeat")
    if conn.execute("SELECT 1 FROM accounts WHERE nick_key=?", (nick_key(login),)).fetchone():
        raise AuthError("taken", 409)
    # Only a legacy secret proves ownership. A submitted ID, nick or device ID never does.
    player = service.player_by_key(conn, legacy_key)
    if not player or legacy_key.startswith(SESSION_PREFIX):
        raise AuthError("profile", 401)
    if conn.execute("SELECT 1 FROM accounts WHERE player=?", (player["id"],)).fetchone():
        raise AuthError("account", 409)
    conn.execute("INSERT INTO accounts(player,login,nick_key,password_hash,created) VALUES(?,?,?,?,?)",
                 (player["id"], login, nick_key(login), password_hash(password), now()))
    return new_session(conn, player)


def login(conn, nick, password, ip):
    rate(conn, "login-ip", ip, 12)
    rate(conn, "login-name", nick_key(nick), 20)
    account = conn.execute("SELECT * FROM accounts WHERE nick_key=?", (nick_key(nick),)).fetchone()
    if not password_matches(password, account["password_hash"] if account else None):
        raise AuthError("credentials", 401)
    player = conn.execute("SELECT * FROM players WHERE id=?", (account["player"],)).fetchone()
    return new_session(conn, player)


def authenticated(conn, token):
    player = player_for_session(conn, token)
    if not player:
        raise AuthError("session", 401)
    return player


def me(conn, token):
    return account_info(conn, authenticated(conn, token))


def logout(conn, token, everywhere=False):
    player = authenticated(conn, token)
    if everywhere:
        conn.execute("DELETE FROM account_sessions WHERE player=?", (player["id"],))
    else:
        conn.execute("DELETE FROM account_sessions WHERE token_hash=?", (service.hash_secret(token),))
    return {"ok": True}


def delete_account(conn, token, password, ip):
    """The player deletes the account from the game (Google Play requires it): the password confirms it.

    Gone: the account, its sessions and codes, email, cloud settings, friends, follows, blocks,
    private dialogs, chat messages, status, the photo and the profile itself. Reports and bans stay:
    they protect other players, and a ban is kept by the device hash, not by the profile.
    """
    rate(conn, "delete-ip", ip, 6, 3600)
    player = authenticated(conn, token)
    pid = player["id"]
    rate(conn, "delete-player", str(pid), 5, 3600)
    account = conn.execute("SELECT password_hash FROM accounts WHERE player=?", (pid,)).fetchone()
    if not account or not password_matches(password, account["password_hash"]):
        raise AuthError("credentials", 401)
    conn.execute("DELETE FROM private_messages WHERE dialog IN (SELECT id FROM private_dialogs WHERE low=? OR high=?)", (pid, pid))
    for sql in ("DELETE FROM private_dialogs WHERE low=? OR high=?",
                "DELETE FROM social_follows WHERE source=? OR target=?",
                "DELETE FROM social_blocks WHERE source=? OR target=?"):
        conn.execute(sql, (pid, pid))
    for table in ("social_profiles", "social_presence", "player_settings", "settings_history", "auth_codes",
                  "account_sessions", "tab_bindings", "messages", "accounts"):
        conn.execute(f"DELETE FROM {table} WHERE player=?", (pid,))
    conn.execute("DELETE FROM players WHERE id=?", (pid,))
    (get_settings().avatar_dir / f"{pid}.png").unlink(missing_ok=True)
    return {"ok": True}


MAIL_SUBJECTS = {"email": "подтверждение почты", "login": "вход в аккаунт"}
MAIL_HEADINGS = {"email": "Подтверждение почты", "login": "Код для входа"}


def mail_texts(code, purpose):
    """Subject, plain text and HTML of a letter with a one-time code."""
    subject = "Counter Zombie Mobile — " + MAIL_SUBJECTS.get(purpose, "восстановление пароля")
    heading = MAIL_HEADINGS.get(purpose, "Восстановление пароля")
    text = (f"{heading}: {code}\n\nКод действует 10 минут. Никому его не сообщайте.\n"
            "Если вы не запрашивали код, просто пропустите это письмо.")
    safe = html.escape(code)
    body = f"""<div style="margin:0;background:#0b0b0e;padding:32px 16px;font-family:Arial,sans-serif;color:#f4f4f6">
  <div style="max-width:520px;margin:0 auto;border:1px solid #3a1d22;border-radius:20px;background:#131317;padding:28px">
    <div style="font-size:13px;letter-spacing:3px;color:#e02532;font-weight:700">COUNTER ZOMBIE MOBILE</div>
    <h1 style="font-size:24px;margin:14px 0 8px;color:#ffffff">{html.escape(heading)}</h1>
    <p style="color:#a7a7ae;margin:0">Введите этот код в игре.</p>
    <div style="margin:26px 0;padding:18px;border-radius:14px;background:#1d1013;border:1px solid #8d1f2a;text-align:center;font-size:34px;letter-spacing:9px;font-weight:800;color:#ffffff">{safe}</div>
    <p style="color:#e02532;font-weight:700">Код действует 10 минут.</p>
    <p style="color:#85858c;font-size:13px;line-height:1.5">Никому не сообщайте этот код. Если вы не запрашивали его, просто пропустите это письмо.</p>
  </div>
</div>"""
    return subject, text, body


class MailRefused(Exception):
    """A refusal explained by the mail service, safe to log."""


def send_resend(cfg, address, subject, text, body):
    response = httpx.post(cfg.resend_url, timeout=15.0,
                          headers={"Authorization": f"Bearer {cfg.resend_key}", "Content-Type": "application/json"},
                          json={"from": cfg.mail_from, "to": [address], "subject": subject, "text": text, "html": body})
    if response.status_code // 100 != 2:
        # the service explains a refusal (domain not verified, limit); no key or address is logged
        try:
            reason = re.sub(r"\S+@\S+", "<address>", str(response.json().get("message", "")))[:200]
        except ValueError:
            reason = ""
        raise MailRefused(f"{response.status_code} {reason}")


def send_smtp(cfg, address, subject, text, body):
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, cfg.smtp_from, address
    message.set_content(text)
    message.add_alternative(body, subtype="html")
    context = ssl.create_default_context()
    smtp = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) if cfg.smtp_starttls else \
        smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=10, context=context)
    with smtp:
        if cfg.smtp_starttls:
            smtp.starttls(context=context)
        smtp.login(cfg.smtp_user, cfg.smtp_password)
        smtp.send_message(message)


def send_code(address, code, purpose):
    cfg = get_settings()
    if not cfg.mail_ready:
        raise AuthError("mail_unavailable", 503)
    subject, text, body = mail_texts(code, purpose)
    senders = ([("resend", send_resend)] if cfg.resend_ready else []) + ([("smtp", send_smtp)] if cfg.smtp_ready else [])
    for name, sender in senders:
        try:
            sender(cfg, address, subject, text, body)
            return
        except MailRefused as error:
            log.warning("mail via %s refused: %s", name, error)
        except Exception as error:
            # never the sender's credentials or the SMTP dialogue: the kind of failure and the SMTP code
            log.warning("mail via %s failed: %s %s", name, type(error).__name__, getattr(error, "smtp_code", ""))
    raise AuthError("mail_unavailable", 503)


def issue_code(conn, player, purpose, target, deliver=True):
    code = f"{secrets.randbelow(1000000):06d}"
    if deliver:
        send_code(target, code, purpose)
    digest = service.hash_secret(f"{player}:{purpose}:{code}")
    conn.execute("INSERT INTO auth_codes VALUES(?,?,?,?,?,0) ON CONFLICT(player,purpose) DO UPDATE SET "
                 "target=excluded.target,code_hash=excluded.code_hash,expires=excluded.expires,attempts=0",
                 (player, purpose, target, digest, now() + 600))
    return code


def consume_code(conn, player, purpose, code):
    row = conn.execute("SELECT * FROM auth_codes WHERE player=? AND purpose=?", (player, purpose)).fetchone()
    if not row or row["expires"] <= now() or row["attempts"] >= 5:
        raise AuthError("code")
    conn.execute("UPDATE auth_codes SET attempts=attempts+1 WHERE player=? AND purpose=?", (player, purpose))
    if not hmac.compare_digest(row["code_hash"], service.hash_secret(f"{player}:{purpose}:{code}")):
        raise AuthError("code")
    conn.execute("DELETE FROM auth_codes WHERE player=? AND purpose=?", (player, purpose))
    return row["target"]


def valid_email(address):
    address = address.strip().lower()
    if len(address) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", address):
        raise AuthError("email")
    return address


def email_request(conn, token, address, ip):
    player = authenticated(conn, token)
    rate(conn, "email", str(player["id"]), 3, 3600)
    rate(conn, "email-ip", ip, 6, 3600)
    address = valid_email(address)
    if conn.execute("SELECT 1 FROM accounts WHERE email=? AND player!=?", (address, player["id"])).fetchone():
        raise AuthError("email_used", 409)
    issue_code(conn, player["id"], "email", address)
    return {"ok": True}


def email_confirm(conn, token, code, ip):
    player = authenticated(conn, token)
    rate(conn, "email-confirm", ip, 20)
    address = consume_code(conn, player["id"], "email", code)
    if conn.execute("SELECT 1 FROM accounts WHERE email=? AND player!=?", (address, player["id"])).fetchone():
        raise AuthError("email_used", 409)
    conn.execute("UPDATE accounts SET email=? WHERE player=?", (address, player["id"]))
    conn.execute("DELETE FROM auth_codes WHERE player=? AND purpose IN ('login','reset')", (player["id"],))
    return account_info(conn, player)


def email_login_request(conn, address, ip):
    address = valid_email(address)
    rate(conn, "email-login-ip", ip, 6, 3600)
    rate(conn, "email-login-name", service.hash_secret(address), 3, 3600)
    if not get_settings().mail_ready:
        raise AuthError("mail_unavailable", 503)
    row = conn.execute("SELECT player FROM accounts WHERE email=?", (address,)).fetchone()
    if row:
        code = issue_code(conn, row["player"], "login", address, deliver=False)
        return address, code, "login"
    # Public response is the same; delivery runs after the response, never inside it.
    return None


def deliver_login_code(address, code, purpose):
    try:
        send_code(address, code, purpose)
    except AuthError:
        pass  # Never disclose account existence, codes or provider credentials in a response/log.


def email_login_confirm(conn, address, code, ip):
    address = valid_email(address)
    rate(conn, "email-code-ip", ip, 20)
    rate(conn, "email-code-name", service.hash_secret(address), 10)
    row = conn.execute("SELECT player FROM accounts WHERE email=?", (address,)).fetchone()
    if not row:
        raise AuthError("code")
    target = consume_code(conn, row["player"], "login", code)
    if target != address:
        raise AuthError("code")
    player = conn.execute("SELECT * FROM players WHERE id=?", (row["player"],)).fetchone()
    return new_session(conn, player)


def recover(conn, nick, ip):
    rate(conn, "recover-ip", ip, 5, 3600)
    rate(conn, "recover-name", nick_key(nick), 3, 3600)
    if not get_settings().mail_ready:
        raise AuthError("mail_unavailable", 503)
    row = conn.execute("SELECT player,email FROM accounts WHERE nick_key=?", (nick_key(nick),)).fetchone()
    if row and row["email"]:
        issue_code(conn, row["player"], "reset", row["email"])
    # Do not disclose whether a login or a verified recovery address exists.
    return {"ok": True}


def reset(conn, nick, code, password, repeat, ip):
    rate(conn, "reset-ip", ip, 15)
    valid_password(password)
    if password != repeat:
        raise AuthError("repeat")
    row = conn.execute("SELECT player,email FROM accounts WHERE nick_key=?", (nick_key(nick),)).fetchone()
    if not row:
        raise AuthError("code")
    target = consume_code(conn, row["player"], "reset", code)
    if not row["email"] or target != row["email"]:
        raise AuthError("code")
    conn.execute("UPDATE accounts SET password_hash=? WHERE player=?", (password_hash(password), row["player"]))
    conn.execute("DELETE FROM account_sessions WHERE player=?", (row["player"],))
    conn.execute("DELETE FROM auth_codes WHERE player=?", (row["player"],))
    return {"ok": True}
