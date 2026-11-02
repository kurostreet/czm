#!/bin/bash
# Install only the private panel. Credentials must already exist; the game/API stay in place.
set -euo pipefail
RELEASE=${1:?usage: server-panel-install.sh /opt/czm/panel-releases/COMMIT}
case "$RELEASE" in /opt/czm/panel-releases/*) ;; *) exit 2 ;; esac
test -f "$RELEASE/server/czm/czm/server_panel.py"
test -s /etc/czm-server-panel/credentials.json
id czm-zm-test >/dev/null
install -d -o root -g czm-zm-test -m 750 /etc/czm-server-panel
chown root:czm-zm-test /etc/czm-server-panel/credentials.json
chmod 640 /etc/czm-server-panel/credentials.json
install -d -o czm-zm-test -g czm-zm-test -m 700 /var/lib/czm-server-panel
# This directory contains public game resources only, never private configs.
chown -R czm-zm-test:czm-zm-test /srv/czm-zm-test/fastdl
if [ ! -f /etc/czm-server-panel/env ]; then
  (umask 027; printf 'CZM_PANEL_OWNERS=1\n' > /etc/czm-server-panel/env)
fi
chown root:czm-zm-test /etc/czm-server-panel/env
chmod 640 /etc/czm-server-panel/env
ln -sfn "$RELEASE" /opt/czm/panel-current
SLOTS_CHANGED=0
install -d -m 755 /etc/systemd/system/czm-zm-test.service.d
if ! cmp -s "$RELEASE/server/czm/deploy/czm-zm-test-slots.conf" /etc/systemd/system/czm-zm-test.service.d/10-slots.conf; then
  install -m 644 "$RELEASE/server/czm/deploy/czm-zm-test-slots.conf" /etc/systemd/system/czm-zm-test.service.d/10-slots.conf
  SLOTS_CHANGED=1
fi
for unit in czm-server-panel-agent.service czm-server-panel.service; do
  install -m 644 "$RELEASE/server/czm/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable czm-server-panel-agent.service czm-server-panel.service >/dev/null
systemctl restart czm-server-panel-agent.service czm-server-panel.service
if [ "$SLOTS_CHANGED" = 1 ]; then
  systemctl restart czm-zm-test.service
fi
systemctl is-active --quiet czm-server-panel-agent.service
systemctl is-active --quiet czm-server-panel.service
