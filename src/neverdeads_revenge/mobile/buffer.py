"""The grid of characters, and the picture it becomes.

The same idea as the desktop build's buffer, and deliberately the same API:
the screens write ``buffer.text(x, y, "FLOOR 3", parse_style("bold"))`` and do
not care which renderer is underneath. What changes here is the output: a
pygame surface instead of a QImage, and a glyph cache instead of Qt's own.

A cell remembers the background it was written onto, so a word drawn over a
panel keeps the panel -- that is what keeps a menu from being a stripe of black
through the middle of itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from .font import BitmapFont
from .theme import BACKGROUND, Style

__all__ = ["Cell", "PatternBuffer"]


@dataclass(slots=True)
class Cell:
    """One square of the grid."""

    char: str = " "
    style: Style = field(default_factory=Style)


class PatternBuffer:
    """A grid of characters that renders to one surface."""

    def __init__(self, cols: int, rows: int, font: BitmapFont) -> None:
        self.cols = cols
        self.rows = rows
        self.font = font
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(cols)] for _ in range(rows)
        ]

    def clear(self) -> None:
        for row in self.cells:
            for cell in row:
                cell.char = " "
                cell.style = Style()

    def put(self, x: int, y: int, char: str, style: Style | None = None) -> None:
        if 0 <= x < self.cols and 0 <= y < self.rows:
            cell = self.cells[y][x]
            new = style or Style()
            if new.bg is None and cell.style.bg is not None:
                # The cell already sits on a panel. Writing a *word* onto it
                # does not lift the panel out from under the writing: the text
                # keeps the background the square had.
                new = Style(
                    fg=new.fg,
                    bg=cell.style.bg,
                    bold=new.bold,
                    dim=new.dim,
                    reverse=new.reverse,
                    italic=new.italic,
                )
            cell.char = char
            cell.style = new

    def text(self, x: int, y: int, string: str, style: Style | None = None) -> int:
        """Write ``string`` starting at ``x``. Returns the next free column.

        Characters past the right edge are dropped rather than wrapped: every
        line in this game is positioned by hand, and a wrap is a line that
        lands somewhere the screen did not ask for.
        """
        style = style or Style()
        column = x
        for char in string:
            if column >= self.cols:
                break
            self.put(column, y, char, style)
            column += 1
        return column

    # -- the picture ---------------------------------------------------------
    def render(self) -> pygame.Surface:
        """Paint every cell onto one surface, glyph by glyph, from the cache."""
        font = self.font
        image = pygame.Surface(
            (self.cols * font.cell_w, self.rows * font.cell_h)
        )
        image.fill(BACKGROUND)
        cell_w, cell_h = font.cell_w, font.cell_h
        for y, row in enumerate(self.cells):
            top = y * cell_h
            for x, cell in enumerate(row):
                style = cell.style
                left = x * cell_w
                if style.bg is not None:
                    image.fill(style.bg, (left, top, cell_w, cell_h))
                if cell.char != " ":
                    image.blit(font.glyph(cell.char, style), (left, top))
        return image
