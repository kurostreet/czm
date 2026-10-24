# Lobby audio check, unread badges and GoldSrc entity capacity

The owner confirmed the ba7d85d test APK works with a second player for lobby
creation/search, joining and voice. These additions build on that tested version.

## Voice

Every member can tap their own participant card to open a small microphone panel.
It records up to three seconds, shows a level meter, plays the result locally and
offers a persistent sensitivity slider. It shares the live lobby's 16-kHz mono
VOICE_COMMUNICATION capture factory and G.711 encoding. Test audio stays in RAM;
outgoing voice is suspended while the panel is open, and the previous on/off
intent is restored when it closes. Leaving, account/room changes, starting a game
or normal backgrounding erase the recording and stop audio. An explicitly pending
Android permission request resumes only its still-active test session.

Speech indicators measure audio energy with a short attack and 280-ms release.
Silent audio packets do not light the microphone. Own and remote icons/portrait
rings use this activity, and off/local mute/host mute take precedence. The voice
protocol permits a strict self-only mic intent/sensitivity message; sender IDs,
speaking notifications and host moderation remain server-controlled. Legacy audio
clients remain compatible. Host mute is rechecked before enabling transmission.

## Notifications

Small 1…99+ badges distinguish unread messages, new followers, accepted friendship
and changes to following relationships. Totals remain separate from unread counts.
The home Friends badge aggregates these events. Global/RU/EN public-chat unread
counts have independent read positions and a home Chat badge. The existing news
and update bell retains its counters; sections without events do not invent them.

Server-side notices acknowledge only IDs returned on the viewed page, scoped to
the authenticated account and category. A delayed acknowledgement cannot clear a
later follow request. A monotonically increasing database revision prevents older
poll responses from restoring cleared badges. Public-chat reads clamp to actual
messages in that room. The first presence starts at current chat history instead
of flagging the entire backlog. Existing incoming requests migrate unchanged.

## Server-specific connection failure

The screenshot reported CL_DeltaEntityGS bad delta entity number 1952. The pinned
engine derived its GoldSrc allocation from local gameinfo and player count even
though that protocol does not advertise the server's edict capacity. Patch 0022
reserves the existing MAX_GOLDSRC_EDICTS capacity before entity allocation. It does
not remove the parser's bounds check or change other wire formats. The regression
executes the actual delta writer for entity 1952 and boundary cases, including
rejection of negative/out-of-range indices.

Validation includes real Java capture/test lifecycle and activity detection with
deterministic adapters, native notification/menu scenarios, backend account/page/
race/room scope tests, legacy voice relay coverage and the normal integrated
three-ABI Android pipeline. Private APK packaging must preserve the matching
certificate and all resource bundles; no public distribution or Play merge.
