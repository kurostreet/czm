# CZM — native lobby design, 24 October 2026

Approved by the owner in chat on 24 October: replace the old pill buttons and
lobby UI with a consistent graphite interface. This supersedes the empty-search
creation action and solid blue/yellow home pills in the 23 October UX notes.

- Three equal home actions remain vertical. Quick Play is deep red; Create Lobby
  and Find Lobby use blue and gold accents on graphite surfaces. Straight Inter
  fonts, measured hints, small corner radii and shared hit geometry.
- Creation uses labelled name, a Settings-style public/invite-only switch (public by default), five capacity
  choices (2–6, including the owner) and one selected server card. No language controls.
- Public search has functional mode filters, map previews, capacity and
  entry controls. No Create Lobby action, invitations tab or empty pagination.
- Room: chosen server above two-column participant cards and the temporary chat.
  Group size is separate from server occupancy. Never invent unknown occupancy.
  Speaking borders follow voice activity; mic state alone never means speaking.
- Empty slots invite friends for the owner. Other members have a context menu
  for profile/local mute; server mute/kick/transfer remain host-only.
- Existing VDS map-preview loading is reused. Missing photos get a quiet fallback.
- Invitations use the same native surfaces and straight headings. Background
  Android push remains a separate task; this change does not implement it.

Latest corrections and voice root causes: `CZM_LOBBY_FIXES_2026-10-24.md`.

## Compatibility and verification

The optional `language` create field defaults to an unknown legacy language.
The additive DB migration preserves old clients and room data. Catalog filters
apply before pagination. Unknown map/language is included in the unfiltered
catalog and excluded from a specific filter rather than guessed.

Native tests exercise the actual C++ window at seven landscape resolutions,
both languages and capacities 2–6, including hit regions, request payloads,
local mute, role controls, launch readiness and session reset.

Commands:

```sh
python3 -m unittest discover -s tests -p test_home_actions.py -v
python3 -m unittest discover -s tests -p test_lobby_menu.py -v
PYTHONPATH=server/czm python3 -m unittest discover -s server/czm/tests -v
```

Only the test branch/draft PR is used. Assemble a private FULL APK with all three
verified resource bundles before installation. No Play release, main-branch
merge or automatic player-update publication is authorized by this change.
