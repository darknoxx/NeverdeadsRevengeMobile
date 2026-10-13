"""Keyboard and gamepad, both speaking the game's own key names.

Two jobs, one table each:

* :data:`KEYS` turns a pygame key into the name the screens already answer --
  ``"up"``, ``"enter"``, ``"f"`` -- so the whole input language of the other
  builds survives the move to a handheld, and a developer can play on a
  keyboard while the pad is not plugged in.
* :data:`BUTTONS` and :data:`AXES` do the same for a gamepad, including the
  analog stick: a stick is not eight keys, so it is read as a *direction* with
  a deadzone, and the app decides how fast that repeats.

The Retroid Pocket Mini V2 reports its pad through Android as a standard
SDL game controller: A/B/X/Y, L1/R1, analog L2/R2, Start/Select, plus the D-pad
as both a hat and buttons. Which number is which button is a fact about the
device, not about this game -- so :func:`describe_pad` exists to *say* what was
pressed, and the mapping below is the one that matched on the bench.
"""

from __future__ import annotations

import pygame

__all__ = [
    "KEYS",
    "BUTTONS",
    "AXES",
    "DEADZONE",
    "key_name",
    "button_name",
    "stick_direction",
    "describe_pad",
]

#: Keyboard, for development on a desktop and for a pad that lies about itself.
KEYS: dict[int, str] = {
    pygame.K_UP: "up",
    pygame.K_DOWN: "down",
    pygame.K_LEFT: "left",
    pygame.K_RIGHT: "right",
    pygame.K_RETURN: "enter",
    pygame.K_KP_ENTER: "enter",
    pygame.K_ESCAPE: "escape",
    pygame.K_SPACE: "space",
    pygame.K_TAB: "tab",
    pygame.K_BACKSPACE: "backspace",
    pygame.K_PERIOD: ".",
    pygame.K_GREATER: ">",
    pygame.K_SLASH: "?",
    pygame.K_QUESTION: "?",
}

#: The pad's face and shoulder buttons, by SDL's own numbering. A is the bottom
#: button on an Xbox-layout pad, which is what a Retroid ships as.
BUTTONS: dict[int, str] = {
    0: "enter",   # A -- the game's one verb: take, open, speak, descend
    1: "escape",  # B -- back, and the pause menu
    2: "q",       # X -- drink
    3: "i",       # Y -- the pack
    4: "l",       # L1 -- the legend
    5: "?",       # R1 -- the reference
    6: "c",       # L2 -- the sheet
    7: "f",       # R2 -- the ultimate
    9: "escape",  # Start -- the pause
    8: "select",  # Select -- the status menu
}

#: Stick axes, as ``(axis, sign)`` per direction.
AXES: tuple[tuple[int, int, str], ...] = (
    (0, -1, "left"),
    (0, 1, "right"),
    (1, -1, "up"),
    (1, 1, "down"),
)

#: How far a stick has to move before it means anything. Hall-effect sticks
#: drift less than the old potentiometers, but a thumb resting on one is not a
#: decision, and 0.4 is the value that stopped a resting stick from walking.
DEADZONE = 0.4


def key_name(event) -> str | None:
    """The game's name for a keyboard event, or ``None``.

    Letters come from the typed text, lower-cased, the way every other build
    reads them -- so a pad's ``X`` and a keyboard's ``x`` end up the same word.
    """
    named = KEYS.get(event.key)
    if named is not None:
        return named
    text = event.text or ""
    return text.lower() if text else None


def button_name(button: int) -> str | None:
    """The game's name for a gamepad button, or ``None``."""
    return BUTTONS.get(button)


def stick_direction(joystick) -> str | None:
    """The direction a stick is being pushed, or ``None`` if it is resting.

    Diagonals are read from the two axes at once, because that is what the
    player is doing -- and the game is eight-way, so a stick that only ever
    produced four directions would be half a D-pad.
    """
    x = joystick.get_axis(0)
    y = joystick.get_axis(1)
    left = x < -DEADZONE
    right = x > DEADZONE
    up = y < -DEADZONE
    down = y > DEADZONE
    if up and left:
        return "nw"
    if up and right:
        return "ne"
    if down and left:
        return "sw"
    if down and right:
        return "se"
    if up:
        return "up"
    if down:
        return "down"
    if left:
        return "left"
    if right:
        return "right"
    return None


def describe_pad(joystick) -> str:
    """One line saying what the pad is -- for the bench, and for a bug report.

    Printed once at startup in development: the name SDL reports, how many
    buttons and axes it has. A mapping that was written for the wrong device is
    a mapping that gets debugged twice.
    """
    return (
        f"{joystick.get_name()}: {joystick.get_numbuttons()} buttons, "
        f"{joystick.get_numaxes()} axes, {joystick.get_numhats()} hats"
    )
