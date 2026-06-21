# YourGov — Release Guide

## Artifacts produced

| Platform | Artifact | Purpose |
|----------|----------|---------|
| Android  | `MyGov-release.aab` | Google Play upload |
| Android  | `MyGov-release.apk` | QA / sideload / direct install |
| iOS      | `MyGov-iOS-*.ipa`  | TestFlight / App Store |
| iOS      | `MyGov-iOS-simulator.zip` | CI smoke-test |

---

## Android release

### Required GitHub Secrets

| Secret | Value |
|--------|-------|
| `ANDROID_KEYSTORE_BASE64` | `base64 mygov-release.jks` output |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_ALIAS` | Key alias (e.g. `mygov`) |
| `ANDROID_KEY_PASSWORD` | Key password |
| `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` | Full JSON content of service account key |

### Generate a keystore (one-time)

```bash
keytool -genkey -v \
  -keystore mygov-release.jks \
  -alias mygov \
  -keyalg RSA -keysize 4096 \
  -validity 10000 \
  -dname "CN=YourGov, OU=Mobile, O=YourGov, L=London, ST=England, C=GB"

# Encode for GitHub Secret
base64 mygov-release.jks | pbcopy   # macOS
base64 mygov-release.jks            # Linux → paste into secret
```

**Never commit the `.jks` file.**

### Google Play service account

1. Google Play Console → Setup → API access → Link to a Google Cloud project
2. Google Cloud Console → IAM → Service accounts → Create
3. Grant role: **Release Manager** (or custom with `androidpublisher` permissions)
4. Create JSON key → paste entire file content into `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`

### Local build commands

```bash
cd android-mygov

# Debug APK (no signing)
./gradlew assembleDebug

# Release AAB (signing via env vars)
KEYSTORE_PATH=../mygov-release.jks \
KEYSTORE_PASSWORD=<pw> \
KEY_ALIAS=mygov \
KEY_PASSWORD=<pw> \
./gradlew bundleRelease \
  -Pandroid.injected.signing.store.file="$KEYSTORE_PATH" \
  -Pandroid.injected.signing.store.password="$KEYSTORE_PASSWORD" \
  -Pandroid.injected.signing.key.alias="$KEY_ALIAS" \
  -Pandroid.injected.signing.key.password="$KEY_PASSWORD"
```

### Trigger a release

```bash
git tag android-v1.0.0
git push origin android-v1.0.0
```

Workflow: `.github/workflows/android-release.yml`

---

## iOS release

### Required GitHub Secrets

| Secret | Value |
|--------|-------|
| `APPLE_CERTIFICATE_P12_BASE64` | `base64 Distribution.p12` |
| `APPLE_CERTIFICATE_P12_PASSWORD` | .p12 export password |
| `KEYCHAIN_PASSWORD` | Arbitrary password for temp keychain |
| `APPLE_PROVISIONING_PROFILE_BASE64` | `base64 MyGov_AppStore.mobileprovision` |
| `APPLE_TEAM_ID` | Your 10-character Apple Team ID |
| `APPLE_API_KEY_ID` | App Store Connect API key ID |
| `APPLE_API_ISSUER_ID` | App Store Connect issuer UUID |
| `APPLE_API_KEY_CONTENT` | `.p8` file content (AuthKey_XXXX.p8) |

### Export distribution certificate (one-time)

1. Xcode → Preferences → Accounts → Manage Certificates → + → Apple Distribution
2. Keychain Access → find "Apple Distribution: ..." → right-click → Export
3. Export as `.p12` with a strong password
4. `base64 Distribution.p12 | pbcopy` → paste into secret

### Download provisioning profile

1. developer.apple.com → Certificates, Identifiers & Profiles
2. Create App ID: `uk.mygov.mobile`
3. Create Distribution profile → App Store → select certificate
4. Download `.mobileprovision` → `base64 MyGov_AppStore.mobileprovision | pbcopy`

### App Store Connect API key

1. App Store Connect → Users and Access → Integrations → App Store Connect API
2. Generate key → role: **Developer** (or App Manager for TestFlight)
3. Download `.p8` once (not re-downloadable)
4. Note the Key ID and Issuer ID

### Local build commands

```bash
cd ios-mygov

# Install XcodeGen (once)
brew install xcodegen

# Generate Xcode project
xcodegen generate

# Simulator build (no signing)
xcodebuild \
  -project MyGov.xcodeproj \
  -scheme YourGov \
  -configuration Release \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO \
  build

# Release archive (after signing setup)
xcodebuild \
  -project MyGov.xcodeproj \
  -scheme YourGov \
  -configuration Release \
  -archivePath build/MyGov.xcarchive \
  archive
```

### Trigger a release

```bash
git tag ios-v1.0.0
git push origin ios-v1.0.0
```

Workflow: `.github/workflows/ios-release.yml`

---

## Versioning convention

| Tag format | Workflow triggered |
|------------|-------------------|
| `android-v1.0.0` | Android release → Google Play internal |
| `ios-v1.0.0` | iOS release → TestFlight |

Bump `versionCode` (Android) and `CFBundleVersion` (iOS) before tagging.

---

## SHA-256 verification

Every Android release includes `SHA256SUMS.txt`. Verify:

```bash
sha256sum -c SHA256SUMS.txt
```
