"""Sends a signed Google Play bundle to the testing tracks through the Google Play Developer API.

The service account czm-publisher (Google Cloud project czm-play) may only release testing
versions of this one app. Its key is /etc/czm/play-service-account.json (root:czm 640); it is
read here and never printed or logged. One run: open an edit, upload the bundle, put it on every
track of CZM_PLAY_TRACKS (internal and closed test by default) with the release notes, commit.
The commit sends the change to Google for review; testers get the build once Google approves it.
"""
import json
import logging
import time
from pathlib import Path
from typing import Iterator

import httpx
import jwt

from .config import get_settings

log = logging.getLogger("czm.play")
API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
UPLOAD = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications/"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"
NOTES_LIMIT = 500                               # Google Play limit per language


class PublishError(Exception):
    pass


def configured() -> bool:
    settings = get_settings()
    return settings.play_publish and bool(settings.play_track_list) and settings.play_service_account_file.is_file()


def release_notes(text: str) -> str:
    text = (text or "").strip() or "Исправления и улучшения."
    return text if len(text) <= NOTES_LIMIT else text[:NOTES_LIMIT - 1].rstrip() + "…"


def access_token(client: httpx.Client) -> str:
    account = json.loads(get_settings().play_service_account_file.read_text())
    now = int(time.time())
    assertion = jwt.encode({"iss": account["client_email"], "scope": SCOPE, "aud": account["token_uri"],
                            "iat": now, "exp": now + 3600}, account["private_key"], algorithm="RS256")
    r = client.post(account["token_uri"], data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                                "assertion": assertion})
    if r.status_code != 200 or not r.json().get("access_token"):
        raise PublishError(f"Google не выдал доступ ({r.status_code})")
    return r.json()["access_token"]


def _check(r: httpx.Response, what: str) -> dict:
    if r.status_code >= 300:
        try:
            message = r.json().get("error", {}).get("message", "")
        except ValueError:
            message = r.text
        raise PublishError(f"{what}: {r.status_code} {message}"[:400])
    return r.json() if r.content else {}


def english_listing(client: httpx.Client, auth: dict, app: str, edit: str) -> str | None:
    """The English language of the store listing (en-US first), None when there is none: Play takes
    release notes only in the listing's languages."""
    languages = [l.get("language", "") for l in _check(client.get(f"{app}/edits/{edit}/listings", headers=auth),
                                                        "языки").get("listings", [])]
    for language in ["en-US", "en-GB"] + languages:
        if language in languages and language.lower().startswith("en"):
            return language
    return None


def _chunks(path: Path) -> Iterator[bytes]:
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            yield chunk


def publish(bundle: Path, version: str, notes: str, client: httpx.Client | None = None, notes_en: str = "") -> int:
    """Puts the bundle on the testing tracks and sends it for review; returns its version code.
    notes_en: the English "What's new", sent when the store listing has an English language."""
    settings = get_settings()
    own = client is None
    if own:
        client = httpx.Client(timeout=httpx.Timeout(60, read=1800, write=1800))
    try:
        auth = {"Authorization": "Bearer " + access_token(client)}
        app = API + settings.play_package
        edit = _check(client.post(f"{app}/edits", headers=auth), "правка")["id"]
        try:
            size = bundle.stat().st_size
            uploaded = _check(client.post(
                f"{UPLOAD}{settings.play_package}/edits/{edit}/bundles",
                params={"uploadType": "media", "ackBundleInstallationWarning": "true"},
                headers={**auth, "Content-Type": "application/octet-stream", "Content-Length": str(size)},
                content=_chunks(bundle)), "загрузка")
            code = int(uploaded["versionCode"])
            release = {"name": f"{code} ({version})", "versionCodes": [str(code)], "status": "completed",
                       "releaseNotes": [{"language": "ru-RU", "text": release_notes(notes)}]}
            english = english_listing(client, auth, app, edit) if (notes_en or "").strip() else None
            if english:
                release["releaseNotes"].append({"language": english, "text": release_notes(notes_en)})
            for track in settings.play_track_list:
                _check(client.put(f"{app}/edits/{edit}/tracks/{track}", headers=auth,
                                  json={"track": track, "releases": [release]}), f"версия {track}")
            _check(client.post(f"{app}/edits/{edit}:commit", headers=auth), "отправка")
        except Exception:
            try:
                client.delete(f"{app}/edits/{edit}", headers=auth)
            except httpx.HTTPError:
                pass
            raise
        log.info("Google Play: %s (%d) sent to %s", version, code, ", ".join(settings.play_track_list))
        return code
    finally:
        if own:
            client.close()
