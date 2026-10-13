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

## The steps, as they actually ran

The toolchain lives in `~/android-toolchain`, none of it needs root, and
`~/android-toolchain/env.sh` puts it on the path. The commands below are the
ones that worked, including the small traps the first attempts hit.

```sh
# 1. Java and the host build tools (these are the only things that need sudo)
sudo apt install -y openjdk-17-jdk cmake \
    autoconf automake libtool pkg-config m4 \
    zlib1g-dev libncurses-dev libffi-dev libssl-dev \
    libbz2-dev libreadline-dev libsqlite3-dev liblzma-dev \
    uuid-dev libexpat1-dev git zip unzip curl

# 2. The Android SDK command-line tools, then the platform and build tools
mkdir -p ~/android-toolchain/sdk && cd ~/android-toolchain
unzip commandlinetools-linux-*_latest.zip -d sdk/.ctmp
mkdir -p sdk/cmdline-tools && mv sdk/.ctmp/cmdline-tools sdk/cmdline-tools/latest
export JAVA_HOME=~/android-toolchain/jdk-17        # unpacked Temurin 17
SM=~/android-toolchain/sdk/cmdline-tools/latest/bin/sdkmanager
yes | "$SM" --sdk_root=~/android-toolchain/sdk --licenses
"$SM" --sdk_root=~/android-toolchain/sdk \
    platform-tools platforms;android-33 build-tools;33.0.2

# 3. The NDK (r25b) and a build-only Python 3.12 (python-build-standalone)
#    unpacked under ~/android-toolchain/{sdk/ndk,python312}

# 4. The build environment. p4a wants Python 3.11/3.12, hence its own venv, and
#    buildozer wants Cython below 3.0.
~/android-toolchain/python312/bin/python3.12 -m venv .venv-android
./.venv-android/bin/pip install -U pip wheel setuptools
./.venv-android/bin/pip install buildozer python-for-android 'cython<3.0'

# 5. Build. VIRTUAL_ENV must be set and the venv's bin on PATH, or buildozer
#    tries `pip install --user` (illegal inside a venv) and cannot find cython.
. ~/android-toolchain/env.sh
export VIRTUAL_ENV="$PWD/.venv-android"
export PATH="$VIRTUAL_ENV/bin:$PATH"
buildozer android debug
```

The result lands in `bin/neverdeads_revenge-0.1.0-debug.apk`, which sideloads
like any other APK (`adb install`, or copy it across).

### Traps worth remembering

- `p4a.bootstrap`, not the old `android.bootstrap`, in `buildozer.spec`.
- `android.sdk_path` / `android.ndk_path` must be set in the spec -- buildozer
  reads them from there only, not from `ANDROID_HOME`, and otherwise uses an
  empty `~/.buildozer/android/platform/android-sdk`.
- `VIRTUAL_ENV` in the environment is what makes buildozer drop its `--user`.
- buildozer 1.6.0 looks for `sdkmanager` under `$SDK/tools/bin` (the old SDK
  layout), while the modern command-line tools install to
  `$SDK/cmdline-tools/latest`. A symlink bridges it:
  `ln -s cmdline-tools/latest ~/android-toolchain/sdk/tools`.
- NDK **r25b** is right, not the newer 28c p4a mentions: p4a's own
  `recommendations.py` sets `MIN_NDK_VERSION = MAX_NDK_VERSION = 25`, so only a
  25.x NDK is accepted.
- The app title must not contain an ASCII apostrophe: p4a writes it straight
  into `strings.xml`, and aapt reads `'` as a broken escape sequence. The spec
  uses the typographic `’` (U+2019) instead, which the launcher shows the same
  way and aapt accepts.
- p4a 2026.05.09 builds the target Python as **3.14.2** but pins its Cython
  recipe at **0.29.36**, which cannot compile against the 3.14 C-API
  (`_PyLong_AsByteArray` gained an argument). pygame-ce needs Cython on the
  *host* Python to build from its `.pyx` sources, so the vendored recipe sets
  `hostpython_prerequisites = ["cython==3.1.3"]` -- the mechanism kivy's recipe
  uses. p4a's own cython recipe is never built, so its old version never comes up.
- pygame-ce 2.5.x names **meson-python** as its PEP 517 build backend, and meson
  cannot cross-compile a Python extension the ordinary way: it compiles a
  sanity-check program for Android and then tries to *run* it on the build
  machine ("binary or interpreter not executable"). pygame-ce still ships the
  `setup.py` build p4a drives, so the vendored recipe overrides
  `install_python_package` to copy that build's output into the target
  site-packages instead of invoking pip (and so meson) a second time. p4a's own
  `MesonRecipe` is not used because it hard-requires numpy/pybind11 wrappers
  that pygame-ce has no need of.


## It builds

`buildozer android debug` produces
`bin/neverdeads_revenge-0.1.0-arm64-v8a-debug.apk` (~21 MB, signed with the
debug key). Checked with `aapt`: package `org.darknoxx.neverdeads_revenge`,
label "Neverdead's Revenge", minSdk 24, target 33, `WAKE_LOCK`, arm64-v8a. The
game's data is inside `assets/private.tar` (fonts, sounds, the package and
`main.pyc`), pygame is in `libpybundle.so`, and the SDL2/python libraries are in
`lib/arm64-v8a/`. What is left is running it on the device.

## What to expect the first time

The recipe in `p4a-recipes/` has now been built once, and the traps above are
what it took. If a future p4a moves again, the fix belongs in that recipe and
the log will say which piece moved. Everything before the packaging step (the
engine, the layout, the input, the save paths, the bench) is exercised by the
desktop tests.

## On the device

- `--sniff` (the pad bench) is the first thing worth running on the real
  hardware: it shows every axis and button raw, which is where the mapping gets
  checked against the pad rather than against a spec sheet.
- The back gesture is escape; leaving the foreground saves the run.
