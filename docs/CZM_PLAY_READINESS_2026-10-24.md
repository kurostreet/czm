# Google Play preparation — 24 October 2026

Scope approved by the owner: prepare the existing `dev.gaming.czm` application,
validate through internal testing, update the current closed Alpha test and
revise Play declarations for the new features. Production release is separate.

## Verified before preparation

- The publisher service account obtained an access token and an authenticated
  Android Publisher read returned HTTP 200. No new key or broader permission is
  needed for that connection. The screenshot's empty key list is not current
  evidence that the existing server connection is broken.
- The accepted private APK comes from 87e42b4. All ten of its ARM64 libraries
  have PT_LOAD alignment of at least 16 KB. The Play artifact must be checked
  independently; Git/private APKs are a different application package.
- The repository already targets SDK 36 and includes the Kotlin BOM/AndroidX
  dependency fixes. The exact old Console warnings still require inspection.
- The previous `play.yml` sends its output to a backend that can immediately
  publish to both configured testing tracks. Preparation now defaults to
  `prepare_only=true` and saves an unsigned intermediate artifact. This is not
  the final AAB: the private install-time game-data pack and upload signature
  must be added and validated on the authorized server.

## Changes in this candidate

- The bell uses Play's account-specific update availability independently of
  whether the immediate in-app update flow is allowed. The button opens the
  existing game's Google Play listing, with an HTTPS fallback. Network errors
  retry after a minute rather than hiding updates for half an hour.
- The RU/EN update card describes the store-page action.
- Account deletion now removes lobby, launch, invitation, moderation-receipt,
  unread-notice and public-chat read-position references before the account.
  Owned rooms close; unrelated players and rooms remain. The previous routine
  could fail with a foreign-key error after using these new features.
- The privacy page distinguishes real-time lobby voice relayed by CZM, the
  private device-only microphone check and voice handled by external game
  servers. It includes temporary rooms, read markers and the new deletion data.
- The Play workflow checks every ARM64 library's ELF segment alignment and
  executes the real update router with deterministic Android/Play adapters.

## Declarations to reconcile with the actual Console form

| Area | Evidence / required next check |
| --- | --- |
| Personal data | Account login, optional email, user IDs, optional uploaded avatar/photo; compare purposes, optionality, deletion and retention with the current form. |
| Messages and social activity | Public chat, private messages, temporary lobby text, follows, invitations, presence and read markers. Do not claim no collection. |
| Audio | Lobby speech leaves the device through CZM's relay. Memory-only real-time processing still belongs in the form, marked ephemeral where its definition applies. The local 3-second check is not transmitted. Audit external in-match servers separately. |
| Pictures and game data | Review uploaded photos and shared map previews, including whether captured UI can contain player information. |
| Device/diagnostic data and SDKs | Check device hash, anti-abuse metadata, Play libraries and all shipped SDKs; do not infer the full answer from the microphone permission alone. |
| Encryption | HTTPS/WSS of CZM does not establish encryption of all data sent to independent game servers. The global encryption answer requires a full traffic/data-flow audit. |
| Deletion | In-app deletion has new regressions; web instructions exist at `/privacy#delete`. Check live behavior and the exact link registered in Console. |
| App access | Reviewers need reusable ordinary accounts and English instructions to reach all restricted features without waiting for an OTP. Two accounts help verify parties/voice; no admin backdoor is needed. |
| UGC | Existing profile reports, private/public message reports, blocks, lobby mute/kick and automatic filtering must be checked for adequate coverage of lobby messages/voice. Verify acceptance of the app's rules before creating UGC. A profile/host-mute button alone does not prove complete policy coverage. |
| Audience and rating | The screenshot shows 18+ in that region. Reconcile the current IARC answers and target audience with text/voice interaction and actual game content; do not guess a lower rating. |
| Permissions / background work | Verify the merged Play manifest, microphone prompt and dataSync foreground-download declaration. |
| Resources / licenses | Preserve required open-source notices and confirm distribution rights for bundled private game resources. |

## Release gates

1. Build the exact candidate with the existing Play package and a higher
   versionCode. Validate the full AAB and generated APKs, upload certificate,
   asset-pack inventory, native alignment and absence of the APK self-installer.
2. Inspect Console warnings and current declarations. Resolve the UGC/data-flow
   checks above and update the truthful disclosures before the Alpha rollout.
3. Use the existing service account for an explicit **internal-only** release,
   then verify a real Play-installed update and preservation of account/settings.
4. Promote the same validated version to the existing Alpha test. Keep testers
   enrolled; do not recreate the application or testing group.
5. Announce update availability through Play's account/track eligibility. The
   currently installed old binary retains its old click behavior until updated.

The closed-test timer and production-access application are distinct from this
update. No production release, account permission expansion or key rotation is
part of this preparation.
