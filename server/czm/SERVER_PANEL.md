# Private single-server panel

`/server-panel` manages the existing `czm-zm-test.service` only. It has no rental,
billing, registration or tenant provisioning. The game, store and existing API
keep their own service and data.

The browser API is `/api/v1/server-panel/*` on loopback port 8210. A separate
root service exposes only fixed-unit power/status/logs and local game console
through `/run/czm-server-panel/control.sock`; it never accepts a shell or unit
path from the browser. The web process runs as the game user with a restricted
filesystem and no privileges. It cannot access store/CZM signing credentials.

Credentials are independent of game accounts. Provision
`/etc/czm-server-panel/credentials.json` privately with `login`, random hex
`salt` and a hex `hashlib.scrypt(password, salt=salt, n=16384, r=8, p=1)` hash.
No example production password or hash belongs in git. Session cookies are
host-only, Secure, HttpOnly, SameSite=Strict, with a 12-hour expiry. Browser
mutations require the configured Origin and a session-derived CSRF header.
Login limits and hashed sessions persist in the separate panel SQLite database.

Stage the selected source in `/opt/czm/panel-releases/<commit>`, then run its
`deploy/server-panel-install.sh` with that release path. This installs the two
panel services and does not restart the game or API. Stage static files separately,
keep the existing site contents, validate Caddy, and add the panel proxy route
before the general `/api/*` route. Uploads are limited to 64 MiB each.

Game paths are opened relative to directory descriptors with no-follow checks.
Only maps/models/sound/sprites/gfx/overviews, selected root configs, and AMXX
configs/plugins/scripting are exposed. Native modules, Reunion, engine binaries
and other host paths are protected. The editor supports UTF-8 and Windows-1251,
optimistic revision checking, atomic saves and ten previous versions per file
(also capped by a total backup budget). Management credentials are stripped from
the server.cfg editor and preserved on save/restore; raw server.cfg download and
binary overwrite are disabled. Only resource allowlists are exported to FastDL.

The owner grants a helper full control of this one game server. Uploaded plugins
execute with the existing game sandbox; this is not a hardened public multi-tenant
hosting offering. Game slots, runtime and current game data are preserved.

Rollback: restore the prior Caddy file and static-site symlink; disable/stop
`czm-server-panel.service` and `czm-server-panel-agent.service`. Do not stop the
game or remove its files. Keep panel state/backups for recovery. Credentials and
sessions must remain private; revoke sessions when changing helper access.
