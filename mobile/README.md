# CHII WORLD mobile — Phase 12

Android/iOS foreground location MVP. Backend contracts remain unchanged.
Phase 12 is **not fully verified** until the physical-device checklist below passes.
No Redis, background location, push, community/news/batch UI, image infrastructure or AR.

## Toolchain

- Flutter stable **3.47.7**, revision `abaf9c523780a608bd46686fd5e53740a07077f8`.
- Dart **3.13.5**. `.flutter-version` and pubspec SDK constraints pin versions;
  `tool/flutterw` verifies both. `pubspec.lock` is committed with the application.
- Android SDK 36; Java 17; iOS deployment target 15.0.
- Run `flutter doctor -v` after installing Android Studio / full Xcode.
- Invoke `tool/flutterw` with Flutter on PATH or set `FLUTTER_BIN` to its executable.
  The wrapper also sets the geolocator Apple SPM foreground-only compile flag.
  Never add Always location keys or background Location Updates capability.

```sh
cd mobile
tool/flutterw pub get --enforce-lockfile
tool/flutterw analyze
tool/flutterw test
tool/flutterw build apk --debug
```

## Local API and Google Maps

Development app ID / Bundle ID is `dev.chiiworld.mobile` (provisional, no deployment identity supplied).
The app defaults to Android emulator API `http://10.0.2.2:8000/api/v1`.
For an Android device over USB, use `adb reverse tcp:8000 tcp:8000` and pass
`--dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1`.
For iOS use a reachable **HTTPS** development API. Existing server ALLOWED_HOSTS must
allow the selected hostname. Do not disable TLS verification or globally relax ATS.
Cleartext is enabled only in the Android debug manifest; release requires HTTPS.
No changes to backend deployment settings have been made by this phase.

Google Maps needs separate Android/iOS API keys. Do not paste keys into Dart source,
Git, command-line flags, reports or chat. Keys are present in built apps and must be
restricted by platform application identity and API, not treated as server secrets.

- Android debug: create ignored `android/maps.local.properties` with
  `MAPS_API_KEY_DEBUG=<local key>`. Restrict to Maps SDK for Android, package ID,
  and the actual debug signing certificate SHA-1.
- Android release: inject `MAPS_API_KEY_RELEASE` from deployment secrets, with
  release package/certificate restrictions. Release signing is deliberately not
  configured with the debug signing key.
- iOS: create ignored `ios/Flutter/Maps.Debug.local.xcconfig` and separately
  `Maps.Release.local.xcconfig`, each setting `MAPS_API_KEY = <platform key>`.
  Restrict to Maps SDK for iOS and the actual Bundle ID. Do not commit these files.
- Enable display with `--dart-define=MAPS_ENABLED=true`. A native key-presence check
  keeps the placeholder/list when no key is configured. This cannot verify key
  validity, billing, quotas or network access: those require the device smoke test.
- Map attribution stays provided by the SDK. Map viewport/tile requests go to Google;
  application diagnostics do not record GPS. No offline tile downloads are provided.

```sh
tool/flutterw run --dart-define=MAPS_ENABLED=true --dart-define=API_BASE_URL=https://your-dev-host/api/v1
# iOS simulator compile once full Xcode is available (does not count as device validation):
tool/flutterw build ios --simulator
```

## Structure and behavior

`core/api.dart` is a bounded Dio transport with safe errors and no HTTP logging.
It rejects absolute external API paths and does not follow redirects with credentials.
`core/session.dart` owns memory access tokens and secure refresh tokens, single-flight
rotation, one authenticated retry, session generation and logout coordination.
Riverpod providers own app dependencies and an explicit auth Notifier; feature
controllers are small ChangeNotifiers scoped to the signed-in user's Home widget.
No repository/interface layer or Riverpod code generation is introduced. The only
substitutable boundaries are HTTP, secure storage and device location for tests.

- Restore: refresh → `/me`. Ambiguous refresh failure clears the old rotating token
  and requires login; it is never blindly retried. Logout waits for refresh/login,
  attempts to revoke the newest refresh, and clears local state. Offline revocation
  is reported as unconfirmed. Local secure-storage failures are shown safely.
- iOS Keychain uses this-device-only unlocked access; Android backup is disabled.
  Native storage behavior, reinstall/restore behavior and platform entitlement setup
  still require physical-device checks; in-memory tests do not prove these properties.
- Permission requests occur on explicit Nearby action. Resume checks location without
  asking again and invalidates old Nearby data, without automatically fetching Nearby.
  Denied, permanent denial, restricted, disabled service, reduced accuracy, stale fix,
  timeout and other location failures have separate handling. iOS restricted status
  uses a small native channel. Paused/background results are rejected.
- Nearby: 1km, 20 default results per page; same coordinates for later pages. New fix
  resets pages. Request generations prevent old results overwriting a newer search.
  Map movement/GPS events do not trigger API searches. The map displays loaded Spots,
  not all database results. An explicit list action works without maps.
- Encounter always obtains a fresh fix (15-second location timeout/freshness bound).
  200/201 are accepted; timeout is not automatically replayed. Generic discovery UI
  deliberately does not resolve Variant IDs by changing backend contracts.
- Capture sends `{}` and no GPS, retaining the same Encounter ID after uncertain
  response. Duplicate taps are coalesced; explicit retry uses server idempotency.
  Server state/expiry remains authoritative, regardless of device clock.
- Collection shows current Character/Variant/Rarity, Spot and acquisition time;
  pagination and refresh-after-capture are provided. Icons are placeholders, not
  speculative URLs from asset_key. Runtime session/Encounter/coordinates are not
  persisted. After process termination Collection recovers confirmed captures;
  an unpersisted Encounter ID cannot be resumed through a nonexistent list endpoint.

## Automated verification

```sh
# From repository root, with Docker running and pinned Flutter on PATH:
docker build -t chii-world-api backend
python3 mobile/tool/run_backend_integration.py
```

The runner creates ONLY the `chii-mobile-test` Compose project and database, migrates
unchanged backend code, seeds synthetic data and a random in-memory test credential,
and executes Dart application controllers over real HTTP. It removes that test
stack and volume in `finally`. No production/development data or crawler is touched.
`backend_flow_test.dart` is skipped in normal tests and enabled only by the runner.
The flow covers login, Nearby, Encounter, repeated Capture, Collection, restore and
logout. It replaces GPS and secure storage; it is not a native-device E2E test.

CI runs unit/widget tests, analysis, Android debug compilation and this isolated
PostGIS contract flow. It needs no Maps key, actual GPS or Google Maps network.
The new workflow has not been run remotely because Phase 12 is not pushed.

## Physical-device acceptance — pending

Both Android and iOS remain **unverified**. No device or Google Maps keys were available.
Full Xcode was not installed; iOS native compilation also remains unverified.

For each platform record OS/device/app build, outcome and request ID only; never GPS,
password, token or raw request payload. Verify:

1. Login, restart refresh, secure-storage read/write/delete, logout and account change.
2. Deny, permanent denial/restricted if available, reduced precision, GPS off,
   timeout and permission changes while app is backgrounded.
3. Google Maps key restrictions, attribution, map rendering and list fallback.
4. Nearby and pagination, then a fresh physical fix before Encounter.
5. Capture, repeated tap/retry and Collection refresh with exactly one acquisition.
6. Backgrounding does not continue tracking; no precision coordinates in logs.
7. Release HTTPS and signing/key configurations separately from debug.

Backend schema/API/model changes: **none**. Phase 11 performance findings remain
unchanged; no caching, query tuning or extra performance experiment was added.


## 2026-10-17 local verification record

| Check | Observed result |
|---|---|
| Flutter doctor | Flutter and Android toolchain pass; Xcode category fails |
| Host | macOS 26.3, Apple Silicon |
| Android | compile/target SDK 36, min SDK 24, build-tools 36.0.0 |
| Java / Gradle / NDK | Zulu 17.0.13 / 9.3.1 / 28.2.13676358 |
| iOS | deployment target 15.0; full Xcode/CocoaPods absent, no native build |
| Unit tests | 35 passed (auth, HTTP, location adapter, feature controllers) |
| Widget tests | 3 passed |
| Real HTTP/PostGIS integration | 1 passed separately; skipped in normal test suite |
| Dart analyzer / format | passed |
| Android debug APK | build passed; key-free/map-disabled build |
| Android physical device | none connected; all native acceptance pending |
| iOS physical device | unavailable; all native acceptance pending |
| Google Maps real rendering/key restrictions | pending keys and devices |
| Remote GitHub Actions | workflow added, not pushed/run |

SDK installed outside the repository using the official stable Git revision. Flutter
was configured to use the installed Zulu JDK 17; no shell startup file was modified.
Doctor raw output and build/test logs are local temporary files, not source artifacts.
Generated APK/build/Gradle/SDK paths and local map keys are ignored by Git.

Resolved direct packages: flutter_riverpod 3.4.3, dio 5.11.1,
flutter_secure_storage 11.2.0, geolocator 14.1.1, google_maps_flutter 2.19.0.
Default unused Cupertino icon dependency was removed. No additional runtime package
was added for routing, model generation, logging, image hosting or caching.

## 2026-10-20 validation rerun

- Flutter 3.47.7 / Dart 3.13.5 remain unchanged. Android SDK/build-tools 36,
  Zulu Java 17.0.13 and macOS 26.3 were confirmed. The SDK is not on the global
  PATH; validation used the pinned executable with a command-local PATH.
- Locked dependency resolution, analyzer, full Dart format check, 35 unit tests
  and 3 widget tests passed. The separate real Django/PostGIS HTTP flow passed
  once; its normal-suite skip is intentional. Its isolated containers were removed.
- Android debug APK compiled successfully. No emulator was launched in this run;
  the available API 35 AVD is not evidence of an emulator acceptance pass.
- No Android physical device was connected. Full Xcode remains absent
  (Command Line Tools only); `xcodebuild` and `simctl` are unavailable. iOS build,
  Simulator, physical-device and signing validation remain **UNVERIFIED**.
- No local Android/iOS Maps key files exist. Actual map rendering/restrictions,
  native secure storage, physical GPS and permission UX remain **UNVERIFIED**.
  The user chose automatic validation with physical checks deferred.
- Added an ignore entry for the generated `android/build/` Gradle report directory.
  No application or Backend changes were required. Source checks found no token,
  private key, Maps key or private absolute-path patterns, and no application
  logging calls for tokens/GPS. This is not proof of native runtime log behavior.
- No commit/push or remote CI run was performed.

Status: **IMPLEMENTATION COMPLETE / DEVICE VALIDATION PENDING**.

## Phase 12.5 — mobile registration

Login now opens a screen-scoped registration form. It calls the unchanged
`POST /api/v1/auth/register` with `email`, `display_name`, and `password`.
Password confirmation is local validation only and is never sent to the server.
Success returns to Login with the normalized email and a confirmation message;
registration neither issues JWTs nor writes secure storage.

The form checks required values, basic email syntax, name/email/password lengths
and confirmation. Django remains authoritative for duplicate email, password
similarity/common-password/numeric checks and all field validation. Only the
registration 400 validation envelope is displayed as field/common errors;
unexpected/server/network failures use fixed safe messages. Passwords are cleared
after submit and disposed with the screen, never saved or logged. Requests are
single-flight with no automatic registration retry. After an uncertain network
outcome users can log in or retry manually; duplicate errors offer the Login route.

2026-10-20 verification:
- 48 unit + 6 widget tests passed (54 total); the two HTTP tests intentionally skip
  in the ordinary suite and both passed separately against isolated Django/PostGIS.
- HTTP tests cover signup/login/me/restore/logout, duplicate signup, and the existing
  Nearby/Encounter/repeated Capture/Collection flow.
- Analyzer, Dart format, Android debug build and iOS Simulator debug build passed.
- Xcode 27.1 built the pinned existing plugins. Flutter generated CocoaPods fallback
  configuration and Podfile.lock because the existing Google Maps iOS plugin does
  not support Swift Package Manager. No package version or Backend change was made.
- The user reports the pre-registration iPhone Login/Location/Nearby/Map/Encounter/
  Capture/Collection flow passed, including GPS and permissions. This is user-reported
  physical evidence, separate from automated checks.
- New registration on physical iPhone and Android remains pending until verified;
  Simulator compilation and Dart HTTP tests do not establish native secure-storage
  or permission behavior. No commit/push was performed.

2026-10-21: The user explicitly deferred physical-device verification of the new
registration flow. Implementation and automated validation are complete; physical
registration/regression acceptance remains pending. No commit/push performed.

## Final acceptance — 2026-10-21

**Phase 12/12.5 MVP: COMPLETE.** The user confirmed physical iPhone signup, email-prefilled Login, login, restart/session restore, logout and Nearby/Encounter/Capture/Collection regression. Combined with the recorded automated checks, this closes the MVP acceptance. Physical evidence is user-reported. Android physical validation remains UNVERIFIED; this is not a production-release readiness claim. Earlier pending entries are historical and superseded by this acceptance.
