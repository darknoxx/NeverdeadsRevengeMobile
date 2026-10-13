"""The handheld's app: one window, one run, and the loop that draws them.

Phase one of the port, and deliberately small: the game screen, the HUD, the
log, and the keys that drive a turn. The menus -- title, shop, sheet, legend,
pack, the whole stack -- come next, and they will come almost unchanged,
because they were written against a *buffer* and a set of key names rather
than against a toolkit.

The frame is cached. A turn-based game redraws when something *happened*, and
the only things that need a repaint between turns are the particles and the
breathing ultimate line -- so the buffer is rebuilt on a turn and re-blitted
otherwise. On a Snapdragon 865 that is the difference between a game and a
space heater.
"""

from __future__ import annotations

import random
import time

import pygame

from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.state import GameState, start_run

from .buffer import PatternBuffer
from .font import BitmapFont
from .input import button_name, key_name, stick_direction
from .keys import KEY_BINDINGS
from .render import draw_game, regions, screen_point

__all__ = ["MobileApp", "ZOOMS", "GRID_FOR"]

#: The three zooms, as the font's pixel size. The grid follows from the font's
#: own metrics -- a cell is about six tenths as wide as it is tall, so a "cell
#: size" in pixels is a number that would lie about the grid it produces.
ZOOMS: dict[str, int] = {"S": 20, "M": 27, "L": 36}

#: The device's screen. The frame is centred inside it and the remainder is
#: black: at these zooms the leftover is 0 to 24 pixels, which is a bezel.
SCREEN = (1240, 1080)


def GRID_FOR(font: BitmapFont) -> tuple[int, int]:
    """The grid the font's metrics allow on the device's screen."""
    return SCREEN[0] // font.cell_w, SCREEN[1] // font.cell_h


class MobileApp:
    """The window, the run, and the loop between them."""

    def __init__(
        self,
        *,
        zoom: str = "M",
        seed: int | None = None,
        hero: str = "noxx",
        headless: bool = False,
        scale: float = 1.0,
    ) -> None:
        pygame.init()
        pygame.joystick.init()
        pygame.display.set_caption("Neverdead's Revenge")
        self.headless = headless
        self.pixel_size = ZOOMS[zoom]
        self.font = BitmapFont(self.pixel_size)
        self.cols, self.rows = GRID_FOR(self.font)
        self.buffer = PatternBuffer(self.cols, self.rows, self.font)
        self.frame = (
            self.cols * self.font.cell_w,
            self.rows * self.font.cell_h,
        )
        #: How much of the device's screen the *window* shows. Development on a
        #: desktop wants the whole frame at half size rather than a 1080-tall
        #: window on a laptop; on the handheld this is 1.0 and the window is
        #: the screen.
        self.scale = scale
        self.window_size = (
            max(1, int(SCREEN[0] * scale)),
            max(1, int(SCREEN[1] * scale)),
        )
        self.screen = None
        if not headless:
            self.screen = pygame.display.set_mode(self.window_size)
        self.offset = (
            (SCREEN[0] - self.frame[0]) // 2,
            (SCREEN[1] - self.frame[1]) // 2,
        )
        if seed is None:
            seed = random.SystemRandom().randrange(2**32)
        self.seed = seed
        self.run: GameState = start_run(HEROES[hero], seed)
        self._dirty = True
        self._last_move: dict[str, float] = {}
        self.joysticks = [
            pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())
        ]
        for stick in self.joysticks:
            stick.init()
        self._stick_held: str | None = None

    # -- the picture ---------------------------------------------------------
    def redraw(self) -> None:
        draw_game(self.buffer, self.run, time.time())
        image = self.buffer.render()
        if self.screen is not None:
            self.screen.fill((0, 0, 0))
            if self.scale == 1.0:
                self.screen.blit(image, self.offset)
            else:
                # Scaled for a smaller window, and *smoothly*: this is the one
                # place the game is allowed to blur, because it is a preview of
                # the device rather than the device.
                self.screen.blit(
                    pygame.transform.smoothscale(image, self.window_size), (0, 0)
                )
            pygame.display.flip()
        self._dirty = False

    def screenshot(self, path: str) -> None:
        """Render one frame to a file, without a window.

        The frame is *centred on the device screen* before saving, so the
        picture is what the handheld would show -- bars included.
        """
        draw_game(self.buffer, self.run, time.time())
        image = pygame.Surface(SCREEN)
        image.fill((0, 0, 0))
        image.blit(self.buffer.render(), self.offset)
        pygame.image.save(image, path)

    # -- input ---------------------------------------------------------------
    def _act(self, name: str) -> None:
        """Do what a key name means, for the game screen's own verbs."""
        action = KEY_BINDINGS.get(name)
        if action is None:
            return
        result = perform_action(self.run, action)
        self._dirty = True
        if result.prompt is not None:
            # Phase one has no dialogs yet. The engine asks, the app answers
            # cautiously: take the fame, wash the curse, let the person talk.
            if result.prompt_kind == "chest":
                perform_action(
                    self.run,
                    Action.OPEN_CHEST if self.run.player.hp > self.run.player.max_hp * 0.5 else Action.TAKE_FAME,
                )
            elif result.prompt_kind == "spring" and self.run.curses:
                perform_action(self.run, Action.CLEANSE)

    def handle(self, event) -> bool:
        """Handle one event. Returns ``True`` if the app should keep running."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and event.mod & pygame.KMOD_CTRL:
                return False
            name = key_name(event)
            if name is not None:
                self._act(name)
        elif event.type == pygame.JOYBUTTONDOWN:
            name = button_name(event.button)
            if name is not None:
                self._act(name)
        elif event.type == pygame.JOYHATMOTION:
            # The D-pad, as a hat: one direction per press, which is what a
            # d-pad is -- the stick is the thing that can be pushed harder.
            x, y = event.value
            direction = {
                (0, 1): "down", (0, -1): "up", (-1, 0): "left", (1, 0): "right",
                (-1, 1): "sw", (1, 1): "se", (-1, -1): "nw", (1, -1): "ne",
            }.get((x, y))
            if direction is not None:
                self._act(direction)
        return True

    def poll_stick(self, now: float) -> None:
        """A pushed stick walks, at the hero's own pace.

        Read on the clock rather than on events because a stick is not a key:
        it has no "press", only a position, and a held position has to repeat
        itself or the player pushes it once per square.
        """
        for stick in self.joysticks:
            direction = stick_direction(stick)
            if direction is None:
                self._stick_held = None
                continue
            if direction != self._stick_held:
                self._stick_held = direction
                self._act(direction)
                self._last_move[direction] = now
                continue
            if now - self._last_move.get(direction, 0.0) >= 0.12:
                self._act(direction)
                self._last_move[direction] = now

    # -- the loop ------------------------------------------------------------
    def loop(self) -> None:
        clock = pygame.time.Clock()
        running = True
        while running:
            now = time.monotonic()
            for event in pygame.event.get():
                if not self.handle(event):
                    running = False
            self.poll_stick(now)
            if self._dirty:
                self.redraw()
            clock.tick(60)
        pygame.quit()
