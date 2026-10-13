# Neverdead's Revenge Mobile

**The same dungeon, on a handheld.**

A third fork of Neverdead's Revenge, for Android handhelds -- built for the
**Retroid Pocket Mini V2** (Snapdragon 865, Android 13, a 3.92" AMOLED at
1240x1080, which is very nearly square).

The engine -- `core/`, `world/`, `game/`, `persistence.py`, the sounds and the
whole test suite -- is copied untouched from the desktop build, which stays
frozen. What is new is the presentation: **pygame-ce** instead of PySide6, a
layout for a nearly square screen, and a **gamepad** instead of a keyboard.

| | |
| --- | --- |
| the desktop build | `~/Vibecoding/NeverdeadsRevenge2.0` (frozen, PySide6, CRT) |
| the terminal build | `~/Vibecoding/NeverdeadsRevenge` (frozen, Textual) |
| this one | Android, 1240x1080, gamepad only, no CRT effects (420 ppi eats them) |

## Status

The engine is in and green, the whole presentation is ported, and all twenty
screens have been walked headless. What remains is the Android build itself:
the APK, and whatever the real pad says once it is running on the device.

| phase | what | state |
| --- | --- | --- |
| 0 | the fork, the engine, the engine tests | done (1336 tests) |
| 1 | theme, font, buffer, render, the three-band layout | done |
| 2 | the pad: mapping, polling, the raw bench (`--sniff`) | done, awaiting a device |
| 3 | Android plumbing: save paths, back button, wake lock, pause/resume | done |
| 4 | the APK: toolchain, build, sideload | **built** -- `bin/neverdeads_revenge-0.1.0-arm64-v8a-debug.apk`, awaiting a device |

## Running it (development, on a desktop)

```sh
python3 -m venv .venv
./.venv/bin/pip install -e '.[dev]'
./.venv/bin/python -m neverdeads_revenge --scale 0.5 --zoom M
```

The flags:

| flag | what it does |
| --- | --- |
| `--zoom S\|M\|L` | how much dungeon against how big the letters |
| `--scale X` | the window at X times the device's size (0.5 on a laptop, 1.0 on the handheld) |
| `--hero noxx\|yeti\|walkyrion` | who goes down |
| `--seed N` | the same dungeon every time |
| `--testrun` | the chronicle unlocked, the purse full, and the ultimates answering from level 1 |
| `--no-sound` | start silent |
| `--sniff` | start on the pad bench: every axis, button and hat, raw (B leaves) |
| `--screenshot DIR` | draw one frame per zoom into DIR and exit (no window, works over ssh) |

`--zoom` takes `S`, `M` or `L`. The grid follows from the font's own metrics
(a cell is about six tenths as wide as it is tall), so the three zooms land as:

| zoom | font | grid | the frame | what it is for |
| --- | --- | --- | --- | --- |
| S | 20px | **95x43** | 1235x1075 | the most dungeon and the longest log |
| M | 27px | **72x32** | 1224x1056 | the middle, and the default |
| L | 36px | **56x25** | 1232x1075 | the biggest letters, a tighter view |

Screenshots of the same moment at all three, from `--screenshot`:
`docs/zoom_s.png`, `docs/zoom_m.png`, `docs/zoom_l.png`.

## The pad

The gamepad is the only input the device has, and the keyboard stands in for it
on a laptop. Directions are **polled** (a stick has a position, a D-pad a hat,
and an arrow key is read the same way); everything else -- buttons, letters, a
menu's shortcuts -- arrives as an event, one press one action. Holding a
direction walks at the hero's own pace, after a repeat delay so a tap is one
square. `--sniff` opens a bench that shows every axis, button and hat raw,
beside the name the game gives it: that is where a mapping is checked against a
real pad.

## On Android

- Saves go to the app's own sandbox (`ANDROID_PRIVATE`); there is no `$HOME`.
- The back gesture is escape, everywhere.
- Leaving the foreground writes the run down, because Android can take the
  process away without another word.
- A wake lock keeps the panel lit while the game is in front.

## Licence

MIT. See `LICENSE`. DejaVu Sans Mono travels with the game under its own
licence (see `assets/fonts/`).
