#!/bin/bash
# Install or update the Counter Zombie Mobile service on the VDS. As root:
#   curl -fsSL https://raw.githubusercontent.com/kurostreet/czm/<commit>/server/czm/deploy/install.sh | bash -s <commit>
# Secrets stay on the server in /etc/czm/env; the first install takes the bot from the
# video project settings (/etc/fva/env) and makes a new pepper. Nothing is printed.
set -euo pipefail
COMMIT=${1:?usage: install.sh <commit>}
REPO=https://raw.githubusercontent.com/kurostreet/czm/$COMMIT/server/czm
FILES="requirements.txt czm/__init__.py czm/config.py czm/db.py czm/profanity.py czm/links.py czm/service.py czm/api.py
       czm/bot.py czm/steam.py czm/main.py czm/cli.py czm/builds.py czm/assemble.py czm/apkpatch.py czm/mappics.py czm/accounts.py czm/settings.py czm/tab.py czm/social.py czm/website.py czm/settings_schema.json czm/tlds.txt
       deploy/czm.service deploy/czm.caddy deploy/install.sh deploy/czm-set
       deploy/czm-assemble.service deploy/czm-assemble.path deploy/czm-assemble.timer"
# the public site (pages, pictures, fonts, script)
SITE="site/index.html site/privacy.html site/assets/apple-touch-icon.png site/assets/art-3.webp
      site/assets/avatar-1.png site/assets/avatar-10.png site/assets/avatar-2.png site/assets/avatar-3.png
      site/assets/avatar-4.png site/assets/avatar-5.png site/assets/avatar-6.png site/assets/avatar-7.png
      site/assets/avatar-8.png site/assets/avatar-9.png site/assets/ct.webp site/assets/env.webp
      site/assets/favicon-64.png site/assets/logo-96.png site/assets/og.jpg site/assets/shot-1.webp
      site/assets/shot-2.webp site/assets/shot-3.webp site/assets/shot-4.webp site/assets/shot-5.webp
      site/assets/shot-6.webp site/assets/shot-7.webp site/assets/shot-8.webp site/assets/shot-9.webp
      site/assets/site.js site/assets/title.png site/assets/zom.webp site/assets/fonts/Inter-Medium.woff
      site/assets/fonts/Inter-SemiBold.woff site/assets/fonts/InterDisplay-Black.woff
      site/assets/fonts/InterDisplay-BlackItalic.woff site/assets/fonts/OFL.txt"
# the public debug key of the engine (the same one signs every build, or updates would not install)
XASH=51353ff8d65e58300eeb2bd014867673f1f367c6
KEYSTORE_URL=https://raw.githubusercontent.com/FWGS/xash3d-fwgs/$XASH/android/debug.keystore
DEST=/opt/czm/releases/$COMMIT

id czm >/dev/null 2>&1 || useradd --system --home-dir /var/lib/czm --shell /usr/sbin/nologin czm
mkdir -p "$DEST/czm" "$DEST/deploy" /var/lib/czm/avatars /var/lib/czm/apk /var/lib/czm/server-list \
         /var/lib/czm/incoming /var/lib/czm/signing /var/lib/czm/mappics /etc/czm
mkdir -p "$DEST/site/assets/fonts"
for f in $FILES $SITE; do curl -fsSL "$REPO/$f" -o "$DEST/$f"; done
# links to pictures and the script change with every release, so browsers fetch the new ones
sed -i "s/__V__/${COMMIT:0:7}/g" "$DEST/site/index.html"

# automatic updates sign the APK with apksigner (Java)
if ! command -v apksigner >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends apksigner >/dev/null
fi
[ -s /var/lib/czm/signing/debug.keystore ] || curl -fsSL "$KEYSTORE_URL" -o /var/lib/czm/signing/debug.keystore

[ -x /opt/czm/venv/bin/python ] || python3 -m venv /opt/czm/venv
/opt/czm/venv/bin/pip install -q --disable-pip-version-check -r "$DEST/requirements.txt"

if [ ! -f /etc/czm/env ]; then
  (
    umask 077
    {
      echo "CZM_PEPPER=$(head -c 48 /dev/urandom | base64 | tr -d '/+=\n')"
      grep -E '^FVA_BOT_(TOKEN|API_URL|OWNER_IDS)=' /etc/fva/env 2>/dev/null | sed 's/^FVA_/CZM_/' || true
      echo "CZM_STEAM_KEY="
    } > /etc/czm/env
  )
fi
chown root:czm /etc/czm/env
chmod 640 /etc/czm/env

# the web server reads avatars, APK files and the server list
chown -R czm:czm /var/lib/czm
chmod 755 /var/lib/czm /var/lib/czm/avatars /var/lib/czm/apk /var/lib/czm/server-list /var/lib/czm/mappics
chmod 750 /var/lib/czm/incoming /var/lib/czm/signing

# czm-set: the owner types keys (mail, Steam) without showing them
install -m 755 "$DEST/deploy/czm-set" /usr/local/sbin/czm-set

ln -sfn "$DEST" /opt/czm/current
for unit in czm.service czm-assemble.service czm-assemble.path czm-assemble.timer; do
  install -m 644 "$DEST/deploy/$unit" /etc/systemd/system/$unit
done
systemctl daemon-reload
systemctl enable --quiet czm
systemctl restart czm
systemctl enable --quiet --now czm-assemble.path czm-assemble.timer

# the site: replaced only when it changed and Caddy accepts the new one
if [ -d /etc/caddy/sites ] && ! cmp -s "$DEST/deploy/czm.caddy" /etc/caddy/sites/czm.caddy; then
  [ -f /etc/caddy/sites/czm.caddy ] && cp -p /etc/caddy/sites/czm.caddy /etc/caddy/sites/czm.caddy.previous
  install -m 644 "$DEST/deploy/czm.caddy" /etc/caddy/sites/czm.caddy
  if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    systemctl reload caddy
  elif [ -f /etc/caddy/sites/czm.caddy.previous ]; then
    echo "Caddy rejected the new site, the previous one stays"
    mv /etc/caddy/sites/czm.caddy.previous /etc/caddy/sites/czm.caddy
  fi
fi
for i in $(seq 1 20); do
  curl -fsS http://127.0.0.1:8200/api/v1/ping >/dev/null 2>&1 && break
  sleep 1
done
systemctl is-active czm
curl -fsS http://127.0.0.1:8200/api/v1/ping && echo
