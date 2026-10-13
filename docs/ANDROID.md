# Building the APK

The game runs on a desktop today and is ready to be packaged. What is missing is
the Android toolchain, which is a **~10 GB download** -- so it is written down
here first, with every URL, and installed only on a yes.

The machine has ~44 GB free, which is enough.

## What gets installed, and from where

| what | why | from |
| --- | --- | --- |
| JDK 17 | Gradle, and `apksigner` | the distro (`openjdk-17-jdk`), or [Adoptium Temurin 17](https://adoptium.net/temurin/releases/?version=17) |
| Android command-line tools | `sdkmanager`, `adb` | [developer.android.com/studio#command-tools](https://developer.android.com/studio#command-tools) (the zips live under `dl.google.com/android/repository/`) |
| Android SDK platform 33 + build-tools | the platform the APK targets | via `sdkmanager`, from the [repository index](https://dl.google.com/android/repository/repository2-3.xml) |
| Android NDK r25b | compiles the Python and pygame C for arm64 | <https://dl.google.com/android/repository/android-ndk-r25b-linux.zip> |
| `buildozer`, `python-for-android` | the build itself | [PyPI: buildozer](https://pypi.org/project/buildozer/), [PyPI: python-for-android](https://pypi.org/project/python-for-android/) |
| `pygame-ce` 2.5.8 | the game's only runtime dependency | [PyPI: pygame-ce](https://pypi.org/project/pygame-ce/), source [pygame-community/pygame-ce](https://github.com/pygame-community/pygame-ce) |

Two things that are **not** downloaded, and why:

- **pygame-ce's Android recipe** is vendored in this repo at
  `p4a-recipes/pygame_ce/`. p4a's own recipe is for upstream pygame 2.1.0; the
  fork carries its own `buildconfig/Setup.Android.SDL2.in` (verified at the
  2.5.8 tag), so the recipe is the upstream one pointed at the fork, pinned to
  the version in this repo. `buildozer.spec` points `p4a.local_recipes` at it.
- **The Python it builds with** is its own: p4a needs Python **3.11 or 3.12**,
  and this machine's is 3.14. So the toolchain goes in a separate venv
  (`.venv-android`) and never touches the development one.

## The steps, once the download is approved

```sh
# 1. Java
sudo apt install openjdk-17-jdk            # or install Temurin 17 by hand

# 2. The Android SDK command-line tools, then the platform and build tools
unzip commandlinetools-linux-*_latest.zip -d "$HOME/android-sdk/cmdline-tools"
#   ...arranged as cmdline-tools/latest/...
yes | "$HOME/android-sdk/cmdline-tools/latest/bin/sdkmanager" --licenses
"$HOME/android-sdk/cmdline-tools/latest/bin/sdkmanager" \
    "platform-tools" "platforms;android-33" "build-tools;33.0.2"

# 3. The NDK
unzip android-ndk-r25b-linux.zip -d "$HOME/android-sdk/ndk"

# 4. A build-only Python, kept apart from the development one
python3.12 -m venv .venv-android
./.venv-android/bin/pip install buildozer python-for-android

# 5. Build. First run downloads and compiles everything and takes a while.
export ANDROID_HOME="$HOME/android-sdk"
export ANDROID_NDK_HOME="$HOME/android-sdk/ndk/android-ndk-r25b"
./.venv-android/bin/buildozer android debug
```

The result lands in `bin/neverdeads_revenge-0.1.0-debug.apk`, which sideloads
like any other APK (`adb install`, or copy it across).

## What to expect the first time

The recipe in `p4a-recipes/` has not been built yet -- this is the step that
tests it. If pygame-ce's 2.5.x build system has moved on from the template p4a
expects, the fix belongs in that file and the log will say which piece moved.
Everything before this point (the engine, the layout, the input, the save
paths, the bench) is already exercised by the desktop tests.

## On the device

- `--sniff` (the pad bench) is the first thing worth running on the real
  hardware: it shows every axis and button raw, which is where the mapping gets
  checked against the pad rather than against a spec sheet.
- The back gesture is escape; leaving the foreground saves the run.
