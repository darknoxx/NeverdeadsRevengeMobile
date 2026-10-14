"""The CRT on the GPU, for a handheld that has one.

The scanline is a full-screen multiply, and on a *software* renderer that is
paid in CPU; SDL's render API is OpenGL ES on Android, where it is nearly free.
The frame is uploaded once per change, the particles are drawn as rectangles
(right on the GPU, so a blood burst does not re-upload a megapixel a frame), and
the scanline is one multiply with a baked pattern.

It is deliberately optional. The window and the renderer are tried once, and if
either cannot be made -- no GL, an old driver, a desktop that refuses -- the app
keeps the software path it had before. :class:`GpuView` therefore knows nothing
about the game: it is handed a finished frame, the particles still floating, and
two switches.
"""

from __future__ import annotations

import pygame

from .crt import SCANLINE_LEVEL, SCANLINE_STEP

__all__ = ["GpuView"]


class GpuView:
    """A window and a renderer, with the scanlines as one draw."""

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
        self._scan_tex = None
        self._overlay_tex = None

    # -- textures that are made once ----------------------------------------
    def _scanlines(self):
        if self._scan_tex is None:
            surface = pygame.Surface(self.size)
            surface.fill((255, 255, 255))
            for y in range(0, self.size[1], SCANLINE_STEP):
                pygame.draw.line(
                    surface, (SCANLINE_LEVEL,) * 3, (0, y), (self.size[0], y)
                )
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
        scanlines: bool = False,
        overlay=None,
    ) -> None:
        """Put ``frame`` on the screen, dressed, and present it."""
        renderer = self.renderer
        renderer.draw_blend_mode = pygame.BLENDMODE_NONE
        renderer.draw_color = (0, 0, 0, 255)
        renderer.clear()

        origin = (offset[0] + shake[0], offset[1] + shake[1])
        self._frame(frame).draw(dstrect=pygame.Rect(origin, frame.get_size()))

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

        if scanlines:
            self._scanlines().draw(dstrect=pygame.Rect((0, 0), self.size))

        overlay_tex = self._overlay(overlay)
        if overlay_tex is not None:
            overlay_tex.draw(dstrect=pygame.Rect((0, 0), overlay.get_size()))

        renderer.present()

    # -- for the screenshot path and for tests ------------------------------
    def snapshot(self) -> pygame.Surface:
        return self.renderer.to_surface()
