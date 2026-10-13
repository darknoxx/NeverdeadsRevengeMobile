"""Colours, and the terminal styles translated -- for pygame.

The game carries its colours the way the terminal version did: hex values and
Rich colour names. This is where those become plain RGB tuples, so the palette
the player sees on the map is still the palette the game chose -- this build is
a *renderer*, not a re-skin.

A ``Style`` is the small part of Rich's style string the game actually uses: a
foreground, bold, dim, reverse, italic. Everything the screens pass around --
``"bold green"``, ``"dim cyan"``, ``"red"`` -- is parsed here, once, so the
screens can keep speaking the language they were written in.

The desktop build says the same thing with QColor. Here it is a tuple, because
pygame wants tuples and a colour that has to be converted on every glyph is a
colour paid for sixty times a second.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Style", "parse_style", "BACKGROUND", "FOREGROUND", "NAMED"]

RGB = tuple[int, int, int]

#: The dungeon's own black, and the phosphor the text is drawn in. Not pure
#: black and pure white: a CRT never was, and on an AMOLED a true black cell is
#: a cell that is switched off -- which is the one place the frame can be seen
#: to flicker as the panel dims it.
BACKGROUND: RGB = (11, 11, 11)
FOREGROUND: RGB = (200, 200, 200)

#: The named colours the game uses, as RGB. Standard and bright ANSI, the two
#: greys, and the one orange a damage line is drawn in -- the same values the
#: terminal approximated, written down so every build agrees.
NAMED: dict[str, RGB] = {
    "black": (0, 0, 0),
    "red": (170, 0, 0),
    "green": (0, 170, 0),
    "yellow": (170, 170, 0),
    "blue": (0, 0, 170),
    "magenta": (170, 0, 170),
    "cyan": (0, 170, 170),
    "white": (192, 192, 192),
    "bright_black": (128, 128, 128),
    "bright_red": (255, 85, 85),
    "bright_green": (85, 255, 85),
    "bright_yellow": (255, 255, 85),
    "bright_blue": (85, 85, 255),
    "bright_magenta": (255, 85, 255),
    "bright_cyan": (85, 255, 255),
    "bright_white": (255, 255, 255),
    "grey30": (77, 77, 77),
    "grey70": (179, 179, 179),
    "orange1": (255, 135, 0),
}

#: Style words that are not a colour.
_BOLD = {"bold", "b"}
_DIM = {"dim", "d"}
_REVERSE = {"reverse", "reversed", "r"}
_ITALIC = {"italic", "i"}


@dataclass(frozen=True, slots=True)
class Style:
    """A foreground, an optional background, and four flags."""

    fg: RGB = FOREGROUND
    bg: RGB | None = None
    bold: bool = False
    dim: bool = False
    reverse: bool = False
    italic: bool = False


def _hex_colour(word: str) -> RGB | None:
    """``#rgb`` or ``#rrggbb`` as a tuple, or ``None``."""
    digits = word[1:]
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    if len(digits) != 6:
        return None
    try:
        return (
            int(digits[0:2], 16),
            int(digits[2:4], 16),
            int(digits[4:6], 16),
        )
    except ValueError:
        return None


def _colour(word: str) -> RGB | None:
    """A colour from a name or a hex value, or ``None`` if it is not one."""
    if word in NAMED:
        return NAMED[word]
    if word.startswith("#") and len(word) in (4, 7):
        return _hex_colour(word)
    if word.startswith("grey") or word.startswith("gray"):
        digits = word[4:]
        if digits.isdigit():
            level = max(0, min(100, int(digits))) * 255 // 100
            return (level, level, level)
    return None


def parse_style(text: str, base: Style | None = None) -> Style:
    """Read a Rich-ish style string into a :class:`Style`.

    Unknown words are ignored rather than raising: a colour this build has not
    learned is a colour that falls back to the foreground, which is a legible
    screen, and a screen that refuses to draw is not.
    """
    style = base or Style()
    fg = style.fg
    bold, dim, reverse = style.bold, style.dim, style.reverse
    italic = style.italic
    for word in text.replace(",", " ").split():
        word = word.lower()
        if word in _BOLD:
            bold = True
        elif word in _DIM:
            dim = True
        elif word in _REVERSE:
            reverse = True
        elif word in _ITALIC:
            italic = True
        elif word == "on" or word == "not":
            continue
        else:
            colour = _colour(word)
            if colour is not None:
                fg = colour
    return Style(fg=fg, bold=bold, dim=dim, reverse=reverse, italic=italic)


def blend(colour: RGB, other: RGB, amount: float) -> RGB:
    """``colour`` moved ``amount`` of the way toward ``other``.

    The one piece of arithmetic every renderer needs and none of them should
    write twice: ``dim`` fades the phosphor toward the background, and a
    pulsing line breathes by the same sum.
    """
    amount = max(0.0, min(1.0, amount))
    return tuple(
        int(round(a + (b - a) * amount)) for a, b in zip(colour, other)
    )  # type: ignore[return-value]
