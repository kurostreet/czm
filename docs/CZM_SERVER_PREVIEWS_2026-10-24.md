# Square map previews and a full-width server browser

The installed 2026-10-24 test build showed a thin, heavily cropped map in the
creation form. In the server browser, cover-scaled images also painted beyond
their allotted area and under the server title. The permanent details panel
reduced the list width even when the user was only searching.

- Map thumbnails are square in creation, public rooms, the active lobby, pinned
  home cards, server rows, and the server details card. Pictures keep their aspect
  ratio and are cropped within their destination; downloaded photos and missing
  photo placeholders both restore the previous scrolling-list clip.
- Creation keeps its compact dimensions. A square photo sits beside the selected
  server's wrapped title, occupancy and map name, above the change-server button.
- The browser list fills the screen width. Tapping a server opens a details card
  with its square map, name, occupancy, ping, address, players and actions. Close,
  Android Back or a matching backdrop tap returns to the list without losing the
  search/scroll position. Dragging out of the card does not dismiss it. Password
  dialogs remain above it. Selecting for a lobby uses the existing callback and
  does not connect to the game.
- The Ready button's blue/unready and green/ready colours follow readiness only.
  Its previous flashing was incidental: any periodic GET or heartbeat temporarily
  disabled it. A tap during those reads is now queued once and sent with the
  latest room revision. Changing/closing rooms clears the queued action.

Native checks exercise seven landscape sizes, both interface languages, modal
touch routing, backdrop/drag behaviour, password-dialog priority, lobby picker
callbacks, square thumbnails, nested clipping, and Ready taps during polling.
Android CI validates the integrated three-ABI build. Physical-device visual and
audio acceptance are separate from these code checks. No server schema or public
APK distribution changes are included.
