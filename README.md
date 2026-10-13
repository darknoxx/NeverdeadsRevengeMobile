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
| S | 20px | **95x43** | 1235x1075 | the most dungeon |
| M | 27px | **72x32** | 1224x1056 | the middle, and the default |
| L | 36px | **56x25** | 1232x1075 | the biggest letters, a tighter view |

Screenshots of the same moment at all three, from `--screenshot`:
`docs/zoom_s.png`, `docs/zoom_m.png`, `docs/zoom_l.png`.

## The screen

Three bands, and no rules between them -- each rule cost a row, and the bands
read apart without one. The **HUD** is health on its own line (with the
ultimate's ask in the top-right corner of that line, where the eye goes without
spending a line of playfield), then the level and floor, the fight's numbers,
the gold, what is worn, what is working, and the charge. The **map** takes
everything else, magnified 2x into its own band. The **log** is the last three
things said.

## The CRT, what is left of it

The desktop build drew its CRT with a shader. At 420 ppi a fine scanline is a
line nobody can see, so this fork left all of it out -- and then put back the
part that *is* visible and *is* affordable on a software renderer:

- **Scanlines**, coarse (every third row), baked into one overlay surface and
  blitted -- not drawn per frame.
- **Bloom**, done at a quarter of the size (a blur is a blur at a quarter of the
  size, and the cost of one is the size of the surface it runs on).
- **A magnified playfield**: the *map* is drawn at twice its size and windowed
  back into its band, so the HUD and the log keep their font and the thing the
  player is looking at is the thing that grows. The window follows the hero, so
  he is never cropped out at the edge of a floor.

All three are switches in the pause menu (`MAP ZOOM`, `SCANLINES`, `BLOOM`).
Scanlines and bloom are **off by default** -- the handheld found them too dear
for what they give -- and `SHOW FPS` puts a live readout in the corner of the
screen (drawn straight onto the panel, not into the buffer, so measuring does
not force the re-render it measures). The pad bench shows the last and worst
`render` / `post` / `present` in milliseconds.

The renderer caches the whole frame -- glyphs, map zoom *and* the CRT -- and
rebuilds it only when the buffer itself changes. Effects and the shake draw over
the cached copy, so a blood burst costs a copy and a few dots instead of two
thousand cell blits and a bloom: the CRT is baked once per change, not once per
frame, which is what made it unplayable on the handheld (2 fps). The ultimate's
breath is *stepped*, not smooth, because a smooth one changed the HUD text every
frame and so rebuilt the frame sixty times a second.

## The pad

The gamepad is the only input the device has, and the keyboard stands in for it
on a laptop. Movement is the **D-pad** (and the arrow keys): a D-pad is a hat --
eight positions and no in-between -- which is what a grid wants. The analog
stick is deliberately *not* read for movement; it drifts and has no true rest.
The **borrowed hour** and the **wait** are on the shoulders, L1 and R1; the
**ultimate** is the left stick click, the **sheet** the right one, the legend and
this page on L2 and R2, and Start pauses. Directions are **polled**; everything
else -- buttons, letters, a menu's shortcuts -- arrives as an event, one press
one action.

One thing to know if the mapping is ever touched again: on Android the button
**numbers are not the PC ones**. SDL maps each Android keycode to an
`SDL_CONTROLLER_BUTTON_*` index (`keycode_to_SDL` in SDL's
`src/joystick/android/SDL_sysjoystick.c`), and *that index* is what pygame
reports -- so the shoulders are 9 and 10, the stick clicks 7 and 8, Start 6 and
Select 4. Assuming the PC layout quietly put "escape" on L1 and nothing at all on
R1. Holding a direction walks at the hero's own pace, after a repeat delay so a
tap is one square. `--sniff` opens a bench that shows every axis, button and hat
raw, beside the name the game gives it: that is where a mapping is checked
against a real pad.

## On Android

- Saves go to the app's own sandbox (`ANDROID_PRIVATE`); there is no `$HOME`.
- The back gesture is escape, everywhere.
- Leaving the foreground writes the run down, because Android can take the
  process away without another word.
- A wake lock keeps the panel lit while the game is in front.

## Licence

MIT. See `LICENSE`. DejaVu Sans Mono travels with the game under its own
licence (see `assets/fonts/`).
