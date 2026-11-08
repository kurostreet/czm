# Managed server resource packs

The new protocol delivers **data only**, separately from the accepted Dev85 / Play
40280152. Client/native code still updates through the application store. Nothing
in the publisher enables a pack automatically or changes the source game server.

The backend's `official_servers.slot` is the stable identity (`survival`, `escape`).
The administrator can change its IP:port without a new APK. The existing
`official_switch.enabled` controls card visibility; it does not authorize resource
loads. A separate `official_resources.enabled` defaults to off. An empty slot,
missing revision or changed manifest closes resource eligibility.

## Delivery

A first install can download a single complete ZIP. Later updates compare the file
inventory and fetch only missing or changed files. Every object URL is immutable
within a `pack_id/revision`; resuming bytes from another revision is forbidden.
ZIP contains game-relative regular files only, with no folder entries.

Catalog: `GET https://kontrafps.ru/api/v1/server-resources/catalog`

```json
{
  "schema": 1,
  "max_age_seconds": 60,
  "servers": [
    {
      "server_id": "survival",
      "address": "176.118.222.43:27016",
      "resources_enabled": true,
      "pack_id": "survival",
      "revision": "r1",
      "manifest_url": "https://kontrafps.ru/server-resources/survival/r1/manifest.json",
      "manifest_sha256": "<64 lowercase hexadecimal characters>",
      "download_bytes": 1234
    },
    {"server_id": "escape", "address": "", "resources_enabled": false}
  ]
}
```

The actual default is two disabled entries, with no pack/manifest fields. The
catalog uses `Cache-Control: no-store`. The client must use its own elapsed-time
freshness and compare the selected address to this current registry; a cached IP
alone never grants another server the managed pack. Unknown global/favorite
servers cannot select their own manifest or origin.

Manifest (UTF-8 JSON, SHA-256 checked against the trusted catalog before parsing):

```json
{
  "schema": 1,
  "pack_id": "survival",
  "revision": "r1",
  "total_bytes": 4000,
  "files": [
    {
      "path": "sound/music/round.wav",
      "size": 4000,
      "sha256": "<64 lowercase hexadecimal characters>",
      "url": "https://kontrafps.ru/server-resources/survival/r1/files/<sha256>"
    }
  ],
  "archive": {
    "url": "https://kontrafps.ru/server-resources/survival/r1/bundle.zip",
    "size": 1234,
    "sha256": "<64 lowercase hexadecimal characters>"
  }
}
```

`download_bytes` is the whole ZIP size; the client's displayed missing-byte count
comes from its comparison with the actual installed inventory. `total_bytes` is
the uncompressed sum. URLs use only HTTPS on `kontrafps.ru`, no credentials,
redirects or game-supplied origins. FileResponse supplies byte ranges for resume;
a Caddy configuration must forward `/server-resources/*` to this backend (or
serve only its `published` directory with the exact same URL mapping). Never
serve the parent resource store or any game server directory.

Limits are shared with the client: 16,384 files, 512 MiB per file, 8 GiB total and
ZIP, 8 MiB manifest. IDs match `[a-z0-9][a-z0-9_-]{0,63}`. Asset paths are at most
240 ASCII characters, one to eight components, each at most 80 characters,
containing letters/digits/underscore/hyphen/dot/space. Components start with a
letter/digit/underscore/hyphen and cannot end with a dot or space. Duplicate paths
under case folding are rejected. These limits are protocol v1 constraints, not an
invitation to allocate that much memory: streams and bounded reads are required.

## Prepare resources on VDS

Use a separate pack per game mode initially. The publisher reads an existing local
server game directory; there is no need to copy every file by hand into a mixed
folder. For a future remote ZE server, first copy its allowed client assets into a
local staging source under operator control. Do not let a player's client pull
arbitrary files from a game server's self-advertised download URL.

All commands run in the service environment with `CZM_DATA_DIR` pointing to its
normal data directory. The dedicated store is:

```text
<data_dir>/server-resources/staging/<temporary build>
<data_dir>/server-resources/published/<pack_id>/<revision>/manifest.json
<data_dir>/server-resources/published/<pack_id>/<revision>/bundle.zip
<data_dir>/server-resources/published/<pack_id>/<revision>/files/<sha256>
```

Build from the game folder (this only reads that folder):

```bash
python -m czm.resource_publish publish --source /srv/czm-zm-test/game/cstrike --pack survival --revision r1
python -m czm.resource_publish verify --pack survival --revision r1
```

Check the output receipt (`files`, `total_bytes`, `archive_bytes`,
`manifest_sha256`) and test the revision before enabling it. Commands do not
modify the current APK/AAB or make a database assignment. The final directory is
renamed atomically only after a complete validated ZIP, per-file objects and
manifest have been written. Reusing a revision is rejected; publish `r2` instead.
Run as the service's file owner, or arrange its normal group read permissions;
temporary build folders retain restrictive permissions.

A separate explicit local operator action activates an already configured slot:

```bash
python -m czm.resource_publish activate --slot survival --pack survival --revision r1
python -m czm.resource_publish disable --slot survival
```

Activation fully verifies files and ZIP before updating that logical slot in one
database transaction. It does not change visibility, the server endpoint or the
other slot. For ZE use `--pack escape --slot escape`. Both slots may explicitly
reference the same pack if a future shared collection is intended; the publisher
does not silently merge packs. Existing installed clients without this protocol
continue receiving their unchanged `hello.official` fields.

Supported input inventory:

| Relative path | Actual format checked |
|---|---|
| Root `*.wad` | WAD2/WAD3 header and directory bounds |
| `maps/**/*.bsp` | GoldSrc v30 header and lump bounds |
| `models/**/*.mdl` | IDST v10 / IDSQ v10 sequence groups, declared file length |
| `sprites/**/*.spr` | IDSP v2 |
| `sound/**/*.{wav,mp3,ogg}` | RIFF/WAVE, MPEG/ID3, OggS |
| `gfx/**/*.{tga,bmp,png}`, `textures/**/*.{tga,bmp,png}` | Image header/type and basic size/dimension bounds |

Other files are ignored, including configs, `addons`, server plugins, APK/DEX/JAR,
native libraries and executables. A renamed executable with an allowed extension
fails its format check. Symlinked asset files/directories, unsafe names, case
collisions, changing source files, excessive sizes and empty inventories fail the
whole build and leave no published revision. Format checks are an additional
boundary, not a malware or asset-rights assessment.

## Validation

Backend/publisher tests exercise real deterministic archives and file responses,
explicit activation, visibility off, endpoint changes, empty/disabled slots,
corruption, paths/symlinks, bounded sizes, preservation of private source files,
immutable revisions and HTTP 206 resume. On the client, separately test manifest
hash and revision mismatch, connection interruption, cancellation/resume, network
consent, lack of space, bad paths/ZIPs, cache clear and actual match loading. A
server switch and a FastDL filesystem rescan must never retain another server's
mount. Real mode packs stay disabled until those checks and publication succeed.
