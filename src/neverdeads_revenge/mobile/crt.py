"""The two CRT effects that survive 420 ppi -- kept cheap enough to be worth it.

The desktop build drew its CRT with a shader -- a sampling warp, bloom,
scanlines, a vignette. This fork left all of it out, because at 420 ppi a fine
scanline is invisible and a full-resolution bloom is not worth the CPU. What is
here is the part that is visible *and* affordable on a software renderer: lines
coarse enough to read, and a bloom done at a fraction of the size.

Both were too dear on the handheld at first -- bloom cost 2 fps -- and the fix
was to run them once per *change* (baked into the cached frame) and to make each
one cheaper: the scanlines are drawn straight onto the frame instead of being
alpha-blended through an overlay surface, and the bloom is a downscale, a dim,
and a nearest-neighbour upscale, with no separate blur pass.
"""

from __future__ import annotations

import pygame

__all__ = [
    "SCANLINE_ALPHA",
    "SCANLINE_STEP",
    "bloom",
    "scanlines",
]

#: Every Nth row is darkened. Coarse on purpose: at 420 ppi a line every two
#: pixels is invisible, and one every three reads as a texture.
SCANLINE_STEP = 3

#: Kept for the record and for a future alpha overlay; the lines are drawn
#: opaque now, because an alpha overlay was one of the dear things.
SCANLINE_ALPHA = 70


def scanlines(image: pygame.Surface, step: int = SCANLINE_STEP) -> None:
    """Darken every Nth row of ``image``, in place.

    Drawn straight onto the frame rather than blended through a full-screen
    alpha overlay: the overlay was a per-pixel alpha pass over a million and a
    third pixels on every rebuild, which is the sort of thing a software
    renderer on a handheld notices. Opaque lines are a plain write.
    """
    width, height = image.get_size()
    ink = (0, 0, 0)
    for y in range(0, height, step):
        pygame.draw.line(image, ink, (0, y), (width, y))


def bloom(
    image: pygame.Surface,
    *,
    downscale: int = 8,
    intensity: float = 0.5,
) -> None:
    """A soft glow, added back onto ``image`` in place.

    The frame is shrunk, dimmed, and grown again, then added: what the eye reads
    as light spilling is a low-frequency version of the picture, and a
    low-frequency version does not need the pixels. The shrink is the blur --
    there is no separate blur pass -- and the growth is a plain
    nearest-neighbour ``scale``, because the surface is already soft and the
    filtering would only cost time.
    """
    width, height = image.get_size()
    small = pygame.transform.smoothscale(
        image, (max(1, width // downscale), max(1, height // downscale))
    )
    if intensity < 1.0:
        # Dim the glow while it is *small*: the same multiply, on a fraction of
        # the pixels, instead of a full-screen pass.
        level = int(255 * intensity)
        small.fill((level, level, level), special_flags=pygame.BLEND_MULT)
    glow = pygame.transform.scale(small, (width, height))
    image.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)
