"""A monospaced cell, drawn with pygame, without antialiasing.

The desktop build asks Qt for a font and measures a cell with QFontMetrics.
Here it is pygame's font, with the same two faces (regular and bold) and the
same rule: a glyph is drawn *without* antialiasing, because a phosphor either
lit a pixel or it did not, and a blurred character on a 420 ppi panel is the
one thing this screen does not need help with.

Everything is cached. A frame is up to 3,348 cells, and rendering the same
"the" sixty times a second is the difference between a game and a slide show.
"""

from __future__ import annotations

from pathlib import Path

import pygame

from .theme import BACKGROUND, FOREGROUND, Style, blend

__all__ = ["BitmapFont", "FONT_DIR"]

#: Where the faces travel with the game. On Android a font has to be inside
#: the package: the system's fonts are not ours to assume.
FONT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"


class BitmapFont:
    """The four faces the game draws with, and the metrics of one cell."""

    def __init__(self, pixel_size: int, font_dir: Path | None = None) -> None:
        if not pygame.font.get_init():
            pygame.font.init()
        base = font_dir or FONT_DIR
        self.pixel_size = pixel_size
        self.normal = pygame.font.Font(str(base / "DejaVuSansMono.ttf"), pixel_size)
        self.bold = pygame.font.Font(
            str(base / "DejaVuSansMono-Bold.ttf"), pixel_size
        )
        self.italic = pygame.font.Font(
            str(base / "DejaVuSansMono-Oblique.ttf"), pixel_size
        )
        self.bold_italic = pygame.font.Font(
            str(base / "DejaVuSansMono-BoldOblique.ttf"), pixel_size
        )
        #: Width of one cell. The widest of the characters that must never be
        #: clipped, so a monospace face cannot lie about a wide glyph.
        self.cell_w = max(
            self.normal.size(char)[0] for char in "MWi0@#"
        )
        #: Height of one cell, plus a pixel: a descender must not be shaved.
        self.cell_h = self.normal.get_height() + 1
        self._glyphs: dict[tuple, pygame.Surface] = {}

    # -- the faces -----------------------------------------------------------
    def face(self, style: Style) -> pygame.font.Font:
        if style.bold and style.italic:
            return self.bold_italic
        if style.bold:
            return self.bold
        if style.italic:
            return self.italic
        return self.normal

    # -- one glyph -----------------------------------------------------------
    def glyph(self, char: str, style: Style) -> pygame.Surface:
        """A ready-to-blit surface for ``char`` in ``style``, from the cache.

        ``dim`` is folded into the ink rather than drawn as a translucent
        surface: the phosphor fades toward the background, and alpha would let
        the panel's own light through instead.
        """
        ink = style.fg
        if style.dim:
            ink = blend(ink, BACKGROUND, 0.45)
        key = (char, ink, style.bold, style.italic, style.reverse)
        cached = self._glyphs.get(key)
        if cached is not None:
            return cached

        surface = pygame.Surface((self.cell_w, self.cell_h), pygame.SRCALPHA)
        if style.reverse:
            # A struck square: the cell is ink and the glyph is the hole in it.
            surface.fill(style.fg)
            pen = style.bg if style.bg is not None else BACKGROUND
            if style.dim:
                pen = blend(pen, style.fg, 0.45)
        else:
            pen = ink
        rendered = self.face(style).render(char, False, pen)
        surface.blit(rendered, (0, 0))
        self._glyphs[key] = surface
        return surface

    def clear_cache(self) -> None:
        """Drop the cache. For a resize, or a palette that moved."""
        self._glyphs.clear()


#: Kept so a caller that wants the plain foreground does not import the theme.
DEFAULT_INK = FOREGROUND
