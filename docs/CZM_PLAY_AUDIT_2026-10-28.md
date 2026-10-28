# Google Play release audit — 28 October 2026

The checked Play build is `dev.gaming.czm` version `1.35-4482dc9`,
versionCode `40140794`, commit `4482dc9375f3e24c8732dab714c3775f12a8e621`.
This audit does not authorize a production release.

## Artifact evidence

The full AAB SHA-256 is
`c1a22392497e2d5c7c1a1c6b660e1c75737f25add6d5395f6ca9c41551427352`.
The stored file matches the publication receipt. Its actual base manifest has
minSdk 21, targetSdk 36 and exactly INTERNET, VIBRATE, RECORD_AUDIO,
POST_NOTIFICATIONS, FOREGROUND_SERVICE, FOREGROUND_SERVICE_DATA_SYNC and
WAKE_LOCK. It contains arm64-v8a and armeabi-v7a libraries. The signed-bundle
receipt records all ten ARM64 libraries passing the 16 KB checks and generated
APKs containing the install-time game-data pack. Both build workflows for the
exact commit completed successfully.

## Console and disclosures

On 28 October the existing Data Safety change was still saved but unsubmitted.
It was sent for review; Publishing overview now lists Data Safety under
“Changes in review”, with no remaining unsubmitted change at that observation.

The new “App activity / Other actions” declaration describes the implemented
playtime leaderboard: collected and shared for app functionality, not ephemeral,
and required because the current game has no collection opt-out. Existing
text, audio, image, identity and activity disclosures remain in place.
The blanket encryption answer remains No because independent game-server UDP
traffic does not establish encryption of every collected data flow.

Target audience is 18+ in Console. The privacy page is updated to match that
audience and explicitly describes deletion of playtime, ranking, rules
acceptance, profile warnings and access rights. Reports, bans and moderation
history remain for safety. Both RU and EN explain this. No new background
microphone or advertising permission is added by this work.

Community rules acceptance, in-app lobby reports, user blocks, moderation
roles and bounded server-side playtime accounting are present in the checked
code. Their presence does not replace ongoing moderation or a physical
Play-installed acceptance test.

## Account deletion regression and fix

The shipped server raised a foreign-key error when an account had playtime,
a moderation warning or a staff row. Private-test access could also block
deletion. Account deletion now removes those owned rows, per-install playtime
signals and update-witness rows, while retaining unrelated players and safety
records. Wrong-password requests remain non-destructive.

Player IDs previously used SQLite's implicit rowid allocation, which can reuse
the largest deleted ID. A persistent monotonic sequence now reserves existing
profile IDs and IDs appearing in retained moderation records. New players do
not inherit someone else's ban or historical moderation identity.

These changes are server-side and do not require re-uploading versionCode
40140794. The fix is kept on a separate branch; the protected application
branch is not merged as part of this audit.

Validation: 189 server tests pass, including the five added regressions for
Top 100/witness deletion, warned SUPPORT deletion, private-test access, ID
reuse after deletion/restart and migration of retained moderation IDs.

## Remaining production gates

- Complete physical acceptance from Google Play on a certified device,
  including installation/update, account preservation, microphone, lobby,
  moderation/report paths, Top 100 and the account-specific update bell.
- Inspect the actual outcome of the submitted Data Safety review.
- Finish the existing closed-test requirement and apply for production access;
  do not replace or move the existing tester group.
- Confirm distribution rights for bundled resources. The checked data pack
  contains, for example, `cstrike/maps/de_dust2.bsp`, `cstrike/cstrike.wad`,
  `valve/halflife.wad` and weapon model files. Their filenames establish
  inclusion, not a license or permission. Open-source engine licensing and
  renamed branding alone do not settle the rights to the bundled resources.
  Record the owner's evidence or replace resources before claiming this gate
  is closed.
- Production rollout remains a separate owner decision.

Relevant Google policies:
- https://support.google.com/googleplay/android-developer/answer/10787469
- https://support.google.com/googleplay/android-developer/answer/9876937
- https://support.google.com/googleplay/android-developer/answer/13327111
- https://support.google.com/googleplay/android-developer/answer/9888072

