# BEST INTRADAY Android

This is an Android Studio project which packages the supplied BEST_INTRADAY Python scanner using Chaquopy.

## What is included

- Original scanner logic copied from BEST_INTRADAY_FINAL_V2_FIXED(1).py
- Fixed the invalid `from __future__ import annotations` placement.
- TRUE same-time RVOL and disk cache retained.
- Android UI for capital and Upstox access token.
- START / STOP.
- One scan immediately, then every 10 minutes while the app is open.
- Results show regime, picks, price, score, RS, RVOL, quantity, T1/T2 and band.
- Scanner state/RVOL cache is redirected to Android's writable Python HOME.

## Build in Android Studio

1. Install Android Studio.
2. Open this folder: `BEST_INTRADAY_ANDROID`.
3. Let Gradle sync and download dependencies.
4. Make sure a JDK compatible with your Android Studio/Gradle setup is selected.
5. Install an Android SDK with API 35.
6. Build > Build Bundle(s) / APK(s) > Build APK(s).
7. The debug APK will normally appear under:
   `app/build/outputs/apk/debug/app-debug.apk`

The project uses Chaquopy 17.0.0, Python 3.13, Android minSdk 24, and arm64-v8a/x86_64. Chaquopy's current documentation says version 17 supports Python 3.10–3.14 and Android Gradle Plugin 7.3–9.2.

## Important

The Upstox access token is entered locally in the app and is not hard-coded into the project.

The current UI scanner is foreground-oriented: if Android kills the app process, scanning stops. A later version can add a foreground service / notification if continuous background scanning is required.
