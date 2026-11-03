#!/bin/bash
# Installs the Survival plugins and configs on the zombie game server (czm-zm-test.service).
#
#   install.sh RELEASE_DIR [--content]
#
# RELEASE_DIR is server/zm of one commit. Every plugin is compiled first; if one fails, nothing
# on the server changes. --content also (re)installs the maps and sounds from
# /var/lib/czm/survival-src (tools/install_content.py). Before any change the touched files are
# saved to /var/backups/czm-zm/. The game restarts at the end; the API and the site do not.
set -euo pipefail

R=$(cd "$1" && pwd)
CONTENT=0
[ "${2:-}" = "--content" ] && CONTENT=1

GAME=/srv/czm-zm-test/game
CS=$GAME/cstrike
A=$CS/addons/amxmodx
FASTDL=/srv/czm-zm-test/fastdl
SRC=/var/lib/czm/survival-src
OWNER=$(stat -c %U:%G "$CS")
STAMP=$(date +%Y%m%d-%H%M%S)

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT

echo "== compile"
for f in "$R"/scripting/*.sma; do
	n=$(basename "$f" .sma)
	if ! (cd "$A/scripting" && ./amxxpc "$f" -i"$R/scripting/include" -i"$A/scripting/include" -o"$BUILD/$n.amxx") > "$BUILD/$n.log" 2>&1; then
		cat "$BUILD/$n.log"
		echo "COMPILE_FAIL $n"
		exit 1
	fi
	grep -iE "warning|error" "$BUILD/$n.log" | sed "s#^#$n: #" || true
	if grep -qE "(error|fatal error) [0-9]+:" "$BUILD/$n.log" || [ ! -s "$BUILD/$n.amxx" ]; then
		echo "COMPILE_FAIL $n"
		exit 1
	fi
done
echo "COMPILE_OK"

echo "== backup"
mkdir -p /var/backups/czm-zm
(cd "$CS" && tar -czf "/var/backups/czm-zm/before-$STAMP.tgz" --ignore-failed-read \
	server.cfg mapcycle.txt addons/amxmodx/configs addons/amxmodx/plugins 2>/dev/null) || true
echo "/var/backups/czm-zm/before-$STAMP.tgz"

if [ "$CONTENT" = 1 ]; then
	echo "== content"
	python3 -I "$R/tools/install_content.py" "$SRC" "$GAME" "$FASTDL"
fi

echo "== plugins"
install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 0644 "$BUILD"/*.amxx "$A/plugins/"
install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 0644 "$R/configs/plugins-czm.ini" "$A/configs/plugins-czm.ini"
install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 0644 "$R/scripting/include/czm_survival.inc" "$A/scripting/include/"

# The key that signs the tickets of CZM players. The API reads the same file (group czm).
KEY=/etc/czm/game-ticket.key
if [ ! -s "$KEY" ]; then
	umask 077
	python3 -I -c "import secrets; print(secrets.token_hex(32))" > "$KEY"
	chown root:czm "$KEY"
	chmod 0640 "$KEY"
	echo "new ticket key"
fi
install -o root -g "${OWNER#*:}" -m 0640 "$KEY" "$A/configs/czm_ticket.key"

echo "== configs"
python3 -I - "$R/configs" "$CS" "$A/configs" <<'EOF'
import json, os, re, shutil, sys
src, cs, configs = sys.argv[1:]
BEGIN, END = "// >>> CZM Survival (server/zm, do not edit inside)", "// <<< CZM Survival"

def block(path, body):
    text = open(path, encoding="utf-8", errors="surrogateescape").read() if os.path.exists(path) else ""
    text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "", text, flags=re.S)
    text = text.rstrip("\n") + "\n\n" + BEGIN + "\n" + body.strip() + "\n" + END + "\n"
    open(path, "w", encoding="utf-8", errors="surrogateescape").write(text)

block(os.path.join(cs, "server.cfg"), open(os.path.join(src, "server.cfg")).read())
block(os.path.join(configs, "zombieplague.cfg"), open(os.path.join(src, "zombieplague.cfg")).read())

# zombieplague.ini: change single keys inside their sections, keep everything else
edits = json.load(open(os.path.join(src, "zombieplague.ini.json")))
path = os.path.join(configs, "zombieplague.ini")
lines = open(path, encoding="utf-8", errors="surrogateescape").read().split("\n")
section, done = None, set()
for i, line in enumerate(lines):
    m = re.match(r"\[([^\]]+)\]", line)
    if m:
        section = m.group(1)
        continue
    if section in edits and "=" in line and not line.lstrip().startswith(";"):
        key = line.split("=", 1)[0].strip()
        if key in edits[section]:
            lines[i] = f"{key} = {edits[section][key]}"
            done.add((section, key))
missing = [(s, k) for s in edits for k in edits[s] if (s, k) not in done]
if missing:
    raise SystemExit(f"zombieplague.ini has no {missing}")
open(path, "w", encoding="utf-8", errors="surrogateescape").write("\n".join(lines))

for name in ("mapcycle.txt",):
    shutil.copyfile(os.path.join(src, name), os.path.join(cs, name))
shutil.copyfile(os.path.join(src, "mapcycle.txt"), os.path.join(configs, "maps.ini"))
print("configs ok")
EOF
chown "$OWNER" "$CS/server.cfg" "$CS/mapcycle.txt" "$A/configs/zombieplague.cfg" "$A/configs/zombieplague.ini" "$A/configs/maps.ini"

echo "== restart"
systemctl restart czm-zm-test.service
sleep 10
systemctl is-active czm-zm-test.service
LOG=$(ls -t "$A"/logs/error_*.log 2>/dev/null | head -1 || true)
if [ -n "$LOG" ]; then
	echo "-- $LOG (last lines)"
	tail -n 15 "$LOG"
fi
journalctl -u czm-zm-test.service --since "-20s" --no-pager | grep -iE "czm|error|fail|plugin" | tail -n 20 || true
echo "INSTALL_DONE"
