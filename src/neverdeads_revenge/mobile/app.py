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
from .input import KeyEvent, button_name, dpad_direction, key_name
from .crt import bloom, scanlines
from .render import draw_game, pulse_level, regions, screen_point, zoom_map
from .screens.game import GameScreen
from .screens.title import TitleScreen

__all__ = ["MobileApp", "ZOOMS", "GRID_FOR"]

#: The three zooms, as the font's pixel size. The grid follows from the font's
#: own metrics -- a cell is about six tenths as wide as it is tall, so a "cell
#: size" in pixels is a number that would lie about the grid it produces.
ZOOMS: dict[str, int] = {"S": 20, "M": 27, "L": 36}

#: How much the *map* is magnified over the HUD and the log. The bars keep the
#: font the zoom chose; the playfield is drawn twice as large and windowed back
#: into its band, so the thing the player is looking at is the thing that grows.
MAP_ZOOM = 2

#: The analog triggers, which SDL keeps on axes and not buttons: L2 is the
#: borrowed hour, R2 is the wait. A pad's triggers were the two free controls
#: left, and they are *positions*, so they are polled like a stick.
TRIGGER_KEYS = {4: "r", 5: " "}

#: How far a trigger must move from its resting value to count as pressed. The
#: resting value is learned from the first reading, because a trigger rests at
#: -1 on some pads and 0 on others, and guessing would either fire at rest or
#: never fire at all.
TRIGGER_THRESHOLD = 0.5

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

        # -- the CRT, what is left of it on a 420 ppi panel ----------------
        # Both off by default: the handheld found them too dear for what they
        # give, so they are opt-in switches in the pause menu, not defaults.
        self.map_zoom = MAP_ZOOM
        self.scanlines_on = False
        self.bloom_on = False
        #: The rendered glyph frame, rebuilt only when the *buffer* changes --
        #: see :meth:`redraw`. Effects and the shake reuse it, so a blood burst
        #: no longer re-renders two thousand cells a frame.
        self._glyph_frame: pygame.Surface | None = None
        #: Whether the buffer itself changed (input, a turn, a screen). Effects
        #: and the shake set :attr:`_dirty` (repaint) but not this.
        self._buffer_dirty = True
        #: The last step of the ultimate's breath that was drawn, so a *new*
        #: step is what asks for a re-render and the shimmer does not.
        self._pulse_level = -1.0
        #: The last redraw, split up: the honest numbers for "is the CRT
        #: affordable", shown on the bench. ``render`` is the glyph frame,
        #: ``post`` is bloom and scanlines, ``present`` is blit and flip.
        self._render_ms = 0.0
        self._post_ms = 0.0
        self._present_ms = 0.0
        #: The worst frame since startup. The last frame is whatever is being
        #: drawn now (often the bench itself); the *peak* is what a turn in the
        #: game actually cost, which is the number that matters.
        self._render_peak = 0.0
        self._post_peak = 0.0
        self._present_peak = 0.0
        self._fps = 0.0
        #: A live readout, drawn straight onto the screen and *not* into the
        #: buffer -- so measuring does not itself force the re-render it is
        #: measuring. A switch, because it is a bench, not a HUD line.
        self.show_fps = False

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
        #: The resting value of each trigger axis, learned from the first
        #: reading, and which ones are currently pulled.
        self._trigger_rest: dict[tuple[int, int], float] = {}
        self._trigger_down: set[tuple[int, int]] = set()
        #: The Android wake lock, if this build could take one. See
        #: :meth:`_acquire_wakelock`.
        self._wakelock = None

    # -- the stack -----------------------------------------------------------
    def push(self, screen) -> None:
        self.screens.append(screen)
        self._dirty = True
        self._buffer_dirty = True

    def pop(self) -> None:
        if len(self.screens) > 1:
            self.screens.pop()
        self._dirty = True
        self._buffer_dirty = True

    # -- the picture ---------------------------------------------------------
    def _compose_frame(self) -> pygame.Surface:
        """Draw the stack into one finished frame: glyphs, zoom, and the CRT.

        This is the expensive part -- two thousand blits, a map scale, and the
        bloom -- so it is the part that is cached: see :meth:`redraw`. The CRT
        is baked in *here* rather than applied per frame, because per frame is
        what made the effects unplayable on the handheld: bloom ran sixty times
        a second over a blood burst that changed nothing but the dots.
        """
        self._buffer.clear()
        # An opaque modal: nothing under it is drawn. A menu is a panel, not a
        # window onto the dungeon, so the topmost modal starts the stack.
        start = 0
        for index, screen in enumerate(self.screens):
            if getattr(screen, "modal", False):
                start = index
        drawn = self.screens[start:]
        for screen in drawn:
            screen.draw(self._buffer, self)
        image = self._buffer.render()

        # The map is magnified only when the map is actually on screen: a modal
        # starts the stack, so the band would otherwise hold a dialog and the
        # zoom would magnify the wrong thing.
        map_on_screen = self.run is not None and any(
            isinstance(screen, GameScreen) for screen in drawn
        )
        if map_on_screen and self.map_zoom > 1:
            zoom_map(
                image,
                self.run,
                self._buffer.cols,
                self._buffer.rows,
                self.font.cell_w,
                self.font.cell_h,
                self.map_zoom,
            )
        if self.bloom_on:
            bloom(image)
        if self.scanlines_on:
            scanlines(image)
        return image

    def redraw(self) -> None:
        """Draw the frame and put it on the screen.

        The frame -- glyphs, zoom and CRT -- is rebuilt only when the *buffer*
        changes. Effects and the shake draw over the cached copy, so a blood
        burst costs a copy and a few dots instead of two thousand blits and a
        bloom, which is what made the effects unplayable on the handheld.
        """
        started = time.perf_counter()
        if self._glyph_frame is None or self._buffer_dirty:
            self._glyph_frame = self._compose_frame()
            self._buffer_dirty = False
        self._render_ms = (time.perf_counter() - started) * 1000.0

        post_started = time.perf_counter()
        # Copy only when something is about to write on it.
        if self.effects.active:
            image = self._glyph_frame.copy()
            self.effects.draw(image)
        else:
            image = self._glyph_frame
        self._post_ms = (time.perf_counter() - post_started) * 1000.0

        self._present_ms = 0.0
        if self.screen is not None:
            present_started = time.perf_counter()
            dx, dy = self.shake.offset()
            self.screen.fill((0, 0, 0))
            if self.scale == 1.0:
                self.screen.blit(image, (self.offset[0] + dx, self.offset[1] + dy))
            else:
                scaled = pygame.transform.smoothscale(image, self.window_size)
                self.screen.blit(scaled, (dx, dy))
            if self.show_fps:
                self._draw_fps_readout()
            # Measured before the flip, which may wait on the panel: this is
            # the work, which is the number that says whether the CRT is
            # affordable.
            self._present_ms = (time.perf_counter() - present_started) * 1000.0
            pygame.display.flip()
        self._render_peak = max(self._render_peak, self._render_ms)
        self._post_peak = max(self._post_peak, self._post_ms)
        self._present_peak = max(self._present_peak, self._present_ms)
        self._dirty = False

    def screenshot(self, path: str) -> None:
        """Render one frame to a file, without a window."""
        frame = self._compose_frame()
        self.effects.draw(frame)
        image = pygame.Surface(self.surface_size)
        image.fill((0, 0, 0))
        image.blit(frame, self.offset)
        pygame.image.save(image, path)

    def timings(self) -> tuple[float, float, float]:
        """``(render, post, present)`` for the last redraw, in milliseconds."""
        return self._render_ms, self._post_ms, self._present_ms

    def peaks(self) -> tuple[float, float, float]:
        """``(render, post, present)`` for the worst redraw since startup."""
        return self._render_peak, self._post_peak, self._present_peak

    def fps(self) -> float:
        """The smoothed frame rate, for the bench."""
        return self._fps

    def _draw_fps_readout(self) -> None:
        """The live numbers, straight onto the screen and not into the buffer.

        Drawing them into the buffer would change the buffer every frame, which
        would force exactly the re-render the numbers exist to measure.
        """
        text = (
            f"{self._fps:4.0f}fps  r{self._render_ms:3.0f} "
            f"p{self._post_ms:3.0f} v{self._present_ms:3.0f}"
        )
        label = self.font.bold.render(text, False, (255, 230, 120))
        self.screen.fill((0, 0, 0), (0, 0, label.get_width() + 4, label.get_height()))
        self.screen.blit(label, (2, 0))

    # -- the CRT switches ----------------------------------------------------
    def toggle_scanlines(self) -> None:
        # The CRT is baked into the cached frame now, so a switch means the
        # frame must be rebuilt -- once, not per frame.
        self.scanlines_on = not self.scanlines_on
        self._dirty = True
        self._buffer_dirty = True

    def toggle_bloom(self) -> None:
        self.bloom_on = not self.bloom_on
        self._dirty = True
        self._buffer_dirty = True

    def toggle_map_zoom(self) -> None:
        """Cycle the playfield between life-size and magnified."""
        self.map_zoom = 1 if self.map_zoom > 1 else MAP_ZOOM
        self._dirty = True
        self._buffer_dirty = True

    def toggle_show_fps(self) -> None:
        self.show_fps = not self.show_fps
        self._dirty = True

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
            self.map_zoom,
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
        self._buffer_dirty = True
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
        self._buffer_dirty = True
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
        self._buffer_dirty = True
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
            # A key can change what a screen draws, and only the screen knows
            # whether it did -- so any key re-renders, which is one render per
            # press and never per frame.
            self._buffer_dirty = True

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
            self._buffer_dirty = True

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
        """Where the player is pushing: the d-pad, and the keys after it.

        The d-pad is the instrument a grid wants -- eight positions and no
        in-between -- and it is read as a hat *or* as the four buttons SDL
        reserves for it, because not every pad reports a hat.

        The analog stick is deliberately **not** read for movement. It drifts,
        and a drifting stick is not a metaphor: a resting stick on the bench
        reported itself as "down" forever, which scrolled the premise and ran
        the menus off the bottom of the screen. The bench still shows it raw.
        """
        for pad in self.joysticks:
            direction = dpad_direction(pad)
            if direction is not None:
                return direction
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

    def poll_triggers(self) -> None:
        """Read the analog triggers, which are positions and not buttons.

        SDL keeps L2 and R2 on axes, and a resting trigger is not the same value
        on every pad -- -1 on some, 0 on others -- so the resting value is
        learned from the first reading and a trigger counts as pressed once it
        has moved far enough from it. This is how the handheld's two free
        controls get the borrowed hour and the wait: every other control was
        taken, and these were the ones with nothing on them.
        """
        for index, pad in enumerate(self.joysticks):
            axes = pad.get_numaxes()
            for axis, key in TRIGGER_KEYS.items():
                if axis >= axes:
                    continue
                value = pad.get_axis(axis)
                slot = (index, axis)
                rest = self._trigger_rest.get(slot)
                if rest is None:
                    # The first reading is the rest: assume nobody is holding a
                    # trigger down at the moment the game starts.
                    self._trigger_rest[slot] = value
                    continue
                pressed = abs(value - rest) >= TRIGGER_THRESHOLD
                if pressed and slot not in self._trigger_down:
                    self._trigger_down.add(slot)
                    self.key_down(key, text=key if key.isprintable() else "")
                elif not pressed and slot in self._trigger_down:
                    self._trigger_down.discard(slot)
                    self.key_up(key)

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
        """Advance what moves between turns, and say whether to repaint.

        Effects and the shake ask only for a *repaint*: the frame they draw over
        is cached, so a blood burst no longer re-renders the glyphs. The hold
        bar and a new step of the ultimate's breath change the buffer itself, so
        those ask for a re-render.
        """
        self.effects.step(dt)
        if self.effects.active or self.shake.is_shaking():
            self._dirty = True
        if self.run is None:
            return
        from .render import ultimate_ready

        holding = any(
            getattr(screen, "hold", None) is not None and screen.hold.holding
            for screen in self.screens
        )
        if holding:
            self._buffer_dirty = True
            self._dirty = True
        if ultimate_ready(self.run):
            level = pulse_level(time.monotonic())
            if level != self._pulse_level:
                self._pulse_level = level
                self._buffer_dirty = True
                self._dirty = True

    def loop(self) -> None:
        clock = pygame.time.Clock()
        running = True
        self._acquire_wakelock()
        while running and not self._quit:
            dt = clock.tick(60) / 1000.0
            if dt > 0.0:
                instant = 1.0 / dt
                self._fps = instant if self._fps == 0.0 else self._fps * 0.9 + instant * 0.1
            now = time.monotonic()
            for event in pygame.event.get():
                if not self.handle(event):
                    running = False
            self.poll_held(now)
            self.poll_holds(now)
            self.poll_triggers()
            self.tick(dt)
            if self._dirty:
                self.redraw()
        self._release_wakelock()
        pygame.quit()
