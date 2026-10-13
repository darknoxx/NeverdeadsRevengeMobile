"""The two CRT effects that survive 420 ppi: a coarse scanline and a soft bloom.

The desktop build drew its CRT with a shader -- a sampling warp, bloom,
scanlines, a vignette -- and this fork left all of it out, because at 420 ppi a
fine scanline is a line nobody can see and a full-resolution bloom is not worth
the CPU. What is here is the part that *is* visible and *is* affordable on a
software renderer: lines coarse enough to read, and a bloom done at a quarter of
the size, because a blur is a blur at a quarter of the size and the cost of one
is the size of the surface it runs on.
"""

from __future__ import annotations

import pygame

__all__ = [
    "SCANLINE_ALPHA",
    "SCANLINE_STEP",
    "bloom",
    "scanline_overlay",
]

#: Every Nth row is darkened. Coarse on purpose: at 420 ppi a line every two
#: pixels is invisible, and one every three reads as a texture rather than as a
#: grid.
SCANLINE_STEP = 3

#: How dark the lines are, out of 255. Gentle: this is a CRT hint, not a curtain.
SCANLINE_ALPHA = 70


def scanline_overlay(
    size: tuple[int, int],
    step: int = SCANLINE_STEP,
    alpha: int = SCANLINE_ALPHA,
) -> pygame.Surface:
    """A ready-to-blit surface of dark rows -- built once, not per frame."""
    overlay = pygame.Surface(size, pygame.SRCALPHA)
    line = (0, 0, 0, alpha)
    for y in range(0, size[1], step):
        pygame.draw.line(overlay, line, (0, y), (size[0], y))
    return overlay


def bloom(
    image: pygame.Surface,
    *,
    downscale: int = 6,
    radius: int = 3,
    intensity: float = 0.55,
) -> None:
    """A soft glow, added back onto ``image`` in place.

    The frame is shrunk, blurred, and grown again, then added: what the eye
    reads as light spilling is a low-frequency version of the picture, and a
    low-frequency version does not need the pixels. ``intensity`` scales it back
    down before it is added, so the glow is a hint and not a wash.

    The *growth* is a plain nearest-neighbour ``scale``, not a smooth one: the
    surface is already blurred, so filtering it again would only cost time --
    and on the handheld the smooth upscale was a large part of why bloom was
    unplayable.
    """
    width, height = image.get_size()
    small = pygame.transform.smoothscale(
        image, (max(1, width // downscale), max(1, height // downscale))
    )
    blurred = pygame.Surface(small.get_size())
    pygame.transform.box_blur(small, radius, dest_surface=blurred)
    if intensity < 1.0:
        # Dim the glow while it is *small*: the same multiply, on a fraction of
        # the pixels, instead of a full-screen pass.
        level = int(255 * intensity)
        blurred.fill((level, level, level), special_flags=pygame.BLEND_MULT)
    glow = pygame.transform.scale(blurred, (width, height))
    image.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)
