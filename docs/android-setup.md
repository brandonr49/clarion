# Android Development Setup (macOS)

Complete guide for setting up Android development from scratch on a Mac.
This was written for a developer with no prior Android experience.

## Prerequisites

- macOS (Intel or Apple Silicon)
- ~15 GB free disk space (Android Studio + SDK + emulator images)

## Step 1: Install Android Studio

Download from https://developer.android.com/studio and install.

Or via Homebrew:
```bash
brew install --cask android-studio
```

On first launch, Android Studio will download the Android SDK, build tools,
and platform tools. Accept all defaults.

## Step 2: Install the Android SDK

Android Studio usually handles this on first launch, but verify:

1. Open Android Studio
2. Go to **Settings → Languages & Frameworks → Android SDK**
3. Under **SDK Platforms**, ensure at least one API level is installed (API 35 recommended)
4. Under **SDK Tools**, ensure these are installed:
   - Android SDK Build-Tools
   - Android SDK Platform-Tools
   - Android SDK Command-line Tools

The SDK installs to `~/Library/Android/sdk` by default.

## Step 3: Java (comes with Android Studio)

Android Studio ships with JetBrains Runtime (JBR), a Java distribution.
No separate Java installation needed. The Clarion build uses it:

```bash
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
```

If you need standalone Gradle (for building from the terminal without
Android Studio open), install it via Homebrew:

```bash
brew install gradle
```

Then generate the wrapper in the android project:
```bash
cd android
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
  gradle wrapper --gradle-version 8.9
```

## Step 4: Verify the Setup

```bash
# Check Java
"/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin/java" -version

# Check SDK
ls ~/Library/Android/sdk/platforms/
ls ~/Library/Android/sdk/build-tools/

# Check ADB (Android Debug Bridge)
~/Library/Android/sdk/platform-tools/adb version
```

## Step 5: Build the Clarion Android App

```bash
cd /path/to/clarion
make android-build
```

This runs:
```bash
cd android && \
  JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
  ANDROID_HOME=~/Library/Android/sdk \
  ./gradlew assembleDebug
```

The APK is output to: `android/app/build/outputs/apk/debug/app-debug.apk`

## Step 6: Install on a Physical Device

1. On your Android phone: **Settings → About Phone → tap "Build Number" 7 times**
   to enable Developer Options.
2. **Settings → Developer Options → enable "USB Debugging"**
3. Connect phone to Mac via USB cable
4. Accept the "Allow USB debugging?" prompt on the phone
5. Verify connection:
   ```bash
   ~/Library/Android/sdk/platform-tools/adb devices
   ```
   You should see your device listed.
6. Install the app:
   ```bash
   make android-install
   ```

## Step 7: Configure the App

1. Open the Clarion app on your phone
2. Tap the gear icon (Settings)
3. Enter your server URL (e.g., `http://192.168.1.100:8080`)
4. Tap "Test Connection" to verify
5. Go back and start submitting notes

## Troubleshooting

### "JAVA_HOME is not set"
Set it in your shell profile:
```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
```

### "ANDROID_HOME is not set"
```bash
export ANDROID_HOME=~/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools
```

### ADB doesn't see my device
- Try a different USB cable (some cables are charge-only)
- Revoke and re-authorize USB debugging on the phone
- Run `adb kill-server && adb start-server`

### Build fails with "SDK not found"
Ensure `ANDROID_HOME` points to `~/Library/Android/sdk` and that
the required SDK platforms and build tools are installed via Android Studio.

### Opening the project in Android Studio
Open the `android/` directory (not the repo root) in Android Studio.
It will recognize the Gradle project and set up the IDE automatically.

## Project Structure

```
android/
├── app/
│   ├── build.gradle.kts            # App dependencies and config
│   └── src/main/
│       ├── AndroidManifest.xml     # App permissions and entry point
│       └── java/com/clarion/app/
│           ├── MainActivity.kt     # Entry point, navigation
│           ├── ui/                 # Compose UI screens
│           ├── data/               # API client, models, config
│           └── viewmodel/          # State management
├── build.gradle.kts                # Root build config (plugins)
├── settings.gradle.kts             # Project settings
├── gradle/wrapper/                 # Gradle wrapper (versioned)
└── gradle.properties               # JVM and Android settings
```
