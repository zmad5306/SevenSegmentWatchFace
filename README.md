# Seven Segment watch face

A 7-segment LCD-style watch face for Wear OS, built with [Watch Face Format](https://developer.android.com/training/wearables/wff) (WFF v2). WFF is the only watch face type the latest Wear OS on Pixel Watch accepts. The APK has no code, only resources.

![preview](app/src/main/res/drawable-nodpi/preview.png)

## Features
- `HH:MM` time drawn from individual pill-shaped segments. Follows the watch's 12/24-hour setting; the leading zero is blank in 12-hour mode.
- `MM-DD` date and `SS` seconds in smaller segments.
- Battery level above the time: a horizontal battery glyph that fills with the charge (red when low) and `NN%`.
- Editable in the watch face editor (long-press the watch face → **Customize**):
  - **Time color**: 11 presets.
  - **Date color**: the same presets. It also colors the battery indicator.
  - **Seconds**: when off, the date moves to the center.
  - **Shadows**: the faint unlit "ghost 8" behind the lit segments.
- In always-on mode, seconds and ghost segments are hidden and the digits are dimmed.

## Layout
`tools/generate_watchface.py` is the source of truth. It writes these files:

| File                                                   | Contents                  |
|--------------------------------------------------------|---------------------------|
| `app/src/main/res/raw/watchface.xml`                   | the WFF scene             |
| `app/src/main/res/values/strings.xml`                  | editor labels             |
| `app/src/main/res/drawable-nodpi/preview.png`          | watch face picker preview |
| `app/src/main/res/drawable/ic_launcher_foreground.xml` | app icon artwork          |
| `app/src/main/res/mipmap-anydpi/ic_launcher.xml`       | adaptive app icon         |

Don't edit those files by hand. Change the geometry, palette, or options in the script, then regenerate:

```bash
python tools/generate_watchface.py
```

## Build

```bash
./gradlew :app:assembleDebug
```

For Play Store uploads, build `bundleRelease` with your signing config. R8 is enabled for release, so the output contains no dex.

## Install
With the watch (or a Wear OS emulator) connected over ADB, for example through **Settings → Developer options → Wireless debugging** on the watch:

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Then long-press the current watch face, scroll to **Seven Segment**, and select it.
