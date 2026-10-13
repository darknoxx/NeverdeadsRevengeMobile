"""What a key means in the dungeon -- for a handheld.

The same dictionary of human key names to domain verbs the other builds keep,
in its own module so the app and the game screen can both read it without
importing each other.

``l`` opens the legend here too (east is the arrow, ``d`` and the stick), and
``f`` is the ultimate. The pad's own buttons are mapped in :mod:`mobile.pad`,
because a button is not a letter and pretending otherwise would put "button 2"
in a table meant for people.
"""

from __future__ import annotations

from neverdeads_revenge.game.actions import Action

__all__ = ["KEY_BINDINGS"]

KEY_BINDINGS: dict[str, Action] = {
    "up": Action.MOVE_NORTH,
    "k": Action.MOVE_NORTH,
    "w": Action.MOVE_NORTH,
    "down": Action.MOVE_SOUTH,
    "j": Action.MOVE_SOUTH,
    "s": Action.MOVE_SOUTH,
    "left": Action.MOVE_WEST,
    "h": Action.MOVE_WEST,
    "a": Action.MOVE_WEST,
    "right": Action.MOVE_EAST,
    "d": Action.MOVE_EAST,
    "y": Action.MOVE_NW,
    "u": Action.MOVE_NE,
    "b": Action.MOVE_SW,
    "n": Action.MOVE_SE,
    "home": Action.MOVE_NW,
    "pageup": Action.MOVE_NE,
    "end": Action.MOVE_SW,
    "pagedown": Action.MOVE_SE,
    ".": Action.WAIT,
    "space": Action.WAIT,
    "i": Action.INVENTORY,
    "q": Action.QUAFF,
    "r": Action.REWIND,
    ">": Action.DESCEND,
    "f": Action.ULTIMATE,
    "enter": Action.INTERACT,
}
