"""The entry point Android runs.

python-for-android's SDL2 bootstrap looks for ``main.py`` in the app directory,
but the game is a package under ``src/`` -- the layout the desktop build uses.
So this puts ``src`` on the path and hands over to the very same entry point the
desktop runs (``python -m neverdeads_revenge``), with no arguments: a handheld
launch has no command line to parse.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from neverdeads_revenge.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main([]))
