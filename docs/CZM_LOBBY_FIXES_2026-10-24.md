# CZM — lobby corrections requested on 24 October 2026

- Remove team-language controls, catalog language filters and language badges.
  Leave optional backend language data intact for compatibility with older tests.
- Use the Settings-style public-lobby switch: on by default; off means invite only.
- Size creation from its three field groups, and search from the visible results.
  An empty search no longer reserves four rows or an unused pagination footer.
- Dismiss creation/search on a matching backdrop press/release. Interior taps or
  a drag ending outside do not dismiss. Backdrop taps never destroy an active room.
- Reconcile and leave a create/join operation completed after dismissal; discard
  stale catalog replies after navigation. Clear old chat data on a room change.
- Clip map cover images to their actual destination; check trimmed Unicode title
  length and keep server occupancy separate from party size.

## Voice root causes

Production Uvicorn had no WebSocket engine installed. Pin `websockets==15.0.1`
and test the actual Uvicorn network transport, not only FastAPI TestClient.
The native voice bridge also passed the legacy device key directly to WSS,
whereas HTTP substituted the private account session inside Java. The socket now
gets that same Java-only session through an origin-restricted account accessor.
No account session is returned to native code, URLs or logs.

Mic intent survives a transient same-room reconnect. Explicit mute, account/room
changes, leaving, authorization denial and backgrounding still disable capture.
The Android permission dialog may pause SDL; its result belongs only to the same
pending session. Old socket/audio callbacks cannot tear down the replacement.

Tests cover native geometry/hits, Unicode validation, cancellation/navigation,
Java permission/reconnect/background/session callbacks, real account credential
routing, and two authenticated peers over a real isolated Uvicorn TCP socket.
A physical two-device audio-quality test is still required.

All APKs remain private test builds. No Play publication, player update broadcast
or merge into the published branch is authorized by these corrections.
