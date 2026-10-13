"""The handheld's app: one window, one run, a stack of screens, and the loop.

The screens were written against a *buffer* and a set of key names, not against
a toolkit -- so this file is where the toolkit lives, and everything above it
is the same code the desktop build runs. What it has to provide is exactly what
the screens ask for: a stack, the progress record, the sound, the particles,
and a camera the effects can ask where a square ended up on the screen.

Three things are the handheld's own:

* The frame is cached. A turn-based game redraws when something *happened*;
  between turns only the particles and the breathing ultimate line move, and
  those are cheap. On a Snapdragon that is the difference between a game and a
  space heater.
* Movement is *polled*, not evented: a stick and a held d-pad have a position,
  not a press, so the app reads them on the clock and repeats at the hero's own
  pace. Every other verb is one press, one action -- the rule every other build
  keeps.
* The pad is the first-class citizen and the keyboard is the stand-in, which is
  the reverse of the desktop build and the right way round for a handheld.
"""

from __future__ import annotations

import os
import random
import time

import pygame

from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game.actions import Action, perform_action
from neverdeads_revenge.game.actors import HEROES
from neverdeads_revenge.game.lore import PAGE_COUNT
from neverdeads_revenge.game.pace import action_gap
from neverdeads_revenge.game.savegame import dump, load
from neverdeads_revenge.game.shop import loadout_from
from neverdeads_revenge.game.state import GameState, RunState, start_run
from neverdeads_revenge.persistence import (
    MetaProgress,
    clear_run,
    load_meta,
    load_run,
    save_meta,
    save_run,
)

from .audio import Sfx, loudest_kind, sound_for_kind
from .buffer import PatternBuffer
from .effects import Effects, Shake
from .font import BitmapFont
from .input import KeyEvent, button_name, key_name
from .render import draw_game, regions, screen_point
from .screens.game import GameScreen
from .screens.title import TitleScreen

__all__ = ["MobileApp", "ZOOMS", "GRID_FOR"]

#: The three zooms, as the font's pixel size. The grid follows from the font's
#: own metrics -- a cell is about six tenths as wide as it is tall, so a "cell
#: size" in pixels is a number that would lie about the grid it produces.
ZOOMS: dict[str, int] = {"S": 20, "M": 27, "L": 36}

#: The device's screen. The frame is centred inside it and the remainder is
#: black: at these zooms the leftover is 0 to 24 pixels, which is a bezel.
SCREEN = (1240, 1080)

#: The directions the *poll* owns: a stick has a position and a d-pad a hat, so
#: neither sends a press the event loop could count -- and an arrow key is read
#: the same way for the same reason. Everything else (buttons, letters, the
#: shortcuts the menus answer) arrives as an event, one press one action.
POLLED_DIRECTIONS = frozenset({"up", "down", "left", "right"})

#: How long a held direction moves once before it starts repeating, in seconds.
#: A keyboard's auto-repeat delay, and it is here for the same reason: a tap
#: should be one step however long the finger lingers, and only a *hold* should
#: walk. Too short and a tap overshoots; too long and holding feels stuck.
_REPEAT_DELAY = 0.30

#: A direction lost and found again within this window is one hold, not two:
#: the stick crossed the deadzone, the player did not press twice.
_RELEASE_GRACE = 0.10

#: How long a held button waits before the app starts feeding it repeats, in
#: seconds. A keyboard's auto-repeat delay, and it is what keeps a tap a tap:
#: shorter than this and the hold's own tap rule (a brief press that never
#: repeated banks nothing) would never see an unrepeated press. Above
#: ``hold.TAP_SECONDS`` with room to spare, so the two cannot disagree.
_HOLD_REPEAT_DELAY = 0.30

#: How often the synthetic repeat stream ticks once it has started, in seconds.
#: The fill is wall-clock time, so this only sets how smoothly the bar moves and
#: how finely completion is timed; twenty a second is smoother than an eye.
_HOLD_REPEAT_RATE = 0.05

#: Android's lifecycle events. pygame names them and a desktop never sends one;
#: guarded so a pygame without them cannot break the import. -1 is not an event
#: type SDL ever uses, so the comparisons stay false on a desktop.
_APP_WILLENTERBACKGROUND = getattr(pygame, "APP_WILLENTERBACKGROUND", -1)
_APP_DIDENTERFOREGROUND = getattr(pygame, "APP_DIDENTERFOREGROUND", -1)
_APP_TERMINATING = getattr(pygame, "APP_TERMINATING", -1)


def _on_android() -> bool:
    """Whether this is running inside a python-for-android package.

    p4a sets ``ANDROID_ARGUMENT`` (and ``ANDROID_PRIVATE``) before the app
    starts, and a desktop sets neither -- so this is the honest test for "there
    is a handheld under me", and it is what turns on fullscreen.
    """
    return any(
        name in os.environ
        for name in ("ANDROID_ARGUMENT", "ANDROID_PRIVATE", "ANDROID_APP_PATH")
    )


def GRID_FOR(font: BitmapFont, size: tuple[int, int] = SCREEN) -> tuple[int, int]:
    """The grid the font's metrics allow on a screen of ``size``."""
    return size[0] // font.cell_w, size[1] // font.cell_h


class MobileApp:
    """The window, the run, the stack, and the loop between them."""

    def __init__(
        self,
        *,
        zoom: str = "M",
        seed: int | None = None,
        hero: str = "noxx",
        headless: bool = False,
        scale: float = 1.0,
        no_sound: bool = False,
        testrun: bool = False,
    ) -> None:
        pygame.init()
        pygame.joystick.init()
        pygame.display.set_caption("Neverdead's Revenge")
        self.headless = headless
        self.pixel_size = ZOOMS[zoom]
        self.font = BitmapFont(self.pixel_size)
        self.scale = scale
        self.screen = None
        if headless:
            # No window at all: screenshots are taken at the device's size.
            self.surface_size = SCREEN
        elif _on_android():
            # A handheld is always fullscreen, and the *real* surface is
            # whatever the panel and the system bars leave. Asking SDL for the
            # screen rather than assuming 1240x1080 is what keeps the bottom of
            # the frame from being cut off.
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            size = self.screen.get_size()
            # A driver that answers (0,0) with (0,0) must not make a zero grid.
            self.surface_size = size if min(size) > 100 else SCREEN
        else:
            requested = (
                max(1, int(SCREEN[0] * scale)),
                max(1, int(SCREEN[1] * scale)),
            )
            self.screen = pygame.display.set_mode(requested)
            self.surface_size = requested
        self.window_size = self.surface_size
        self.cols, self.rows = GRID_FOR(self.font, self.surface_size)
        self._buffer = PatternBuffer(self.cols, self.rows, self.font)
        self.frame = (self.cols * self.font.cell_w, self.rows * self.font.cell_h)
        self.offset = (
            (self.surface_size[0] - self.frame[0]) // 2,
            (self.surface_size[1] - self.frame[1]) // 2,
        )

        # -- the game's own state --------------------------------------------
        self.progress = load_meta()
        self.seed = seed if seed is not None else random.SystemRandom().randrange(2**32)
        self.seed_locked = seed is not None
        self.testrun = testrun
        self.run: GameState | None = None
        self.prologue_seen = False
        self.sfx = Sfx(muted=no_sound or self.progress.muted)
        self.effects = Effects(self.font.cell_w, self.font.cell_h)
        self.shake = Shake()
        #: What the screens call ``app.view``. On the desktop it is the CRT
        #: widget and shaking it warps the sampling; here it is the frame's own
        #: jitter, and it answers the same two questions -- shake(), and
        #: is_shaking() -- so the game screen did not have to be touched.
        self.view = self.shake
        self.screens: list = [TitleScreen()]
        self._seen_log = 0
        self._dirty = True
        self._quit = False

        # -- input ------------------------------------------------------------
        self.joysticks = [
            pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())
        ]
        for stick in self.joysticks:
            stick.init()
        self._held_dir: str | None = None
        self._last_repeat = 0.0
        #: When a hold may start repeating. A press moves at once and then
        #: waits, the way a keyboard's auto-repeat does -- without the wait a
        #: tap that lasted one frame too long moved twice, which is a player
        #: who overshoots the square they aimed at.
        self._repeat_from = 0.0
        #: The direction last *pressed*, and when it was last lost, so a stick
        #: flickering across the deadzone is read as one hold and not two.
        self._last_dir: str | None = None
        self._released_at = 0.0
        #: Buttons currently down. SDL reports a press and a release and no
        #: repeat between them -- which the holds in the game need (see
        #: :meth:`poll_holds`).
        self._buttons_down: set[int] = set()
        self._last_hold_repeat = 0.0
        #: When the current hold's key went down, so the repeat stream can wait
        #: before it starts -- see :meth:`poll_holds`.
        self._hold_down_at: float | None = None
        #: The Android wake lock, if this build could take one. See
        #: :meth:`_acquire_wakelock`.
        self._wakelock = None

    # -- the stack -----------------------------------------------------------
    def push(self, screen) -> None:
        self.screens.append(screen)
        self._dirty = True

    def pop(self) -> None:
        if len(self.screens) > 1:
            self.screens.pop()
        self._dirty = True

    # -- the picture ---------------------------------------------------------
    def redraw(self) -> None:
        self._buffer.clear()
        # An opaque modal: nothing under it is drawn. A menu is a panel, not a
        # window onto the dungeon, so the topmost modal starts the stack.
        start = 0
        for index, screen in enumerate(self.screens):
            if getattr(screen, "modal", False):
                start = index
        for screen in self.screens[start:]:
            screen.draw(self._buffer, self)
        image = self._buffer.render()
        self.effects.draw(image)
        if self.screen is not None:
            dx, dy = self.shake.offset()
            self.screen.fill((0, 0, 0))
            if self.scale == 1.0:
                self.screen.blit(image, (self.offset[0] + dx, self.offset[1] + dy))
            else:
                scaled = pygame.transform.smoothscale(image, self.window_size)
                self.screen.blit(scaled, (dx, dy))
            pygame.display.flip()
        self._dirty = False

    def screenshot(self, path: str) -> None:
        """Render one frame to a file, without a window."""
        self._buffer.clear()
        start = 0
        for index, screen in enumerate(self.screens):
            if getattr(screen, "modal", False):
                start = index
        for screen in self.screens[start:]:
            screen.draw(self._buffer, self)
        # Particles go on the *frame*, exactly as redraw does it, so the two
        # cannot disagree about where a sparkle lands.
        frame = self._buffer.render()
        self.effects.draw(frame)
        image = pygame.Surface(self.surface_size)
        image.fill((0, 0, 0))
        image.blit(frame, self.offset)
        pygame.image.save(image, path)

    # -- the screens' app surface --------------------------------------------
    def screen_point(self, position) -> tuple[float, float] | None:
        """The pixel centre of a dungeon square on the current frame, if it is
        on the screen."""
        if self.run is None:
            return None
        return screen_point(
            self.run,
            position,
            self._buffer.cols,
            self._buffer.rows,
            self.font.cell_w,
            self.font.cell_h,
        )

    def play(self, name: str | None) -> None:
        if name:
            self.sfx.play(name)

    def play_after(self, before: tuple[int, int, int]) -> None:
        """Make the noise the last thing that happened deserves."""
        run = self.run
        if run is None or run.over:
            return
        before_log, before_depth, before_level = before
        if run.depth != before_depth:
            self.play("stairs")
            return
        if run.level != before_level:
            self.play("level")
            return
        kind = loudest_kind(entry.kind for entry in run.log[before_log:])
        self.play(sound_for_kind(kind) if kind is not None else None)

    def save_progress(self) -> None:
        try:
            save_meta(self.progress)
        except OSError:
            pass

    def has_saved_run(self) -> bool:
        return load_run() is not None

    def record_run(self, state, name: str = "") -> int:
        self.progress.record_run(
            depth=state.depth,
            score=state.score,
            kills=state.kills,
            gold=state.gold,
            won=state.run_state is RunState.ESCAPED,
            name=name,
            hero=state.hero.key,
        )
        self.progress.reroll_wilds(Rng(random.SystemRandom().randrange(2**32)))
        self.save_progress()
        return self.progress.best_score

    def toggle_sound(self) -> None:
        self.sfx.toggle()
        self.progress.muted = self.sfx.muted
        self.save_progress()

    # -- navigation ----------------------------------------------------------
    def return_to_title(self) -> None:
        self.run = None
        self.effects.clear()
        self.screens = [TitleScreen()]
        self.redraw()

    def open_hero_select(self) -> None:
        from .screens.hero_select import HeroSelectScreen

        self.push(HeroSelectScreen())

    def open_shop(self) -> None:
        from .screens.menus import ShopScreen

        self.push(ShopScreen())

    def open_scoreboard(self) -> None:
        from .screens.menus import ScoreboardScreen

        self.push(ScoreboardScreen())

    def open_chronicle(self) -> None:
        from .screens.menus import ChronicleScreen

        self.push(ChronicleScreen())

    def open_delete_progress(self) -> None:
        from .screens.dialogs import DeleteProgressScreen

        self.push(
            DeleteProgressScreen(
                on_done=lambda confirmed: self.delete_progress() if confirmed else None
            )
        )

    def delete_progress(self) -> None:
        """Wipe the profile and the saved run. Nothing is kept back."""
        self.progress = MetaProgress()
        self.save_progress()
        clear_run()
        self.run = None
        self._dirty = True

    def begin_run(self, hero_key: str) -> None:
        if not self.prologue_seen:
            # The premise, told once, between the choice and the floor.
            self.prologue_seen = True
            from .screens.prologue import PrologueScreen

            self.push(PrologueScreen(on_done=lambda: self.begin_run(hero_key)))
            return
        if not self.seed_locked:
            self.seed = random.SystemRandom().randrange(2**32)
        loadout = loadout_from(self.progress)
        self.save_progress()
        missing = tuple(
            number
            for number in range(1, PAGE_COUNT + 1)
            if number not in self.progress.pages
        )
        self.run = start_run(
            HEROES[hero_key],
            self.seed,
            loadout=loadout,
            pages=missing,
            ultimate_level=1 if self.testrun else None,
        )
        self._seen_log = 0
        self.effects.clear()
        self.screens = [GameScreen(self.run)]
        self.redraw()

    def continue_run(self) -> None:
        payload = load_run()
        if not payload:
            return
        try:
            state = load(payload)
        except Exception:
            clear_run()
            return
        clear_run()
        self.run = state
        self._seen_log = len(state.log)
        self.screens = [GameScreen(state)]
        self.redraw()

    def save_and_quit(self) -> None:
        if self.run is not None:
            save_run(dump(self.run))
        self.return_to_title()

    def quit_requested(self) -> None:
        from .screens.dialogs import ConfirmScreen

        self.push(
            ConfirmScreen(
                "QUIT NEVERDEAD'S REVENGE?",
                "The dungeon will still be here when you come back.",
                on_done=lambda yes: setattr(self, "_quit", True) if yes else None,
            )
        )

    def confirm_quit_to_title(self) -> None:
        from .screens.dialogs import ConfirmScreen

        self.push(
            ConfirmScreen(
                "QUIT TO THE TITLE?",
                "The run does not come back. It is not written down.",
                on_done=lambda yes: self.return_to_title() if yes else None,
            )
        )

    # -- input ---------------------------------------------------------------
    def _route(self, name: str, event) -> None:
        if self.screens and self.screens[-1].key(name, event, self):
            self._dirty = True

    def key_down(self, name: str, *, repeat: bool = False, text: str = "") -> None:
        """Feed one press to the top screen, the way the other builds do.

        ``repeat`` and ``text`` are keyword-only on purpose: a call like
        ``key_down("n", "n")`` -- which is how the desktop's test helper reads
        -- would otherwise pass the text as the *repeat* flag, and the screen
        would quietly ignore the key as a held one.
        """
        self._route(name, KeyEvent(name, repeat, text))

    def key_up(self, name: str) -> None:
        event = KeyEvent(name)
        if self.screens and self.screens[-1].key_up(name, event, self):
            self._dirty = True

    # -- the platform's own weather ------------------------------------------
    def _suspend(self) -> None:
        """The app is leaving the foreground: write the run down and sleep.

        Android can take the process away without another word, and a run is
        forty kilobytes of map. It goes into the same file "save and quit"
        writes, so ``continue_run`` picks it up exactly as it would after a
        deliberate exit.
        """
        if self.run is not None:
            try:
                save_run(dump(self.run))
            except OSError:
                pass
        self._release_wakelock()

    def _resume(self) -> None:
        """Back in front: keep the panel lit, and repaint what was underneath."""
        self._acquire_wakelock()
        self._dirty = True

    def _acquire_wakelock(self) -> None:
        """Keep the panel lit while the game is in front, on Android.

        A handheld that dims mid-fight has lost the fight for you, and SDL has
        no call for this, so it goes through the platform's own power manager.
        On a desktop there is no ``jnius`` and nothing to keep awake, and this
        is quietly nothing -- which is why it is allowed to fail.
        """
        if self._wakelock is not None:
            return
        try:
            from jnius import autoclass

            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            context = autoclass("android.content.Context")
            power = autoclass("android.os.PowerManager")
            service = activity.getSystemService(context.POWER_SERVICE)
            lock = service.newWakeLock(
                power.SCREEN_BRIGHT_WAKE_LOCK, "neverdeads_revenge"
            )
            lock.acquire()
            self._wakelock = lock
        except Exception:
            self._wakelock = None

    def _release_wakelock(self) -> None:
        lock, self._wakelock = self._wakelock, None
        if lock is None:
            return
        try:
            lock.release()
        except Exception:
            pass

    def handle(self, event) -> bool:
        """Handle one pygame event. Returns ``False`` to leave the loop."""
        if self.screens:
            # The bench (``--sniff``) wants every event raw, before a mapping
            # has read it; no other screen defines this, so this is a no-op
            # everywhere else.
            note = getattr(self.screens[-1], "note", None)
            if note is not None:
                note(event, self)
        if event.type == pygame.QUIT:
            return False
        if event.type == _APP_WILLENTERBACKGROUND:
            # Android is about to put us in the background, and it may take the
            # process away without another word. A run is forty kilobytes of
            # map; it gets written down now, into the same file "save and quit"
            # writes, so continuing works.
            self._suspend()
            return True
        if event.type == _APP_DIDENTERFOREGROUND:
            self._resume()
            return True
        if event.type == _APP_TERMINATING:
            self._suspend()
            return False
        if event.type == pygame.KEYDOWN:
            name = key_name(event)
            if name is not None and name not in POLLED_DIRECTIONS:
                # Directions are the poll's business, and only the poll's: if
                # both counted a held arrow the cursor would move twice per
                # press -- once from this event and once from the held key --
                # which is a menu that skips an item now and then.
                self.key_down(name, text=event.unicode or "")
            if event.key == pygame.K_ESCAPE and event.mod & pygame.KMOD_CTRL:
                return False
        elif event.type == pygame.KEYUP:
            name = key_name(event)
            if name is not None and name not in POLLED_DIRECTIONS:
                self.key_up(name)
        elif event.type == pygame.JOYBUTTONDOWN:
            self._buttons_down.add(event.button)
            name = button_name(event.button)
            if name is not None:
                self.key_down(name)
        elif event.type == pygame.JOYBUTTONUP:
            self._buttons_down.discard(event.button)
            name = button_name(event.button)
            if name is not None:
                self.key_up(name)
        return True

    def _direction_now(self) -> str | None:
        """Where the player is pushing: the d-pad first, then the keys.

        The d-pad is read as a hat, because a d-pad *is* a hat: eight positions
        and no in-between, which is exactly the instrument a grid wants. The
        analog stick is deliberately **not** read for movement -- it drifts, it
        has no rest that is truly still, and the handheld this is for asked for
        the d-pad. (The bench, ``--sniff``, still shows the stick raw.)
        """
        for stick in self.joysticks:
            if stick.get_numhats():
                x, y = stick.get_hat(0)
                if (x, y) != (0, 0):
                    return {
                        (0, 1): "down", (0, -1): "up",
                        (-1, 0): "left", (1, 0): "right",
                        (-1, 1): "sw", (1, 1): "se",
                        (-1, -1): "nw", (1, -1): "ne",
                    }.get((x, y))
        pressed = pygame.key.get_pressed()
        for key, name in (
            (pygame.K_UP, "up"), (pygame.K_DOWN, "down"),
            (pygame.K_LEFT, "left"), (pygame.K_RIGHT, "right"),
        ):
            if pressed[key]:
                return name
        return None

    def _hold_key_down(self, key: str) -> bool:
        """Whether the key a hold is waiting for is *still held*.

        Two sources, because the handheld has two: the pad's A (button zero,
        tracked from its down and up events) and, on a desktop, the return key.
        """
        if key in ("enter", "return"):
            if 0 in self._buttons_down:
                return True
            pressed = pygame.key.get_pressed()
            return bool(pressed[pygame.K_RETURN] or pressed[pygame.K_KP_ENTER])
        return False

    def poll_holds(self, now: float) -> None:
        """Feed the holds the repeat stream a handheld never sends.

        The prologue, the death tally and erasing the profile all advance on a
        *stream* of presses: the fill is the time since the first one and the
        screen closes on the press that crosses it. A keyboard repeats on its
        own and a pad does not -- SDL reports a button going down and coming
        up and nothing in between -- so on a handheld the stream has to be made
        here, or "hold A to begin" fills nothing and the premise never ends.

        It is the same shape as the stick's polling, and for the same reason: a
        held button has a *state*, and the game wants a stream.

        And like a keyboard's auto-repeat it *waits* before it repeats. That is
        not politeness, it is the hold's own rule: a press that is down briefly
        and never repeats is a tap, and a tap banks nothing. Feeding a repeat on
        the very first frame made every press a repeated one, so a tap could
        bank a fill and two of them could add up to a hold nobody held -- which
        is exactly what "hold A feels strange" was.
        """
        if not self.screens:
            return
        hold = getattr(self.screens[-1], "hold", None)
        if hold is None or not hold.keys:
            self._hold_down_at = None
            return
        key = hold.keys[0]
        if not self._hold_key_down(key):
            # The key is up: the next down is a new hold, and the repeat
            # clock starts with it rather than carrying the last one's.
            self._hold_down_at = None
            return
        if self._hold_down_at is None:
            self._hold_down_at = now
            self._last_hold_repeat = now
            return
        if now - self._hold_down_at < _HOLD_REPEAT_DELAY:
            return
        if now - self._last_hold_repeat < _HOLD_REPEAT_RATE:
            return
        self._last_hold_repeat = now
        self.key_down(key, repeat=True)

    def poll_held(self, now: float) -> None:
        """A pushed direction walks, at the hero's own pace.

        Read on the clock rather than on events because a stick has no "press",
        only a position -- and a held position has to repeat itself or the
        player pushes it once per square. The pace is the hero's: the same
        ``action_gap`` the desktop build throttles its repeats with, so a fast
        hero walks fast on both.

        Two guards keep a deliberate tap from becoming a lunge. A press moves
        once and then waits out ``_REPEAT_DELAY`` before repeating, so a tap of
        any ordinary length is exactly one square -- and a stick that flickers
        across the deadzone is read as one hold rather than a fresh press, so
        the wobble at the edge of a direction cannot add a step.
        """
        direction = self._direction_now()
        if direction is None:
            if self._held_dir is not None:
                self._released_at = now
            self._held_dir = None
            return
        if direction != self._held_dir:
            if (
                direction == self._last_dir
                and now - self._released_at < _RELEASE_GRACE
            ):
                # The same direction, a moment after it was lost: the stick
                # crossed the deadzone, the player did not press twice.
                self._held_dir = direction
                return
            self._held_dir = direction
            self._last_dir = direction
            self._last_repeat = now
            self._repeat_from = now + _REPEAT_DELAY
            self.key_down(direction)
            return
        if now < self._repeat_from:
            return
        gap = 0.12
        if self.run is not None:
            gap = action_gap(self.run.player.speed)
        if now - self._last_repeat >= gap:
            self._last_repeat = now
            self.key_down(direction)

    # -- the loop ------------------------------------------------------------
    def tick(self, dt: float) -> None:
        """Advance what moves between turns, and say whether to repaint."""
        self.effects.step(dt)
        if self.run is not None:
            from .render import ultimate_ready

            holding = any(
                getattr(screen, "hold", None) is not None and screen.hold.holding
                for screen in self.screens
            )
            if (
                self.effects.active
                or self.shake.is_shaking()
                or holding
                or ultimate_ready(self.run)
            ):
                self._dirty = True

    def loop(self) -> None:
        clock = pygame.time.Clock()
        running = True
        self._acquire_wakelock()
        while running and not self._quit:
            dt = clock.tick(60) / 1000.0
            now = time.monotonic()
            for event in pygame.event.get():
                if not self.handle(event):
                    running = False
            self.poll_held(now)
            self.poll_holds(now)
            self.tick(dt)
            if self._dirty:
                self.redraw()
        self._release_wakelock()
        pygame.quit()
