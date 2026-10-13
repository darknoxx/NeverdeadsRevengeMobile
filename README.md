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

Phase 0: the fork exists, the engine is in, the engine tests run.

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

## Licence

MIT. See `LICENSE`. DejaVu Sans Mono travels with the game under its own
licence (see `assets/fonts/`).
