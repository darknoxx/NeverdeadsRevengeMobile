"""The CRT on the GPU, for a handheld that has one.

The bloom and the scanlines are full-screen operations, and on a *software*
renderer every one of them is paid in CPU: on this handheld that was the
difference between a playable game and two frames a second. SDL's render API is
OpenGL ES on Android, so bloom (a downscale, a dim and an additive upscale) and
scanlines (a multiply with a baked pattern) cost almost nothing there.

It is deliberately optional. The window and the renderer are tried once, and if
either cannot be made -- an old driver, no GL, a desktop that refuses -- the app
keeps the software path it had before, with the CRT baked into the cached frame.
:class:`GpuView` therefore knows nothing about the game: it is handed a finished
frame, the particles still floating, and three switches.
"""

from __future__ import annotations

import pygame

__all__ = ["GpuView"]

#: The bloom is a fifth of the screen: a blur is a blur at a fifth of the size,
#: and the cost of one is the size of the surface it runs on.
_BLOOM_DIVISOR = 5
#: How bright the added glow is, out of 255. A hint, not a wash -- but it has to
#: be a hint that can be seen at all.
_BLOOM_LEVEL = 150
#: The scanline pattern: every third row is multiplied down to this.
_SCANLINE_STEP = 3
_SCANLINE_LEVEL = 120


class GpuView:
    """A window and a renderer, with the CRT as three draws."""

    def __init__(self, size: tuple[int, int], *, fullscreen: bool = True) -> None:
        from pygame._sdl2 import video as sdl2

        self._sdl2 = sdl2
        self.window = sdl2.Window(
            "Neverdead's Revenge", size=size, fullscreen=fullscreen
        )
        self.renderer = sdl2.Renderer(self.window)
        #: The drawable size the driver actually gave us.
        self.size = tuple(self.window.size)
        self.renderer.draw_blend_mode = pygame.BLENDMODE_NONE

        self._frame_tex = None
        self._frame_size = None
        self._bloom = sdl2.Texture(
            self.renderer,
            (max(1, self.size[0] // _BLOOM_DIVISOR), max(1, self.size[1] // _BLOOM_DIVISOR)),
            target=True,
        )
        self._bloom.blend_mode = pygame.BLENDMODE_ADD
        self._bloom.color = (_BLOOM_LEVEL, _BLOOM_LEVEL, _BLOOM_LEVEL)
        self._scan_tex = None
        self._overlay_tex = None

    # -- textures that are made once ----------------------------------------
    def _scanlines(self):
        if self._scan_tex is None:
            surface = pygame.Surface(self.size)
            surface.fill((255, 255, 255))
            for y in range(0, self.size[1], _SCANLINE_STEP):
                pygame.draw.line(surface, (_SCANLINE_LEVEL,) * 3, (0, y), (self.size[0], y))
            self._scan_tex = self._sdl2.Texture.from_surface(self.renderer, surface)
            self._scan_tex.blend_mode = pygame.BLENDMODE_MUL
        return self._scan_tex

    def _frame(self, surface):
        if self._frame_tex is None or self._frame_size != surface.get_size():
            self._frame_tex = self._sdl2.Texture.from_surface(self.renderer, surface)
            self._frame_size = surface.get_size()
        else:
            self._frame_tex.update(surface)
        return self._frame_tex

    def _overlay(self, surface):
        if surface is None:
            self._overlay_tex = None
            return None
        if self._overlay_tex is None or self._overlay_tex.get_rect().size != surface.get_size():
            self._overlay_tex = self._sdl2.Texture.from_surface(self.renderer, surface)
        else:
            self._overlay_tex.update(surface)
        return self._overlay_tex

    # -- the one call the app makes -----------------------------------------
    def show(
        self,
        frame,
        *,
        offset: tuple[int, int],
        shake: tuple[int, int] = (0, 0),
        particles=(),
        bloom: bool = False,
        scanlines: bool = False,
        overlay=None,
    ) -> None:
        """Put ``frame`` on the screen, dressed, and present it."""
        renderer = self.renderer
        renderer.draw_blend_mode = pygame.BLENDMODE_NONE
        renderer.draw_color = (0, 0, 0, 255)
        renderer.clear()

        origin = (offset[0] + shake[0], offset[1] + shake[1])
        size = frame.get_size()
        renderer.draw_blend_mode = pygame.BLENDMODE_NONE
        self._frame(frame).draw(dstrect=pygame.Rect(origin, size))

        # Particles are drawn *here* rather than onto the frame, so a blood burst
        # does not mean re-uploading a megapixel every frame.
        if particles:
            for particle in particles:
                colour = particle.colour
                renderer.draw_color = (*colour[:3], 255)
                renderer.fill_rect(
                    pygame.Rect(
                        int(origin[0] + particle.x),
                        int(origin[1] + particle.y),
                        max(1, particle.size),
                        max(1, particle.size),
                    )
                )
            renderer.draw_color = (0, 0, 0, 255)

        if bloom:
            self._draw_bloom()

        if scanlines:
            self._scanlines().draw(dstrect=pygame.Rect((0, 0), self.size))

        overlay_tex = self._overlay(overlay)
        if overlay_tex is not None:
            overlay_tex.draw(dstrect=pygame.Rect((0, 0), overlay.get_size()))

        renderer.present()

    def _draw_bloom(self) -> None:
        """The frame, shrunk into the bloom target, added back over itself."""
        renderer = self.renderer
        renderer.target = self._bloom
        renderer.draw_blend_mode = pygame.BLENDMODE_NONE
        renderer.draw_color = (0, 0, 0, 255)
        renderer.clear()
        self._frame_tex.draw(
            dstrect=pygame.Rect(0, 0, self._bloom.width, self._bloom.height)
        )
        renderer.target = None
        self._bloom.draw(dstrect=pygame.Rect((0, 0), self.size))

    # -- for the screenshot path and for tests ------------------------------
    def snapshot(self) -> pygame.Surface:
        return self.renderer.to_surface()
