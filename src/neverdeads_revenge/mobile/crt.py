"""The CRT effect that survives 420 ppi: a coarse scanline.

The desktop build drew its CRT with a shader -- a sampling warp, bloom,
scanlines, a vignette. This fork left all of it out, because at 420 ppi a fine
scanline is a line nobody can see. The scanline came back; the bloom was tried
twice -- baked into the cached frame, then drawn on the GPU -- and never looked
like anything worth what it cost, so it is gone rather than carried.

What is left is deliberately cheap: a baked pattern of dark rows, multiplied
over the frame.
"""

from __future__ import annotations

import pygame

__all__ = [
    "SCANLINE_LEVEL",
    "SCANLINE_STEP",
    "scanlines",
]

#: Every Nth row is darkened. Coarse on purpose: at 420 ppi a line every two
#: pixels is invisible, and one every three reads as a texture.
SCANLINE_STEP = 3

#: What the darkened rows are multiplied down to, out of 255. Kept for the
#: software path; the GPU bakes the same value into its pattern texture.
SCANLINE_LEVEL = 120


def scanlines(image: pygame.Surface, step: int = SCANLINE_STEP) -> None:
    """Darken every Nth row of ``image``, in place.

    Drawn straight onto the frame rather than blended through a full-screen
    alpha overlay: the overlay was a per-pixel alpha pass over a megapixel on
    every rebuild, which is the sort of thing a software renderer notices.
    Opaque lines are a plain write.
    """
    width, height = image.get_size()
    ink = (0, 0, 0)
    for y in range(0, height, step):
        pygame.draw.line(image, ink, (0, y), (width, y))
