# YourGov iOS — WKWebView MVP

SwiftUI + WKWebView shell wrapping the YourGov web app with strict URL allowlisting.

## Prerequisites

| Tool | Version |
|------|---------|
| Xcode | 15.4+ |
| iOS deployment target | 15.0 |
| XcodeGen | 2.40+ |

## Local setup

```bash
# Install XcodeGen (once)
brew install xcodegen

# Generate Xcode project
cd ios-mygov
xcodegen generate

# Open in Xcode
open MyGov.xcodeproj
```

The `MyGov.xcodeproj` is git-ignored — always regenerate from `project.yml`.

## Build

```bash
# Debug on simulator
xcodebuild \
  -project MyGov.xcodeproj \
  -scheme YourGov \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  build

# Release archive (requires signing — see docs/release.md)
xcodebuild \
  -project MyGov.xcodeproj \
  -scheme YourGov \
  -configuration Release \
  -archivePath build/MyGov.xcarchive \
  archive
```

## Signing (TestFlight / App Store)

See `docs/release.md` for the full signing setup. At a minimum you need:

- Apple Developer account (paid)
- Distribution certificate `.p12` exported from Keychain
- App Store provisioning profile `.mobileprovision`
- App Store Connect API key for `altool`/`notarytool`

Never commit certificates or profiles — store them as GitHub Actions secrets.

## Features

| Feature | Status |
|---------|--------|
| WKWebView loading `/start` | ✓ |
| URL allowlist (vercel.app only) | ✓ |
| Back / Forward / Refresh | ✓ |
| Open in Safari | ✓ |
| System share sheet | ✓ |
| Error state + Retry | ✓ |
| Offline recovery | ✓ |
| Dark theme | ✓ |
| Portrait lock | ✓ |

## Known limitations

- No push notifications
- No offline cache
- App icon placeholder only — add 1024×1024 PNG to `AppIcon.appiconset`
- Release signing requires paid Apple Developer account
