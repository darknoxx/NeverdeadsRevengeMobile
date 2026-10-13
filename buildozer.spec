[app]

# The game, as Android sees it. The package name is the one the fork promised to
# keep -- neverdeads_revenge -- and the domain is the GitHub name behind it.
#
# The title uses a typographic apostrophe (U+2019), not the ASCII one: p4a writes
# this straight into strings.xml, and aapt reads an unescaped ASCII apostrophe as
# a broken escape sequence and refuses to build. U+2019 is not that character, so
# it passes -- and the launcher still shows "Neverdead's Revenge".
title = Neverdead’s Revenge
package.name = neverdeads_revenge
package.domain = org.darknoxx

# Everything in the repo is the app. The engine travels as it always did; the
# fonts and sounds are data the game reads at runtime and p4a would leave behind
# without being told, because its default extension list is only py/png/jpg.
source.dir = .
source.include_exts = py,png,jpg,jpeg,ttf,wav,txt,json
source.include_patterns = assets/fonts/*.ttf,src/neverdeads_revenge/sounds/*.wav
source.exclude_dirs = tests,docs,.venv,.git,p4a-recipes,.buildozer,__pycache__
source.exclude_patterns = *.md,LICENSE,pyproject.toml

version = 0.1.0

# pygame_ce is the vendored recipe in p4a-recipes/ (see that file for why it is
# not p4a's own pygame, which is upstream 2.1.0). The SDL2 bootstrap is what
# pygame needs and what buildozer would pick anyway; said out loud so the build
# does not depend on a default.
requirements = python3,pygame_ce
p4a.bootstrap = sdl2

# The device is 1240x1080 -- wider than tall, so landscape -- and the game draws
# its own frame centred inside whatever it is given, so fullscreen is right.
# (p4a appends `.Fullscreen` to the app theme itself when fullscreen is on, so
# the default Theme.NoTitleBar becomes Theme.NoTitleBar.Fullscreen -- setting it
# by hand here would double the suffix and aapt would reject it.)
orientation = landscape
fullscreen = 1

# The wake lock is the one permission the game asks for: it keeps the panel lit
# while a fight is on. Nothing else is needed -- no network, no storage beyond
# the app's own sandbox, no location.
android.permissions = WAKE_LOCK

# A 64-bit Snapdragon 865, so one architecture is enough.
android.archs = arm64-v8a
android.api = 33
android.minapi = 24
android.ndk = 25b

# Where this machine keeps the SDK and NDK. buildozer's own default is under
# ~/.buildozer, which is empty; these point it at the toolchain installed per
# docs/ANDROID.md. The paths are the one machine-local thing in this file.
android.sdk_path = ~/android-toolchain/sdk
android.ndk_path = ~/android-toolchain/sdk/ndk/android-ndk-r25b

# The SDK and NDK are already installed (see docs/ANDROID.md), and their licences
# are accepted there; do not let buildozer try to re-download or re-ask.
android.accept_sdk_license = True
android.skip_update = True

# The vendored recipe. buildozer hands this to p4a, which looks for a recipe
# directory of that name here before its own.
p4a.local_recipes = ./p4a-recipes

# Build only what is needed, and keep the log quiet enough to read.
android.logcat_filters = *:S python:D
android.allow_backup = 0

[buildozer]

log_level = 2
warn_on_root = 1
