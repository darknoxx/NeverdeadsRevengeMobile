"""The app's own wiring, driven the way the window drives it.

Every other test in this fork tests the engine, which the port did not touch.
These test the *port*: the event path, the pad, the polling, and the handful of
attributes the screens ask the app for. They exist because two real crashes got
past a smoke test that called ``app.key_down`` directly instead of feeding
events -- which is not how a player plays.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from neverdeads_revenge.mobile.app import MobileApp  # noqa: E402

KEYCODES = {
    "enter": pygame.K_RETURN,
    "escape": pygame.K_ESCAPE,
    "up": pygame.K_UP,
    "down": pygame.K_DOWN,
    "left": pygame.K_LEFT,
    "right": pygame.K_RIGHT,
}


def key_event(name: str, down: bool = True, text: str = ""):
    """A real pygame event, the shape the window delivers."""
    key = KEYCODES.get(name)
    if key is None:
        # pygame spells a letter's keycode in lower case and a named key in
        # upper: K_n, K_SPACE. Both, then. A punctuation key has no code the
        # game reads anyway -- it comes through as typed text, which is the
        # whole point of reading ``unicode`` -- so zero is the honest stand-in.
        for candidate in (f"K_{name}", f"K_{name.upper()}"):
            key = getattr(pygame, candidate, None)
            if key is not None:
                break
        else:
            key = 0
    return pygame.event.Event(
        pygame.KEYDOWN if down else pygame.KEYUP,
        key=key,
        unicode=text or (name if len(name) == 1 else ""),
        mod=0,
    )


def pad_event(button: int, down: bool = True):
    return pygame.event.Event(
        pygame.JOYBUTTONDOWN if down else pygame.JOYBUTTONUP, button=button
    )


@pytest.fixture
def app():
    window = MobileApp(headless=True, seed=3, no_sound=True)
    window.redraw()
    return window


def top(app) -> str:
    return type(app.screens[-1]).__name__


def start_a_run(app, seed: int = 3):
    """A live run on the app, without walking the prologue for it."""
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run

    from neverdeads_revenge.mobile.screens.game import GameScreen

    app.run = start_run(HEROES["noxx"], seed)
    app.screens = [GameScreen(app.run)]
    app.redraw()
    return app.run


def hold(app, button: int = 0, seconds: float = 1.4) -> None:
    """Hold a pad button the way a thumb does: down, then frames."""
    app.handle(pad_event(button, down=True))
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        time.sleep(0.016)
        app.poll_holds(time.monotonic())
        app.poll_held(time.monotonic())
        if top(app) not in ("PrologueScreen", "GameOverScreen", "DeleteProgressScreen"):
            break
    app.handle(pad_event(button, down=False))


# -- the event path ------------------------------------------------------------
def test_the_real_event_path_walks_the_whole_stack(app):
    """Title, hero select, prologue, run -- through pygame events, not through
    a shortcut the tests invented."""
    app.handle(key_event("n", text="n"))
    assert top(app) == "HeroSelectScreen"

    app.handle(pad_event(0, down=True))  # A takes the hero
    assert top(app) == "PrologueScreen"

    hold(app)  # and a held A lets the premise go
    assert top(app) == "GameScreen"
    assert app.run is not None


def test_a_key_release_does_not_crash(app):
    """The first real key release found this: pygame spells it ``unicode``,
    and the desktop's ``text()`` does not exist here."""
    app.handle(key_event("n", text="n"))
    app.handle(key_event("n", down=False))
    assert top(app) == "HeroSelectScreen"


def test_the_pad_drives_a_menu(app):
    app.handle(key_event("n", text="n"))  # the hero select
    app.handle(pad_event(1, down=True))  # B: back to the title
    assert top(app) == "TitleScreen"

    app.handle(pad_event(0, down=True))  # A: the chosen line, a new run
    assert top(app) == "HeroSelectScreen"


# -- the poll ------------------------------------------------------------------
def test_a_held_direction_walks_and_a_tap_steps_once(app):
    app.handle(key_event("n", text="n"))
    app.handle(pad_event(0, down=True))
    hold(app)
    state = app.run
    assert top(app) == "GameScreen"

    app._direction_now = lambda: "right"  # a stick held right
    now = time.monotonic()
    app.poll_held(now)
    once = state.player.steps
    app.poll_held(now + 0.05)  # too soon for the pace
    assert state.player.steps == once, "a direction moved twice in one press"
    app.poll_held(now + 0.5)  # the pace has passed
    assert state.player.steps > once, "a held direction did not walk"


def test_a_long_tap_is_still_one_step(app):
    """The overshoot the handheld reported: a press that lingered a moment
    moved twice, because the repeat began on the very next frame. A tap now
    moves once and then waits out the repeat delay, like a keyboard's."""
    run = start_a_run(app)
    app._direction_now = lambda: "right"

    now = time.monotonic()
    app.poll_held(now)
    once = run.player.steps
    for step in (0.05, 0.10, 0.20):
        app.poll_held(now + step)
        assert run.player.steps == once, f"a tap moved again after {step}s"
    app.poll_held(now + 0.45)  # the delay is spent: now it is a walk
    assert run.player.steps > once


def test_a_quick_second_tap_moves_again(app):
    """The handheld said "sometimes a press does nothing". That was a release
    grace meant for a stick flickering across its deadzone -- but the stick is
    not read for movement, so all the grace did was swallow the second of two
    quick taps. Two taps now take two steps."""
    run = start_a_run(app)
    held = {"dir": "right"}
    app._direction_now = lambda: held["dir"]

    now = time.monotonic()
    app.poll_held(now)
    once = run.player.steps

    held["dir"] = None          # released
    app.poll_held(now + 0.04)
    held["dir"] = "right"       # pressed again, quickly
    app.poll_held(now + 0.06)
    assert run.player.steps == once + 1, "the second tap was swallowed"


def test_an_effect_lands_on_the_square_it_belongs_to(app):
    """The gold sparkle was drawn a whole band too high once; then the map was
    magnified and the same translation had to follow it. Both are checked."""
    from neverdeads_revenge.mobile.render import map_band, regions, viewport

    run = start_a_run(app)
    cols, rows = app._buffer.cols, app._buffer.rows
    cell_w, cell_h = app.font.cell_w, app.font.cell_h
    band_x, band_y, band_w, band_h = map_band(cols, rows, cell_w, cell_h)
    position = run.player.position

    app.map_zoom = 1
    x0, y0, map_w, map_h = regions(cols, rows)["map"]
    left, top, _, _ = viewport(run, map_w, map_h)
    assert app.screen_point(position) == (
        (x0 + position[0] - left + 0.5) * cell_w,
        (y0 + position[1] - top + 0.5) * cell_h,
    )

    app.map_zoom = 2
    zoomed = app.screen_point(position)
    assert band_x <= zoomed[0] < band_x + band_w, "the zoomed point left the band"
    assert band_y <= zoomed[1] < band_y + band_h, "the zoomed point left the band"
    # The window follows the hero, so his own square lands at the band's centre.
    assert abs(zoomed[0] - (band_x + band_w / 2)) <= cell_w
    assert abs(zoomed[1] - (band_y + band_h / 2)) <= cell_h


def test_the_map_zooms_and_the_bars_do_not(app):
    """The playfield is magnified in its own band; the HUD and the log are
    drawn as they always were."""
    from neverdeads_revenge.mobile.render import map_band, zoom_map

    run = start_a_run(app)
    cols, rows = app._buffer.cols, app._buffer.rows
    cell_w, cell_h = app.font.cell_w, app.font.cell_h
    band = map_band(cols, rows, cell_w, cell_h)

    frame = app._buffer.render()
    hud_before = frame.copy()
    zoom_map(frame, run, cols, rows, cell_w, cell_h, 2)

    # The map band changed...
    band_mid = frame.get_at((band[0] + band[2] // 2, band[1] + band[3] // 2))
    assert band_mid is not None
    # ...and the rows above it did not.
    for y in range(0, band[1], 7):
        assert frame.get_at((5, y)) == hud_before.get_at((5, y)), "the HUD moved"


def test_the_crt_effects_can_be_turned_off(app):
    """The handheld asked for scanlines and bloom, then found them too dear --
    so both are switches, and both are *off* by default."""
    assert not app.scanlines_on and not app.bloom_on
    assert app.map_zoom == 2  # the magnified playfield is the cheap one

    app.toggle_scanlines()
    app.toggle_bloom()
    app.toggle_map_zoom()
    assert app.scanlines_on and app.bloom_on and app.map_zoom == 1

    app.toggle_map_zoom()
    assert app.map_zoom == 2

    # And the whole pipeline still draws at both settings.
    start_a_run(app)
    app.redraw()
    app.toggle_scanlines()
    app.toggle_bloom()
    app.toggle_map_zoom()
    app.redraw()
    render_ms, post_ms, present_ms = app.timings()
    assert render_ms >= 0.0 and post_ms >= 0.0 and present_ms >= 0.0


def test_an_effect_frame_does_not_re_render_the_glyphs(app):
    """The frame cache: a blood burst draws over the cached frame instead of
    re-rendering two thousand cells -- which is what made the CRT feel dear."""
    run = start_a_run(app)
    app.redraw()
    assert not app._buffer_dirty

    # A particle appears, the app repaints, but the buffer did not change, so
    # the glyph frame is the very same object and nothing was re-rendered.
    point = app.screen_point(run.player.position)
    app.effects.blood(point, count=4)
    cached = app._glyph_frame
    app.tick(0.016)
    app.redraw()
    assert app._glyph_frame is cached, "an effect frame re-rendered the glyphs"
    render_ms, _, _ = app.timings()
    assert render_ms < 1.0, "the cache was ignored"

    # An input *does* change the buffer, and so re-renders.
    app.key_down("space", text=" ")
    app.redraw()
    assert app._glyph_frame is not cached, "an input did not re-render"


def test_the_shoulders_are_the_hour_and_the_wait(app):
    """On Android, SDL numbers the shoulders 9 and 10, not 4 and 5: it maps each
    Android keycode to an SDL controller-button index, and that index is what
    pygame reports. The PC layout had put "escape" on L1 and nothing on R1."""
    from neverdeads_revenge.mobile.input import button_name

    assert button_name(9) == "r", "L1 is not the borrowed hour"
    assert button_name(10) == "space", "R1 is not the wait"
    # And the rest of the Android numbering, since it is not the PC one.
    assert button_name(7) == "f", "L3 is not the ultimate"
    assert button_name(8) == "c", "R3 is not the sheet"
    assert button_name(6) == "start", "Start is not the hero's page"
    assert button_name(4) == "select", "Select is not the pause"


def test_start_confirms_the_name_and_select_pauses(app):
    """Start finishes the name entry -- the hint always promised it -- and in the
    dungeon Select pauses while Start opens the hero's page."""
    from neverdeads_revenge.mobile.screens.game import GameScreen
    from neverdeads_revenge.mobile.screens.game_over import NameEntryScreen

    # Start (pad button 6) finishes the name entry.
    done: list = []
    app.screens = [NameEntryScreen(120, previous="", on_done=done.append)]
    app.screens[-1].name = "NOX"
    app.handle(pad_event(6, down=True))
    app.handle(pad_event(6, down=False))
    assert done == ["NOX"], "Start did not finish the name"

    # In the dungeon, Start (6) is the sheet and Select (4) is the pause.
    start_a_run(app)
    app.handle(pad_event(6, down=True))
    app.handle(pad_event(6, down=False))
    assert top(app) == "CharacterScreen", "Start is not the hero's page"

    app.screens = [GameScreen(app.run)]
    app.handle(pad_event(4, down=True))
    app.handle(pad_event(4, down=False))
    assert top(app) == "PauseScreen", "Select does not pause"


def test_the_gpu_view_draws_a_frame():
    """The GPU path is exercised here through SDL's software renderer, so a
    break in it is caught before it reaches the handheld -- where a broken
    draw path would be a black screen instead of a slow one."""
    from neverdeads_revenge.mobile.effects import Effects
    from neverdeads_revenge.mobile.gpu import GpuView

    view = GpuView((320, 240), fullscreen=False)
    try:
        frame = pygame.Surface((300, 200))
        frame.fill((10, 10, 30))
        effects = Effects(17, 33)
        effects.blood((100.0, 100.0), count=4)
        overlay = pygame.Surface((60, 12))
        overlay.fill((0, 0, 0))
        view.show(
            frame,
            offset=(10, 20),
            shake=(1, -1),
            particles=effects.particles,
            bloom=True,
            scanlines=True,
            overlay=overlay,
        )
        out = view.snapshot()
        assert out.get_width() > 0 and out.get_height() > 0
    finally:
        view.window.destroy()


def test_the_app_falls_back_to_software_without_a_gpu(app):
    """A headless app has no window, so it is on the software path -- and that
    path must still draw, with the CRT baked in."""
    assert app.gpu is None
    assert app.gpu_active() is False
    app.bloom_on = True
    app.scanlines_on = True
    app.toggle_bloom()  # off again, and no crash on the software switches
    app.toggle_scanlines()
    start_a_run(app)
    app.redraw()
    assert app.timings()[0] >= 0.0


def test_the_loop_body_survives_a_real_sequence(app, monkeypatch):
    """The whole order the window runs: events, poll, holds, tick, redraw.

    Both crashes the handheld found lived here and not in ``key_down``: the
    game screen shook a view the app did not have, and a key *release* read a
    field pygame spells differently. So this drives the loop's own sequence --
    not a shortcut -- from the title into a run and back out.
    """
    queue: list[list] = [
        [key_event("n", text="n")],   # the hero select
        [pad_event(0, down=True)],    # A takes the hero
    ]
    monkeypatch.setattr(
        pygame.event, "get", lambda: queue.pop(0) if queue else []
    )
    monkeypatch.setattr(app, "_direction_now", lambda: None)

    now = [time.monotonic()]

    def frame() -> None:
        """One pass of the loop's body, exactly as ``MobileApp.loop`` runs it."""
        for event in pygame.event.get():
            assert app.handle(event) or app._quit
        app.poll_held(now[0])
        app.poll_holds(now[0])
        app.tick(0.016)
        if app._dirty:
            app.redraw()
        now[0] += 0.016

    frame()
    frame()
    assert top(app) == "PrologueScreen"

    # Hold A until the premise ends. The hold runs on the wall clock, so this
    # waits on the wall clock too -- a fixed frame count would be a guess.
    deadline = time.monotonic() + 3.0
    while top(app) == "PrologueScreen" and time.monotonic() < deadline:
        time.sleep(0.016)
        frame()
    queue.append([pad_event(0, down=False)])
    frame()
    assert top(app) == "GameScreen", "a held A did not end the premise"
    assert app.run is not None

    queue.append([key_event("right")])
    frame()
    queue.append([key_event("right", down=False)])
    frame()

    queue.append([key_event("escape")])  # the pause menu
    frame()
    assert top(app) == "PauseScreen"

    queue.append([key_event("escape")])  # and back out of it
    frame()
    assert top(app) == "GameScreen"


def test_every_menu_opens_from_a_run(app):
    """Each verb a player presses mid-run, through the event path.

    The menus are where a ported screen meets the app surface, and the two
    crashes this fork found were both exactly that meeting. So open every one
    of them from a live run, draw it, and close it again.
    """
    from neverdeads_revenge.game.actors import HEROES
    from neverdeads_revenge.game.state import start_run

    from neverdeads_revenge.mobile.screens.game import GameScreen

    for name in ("i", "l", "c", "?", "f1", "f", "q", "enter"):
        app.run = start_run(HEROES["noxx"], 3)
        app.screens = [GameScreen(app.run)]
        app.handle(key_event(name, text=name if len(name) == 1 else ""))
        app.redraw()
        app.handle(key_event("escape"))
        app.redraw()


def test_a_tap_on_the_premise_banks_nothing(app):
    """The hold's own rule, which the synthesized repeats must not break: a
    brief press that never repeated is a tap, and taps cannot add up. Feeding a
    repeat on the press frame broke exactly this -- "hold A feels strange"."""
    app.handle(key_event("n", text="n"))
    app.handle(pad_event(0, down=True))   # A takes the hero, opening the premise
    app.handle(pad_event(0, down=False))
    assert top(app) == "PrologueScreen"
    screen = app.screens[-1]

    for _ in range(3):
        app.handle(pad_event(0, down=True))
        deadline = time.monotonic() + 0.10  # shorter than any repeat delay
        while time.monotonic() < deadline:
            time.sleep(0.01)
            app.poll_holds(time.monotonic())
        app.handle(pad_event(0, down=False))
        app.poll_holds(time.monotonic())

    assert top(app) == "PrologueScreen", "taps walked through the premise"
    assert screen.hold.progress == 0.0, "a tap banked a fill"


def test_a_held_button_ends_the_premise(app):
    app.handle(key_event("n", text="n"))
    app.handle(pad_event(0, down=True))
    assert top(app) == "PrologueScreen"

    deadline = time.monotonic() + 2.5
    while top(app) == "PrologueScreen" and time.monotonic() < deadline:
        time.sleep(0.016)
        app.poll_holds(time.monotonic())
    app.handle(pad_event(0, down=False))

    assert top(app) == "GameScreen", "a held A did not end the premise"
    assert app.run is not None


# -- the platform --------------------------------------------------------------
def test_android_gets_its_own_sandbox(tmp_path, monkeypatch):
    """On Android there is no ``$HOME`` to fall back to; python-for-android
    hands the app ``ANDROID_PRIVATE``, and the save belongs inside it."""
    from neverdeads_revenge import persistence

    monkeypatch.delenv("NEVERDEADS_REVENGE_HOME", raising=False)
    monkeypatch.setenv("ANDROID_PRIVATE", str(tmp_path / "private"))
    assert persistence.data_dir() == tmp_path / "private"


def test_the_back_button_means_escape(app):
    """Android's back gesture is a key a keyboard does not have. Everywhere here
    back means escape, so no screen had to learn a second word for it."""
    start_a_run(app)
    app.handle(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_AC_BACK, unicode="", mod=0)
    )
    assert top(app) == "PauseScreen"


def test_leaving_the_foreground_writes_the_run_down(app):
    """Android can take the process away without another word, so the run is
    written the moment the app goes to the background -- into the same file
    ``save and quit`` writes, so continuing works."""
    from neverdeads_revenge.persistence import load_run

    start_a_run(app)
    assert load_run() is None

    app.handle(pygame.event.Event(pygame.APP_WILLENTERBACKGROUND))
    assert load_run() is not None, "the background took the run with it"

    app.handle(pygame.event.Event(pygame.APP_DIDENTERFOREGROUND))  # and back


def test_the_sniff_bench_shows_every_raw_event(app):
    """The bench is how a mapping gets checked against a real pad, so it must
    see every event -- including the axes and hats no screen maps."""
    from neverdeads_revenge.mobile.screens.sniff import SniffScreen

    bench = SniffScreen()
    app.screens = [bench]
    for event in (
        pygame.event.Event(pygame.JOYAXISMOTION, axis=1, value=-0.88),
        pygame.event.Event(pygame.JOYHATMOTION, hat=0, value=(0, -1)),
        pygame.event.Event(pygame.JOYBUTTONDOWN, button=7),
        key_event("n", text="n"),
    ):
        app.handle(event)
    app.redraw()

    joined = "\n".join(bench.events)
    assert "AXIS" in joined and "-0.88" in joined
    assert "HAT" in joined and "(0, -1)" in joined
    assert "BUTTON DOWN" in joined and "-> f" in joined
    assert "KEY DOWN" in joined

    app.handle(key_event("escape"))  # B / escape leaves the bench
    assert app._quit is True


def test_the_dpad_steers_however_the_pad_reports_it(app):
    """A d-pad is usually a hat, but not always: the pad on the bench reported
    it as buttons 11-14, and only the hat was read -- so the face buttons worked
    and the d-pad did nothing. Both are read now, with the stick behind them."""

    class Pad:
        hat = (0, 0)
        buttons: set = set()
        axis = (0.0, 0.0)

        def get_numhats(self):
            return 1

        def get_hat(self, hat):
            return self.hat

        def get_numbuttons(self):
            return 16

        def get_button(self, button):
            return button in self.buttons

        def get_axis(self, axis):
            return self.axis[axis]

    pad = Pad()
    app.joysticks = [pad]

    assert app._direction_now() is None, "a resting pad moved the hero"

    pad.hat = (-1, 0)
    assert app._direction_now() == "left", "the d-pad as a hat does not steer"

    pad.hat = (0, 0)
    pad.buttons = {11, 14}  # up + right, SDL's d-pad buttons
    assert app._direction_now() == "ne", "the d-pad as buttons does not steer"

    # The stick is pushed hard and nothing else: it must NOT steer. A drifting
    # resting stick reported itself as "down" forever on the handheld, which
    # scrolled the premise and ran every menu off the bottom of the screen.
    pad.buttons = set()
    pad.axis = (0.0, 0.95)
    assert app._direction_now() is None, "the drifting stick still steers"


def test_the_pause_menu_opens_the_pad_bench(app):
    """The bench has to be reachable on the device: an installed app gets no
    command line, and the bench is where a pad is seen as it really is."""
    from neverdeads_revenge.mobile.screens.sniff import SniffScreen

    start_a_run(app)
    app.handle(key_event("escape"))
    assert top(app) == "PauseScreen"
    app.handle(key_event("p"))
    assert isinstance(app.screens[-1], SniffScreen)


def test_the_confirm_dialog_answers_a_and_b(app):
    """A is enter and B is escape, and the dialog used to answer only y/n -- so
    A did nothing and only B (escape) worked, which is what the handheld saw."""
    from neverdeads_revenge.mobile.screens.dialogs import ConfirmScreen

    for name, expected in (
        ("enter", True),
        ("escape", False),
        ("y", True),
        ("n", False),
    ):
        answers: list = []
        app.screens = [ConfirmScreen("QUIT?", "body", on_done=answers.append)]
        app.handle(key_event(name, text=name if len(name) == 1 else ""))
        assert answers == [expected], f"{name} answered {answers}"


def test_the_screens_have_what_they_ask_the_app_for(app):
    """The audit that found ``app.view``: every attribute the screens read."""
    for name in (
        "_buffer", "view", "progress", "sfx", "effects", "push", "pop",
        "play", "play_after", "save_progress", "has_saved_run", "record_run",
        "screen_point", "redraw", "return_to_title", "save_and_quit",
        "begin_run", "continue_run", "open_shop", "open_scoreboard",
        "open_chronicle", "open_hero_select", "open_delete_progress",
        "toggle_sound", "quit_requested", "confirm_quit_to_title",
    ):
        assert hasattr(app, name), f"the screens read app.{name} and it is not there"


def test_a_hurt_shakes_the_frame(app):
    """The game screen shakes the view when the hero is wounded; on the
    desktop that is the CRT widget, here it is the frame's own jitter.

    Noxx is faster than a ghoul, so the first wait is still his own turn and
    the blow lands on the second -- waiting in a loop is the honest way to
    stage it, and it is the energy clock, not a pause in the test.
    """
    from neverdeads_revenge.game.actors import ENEMIES, HEROES, make_enemy
    from neverdeads_revenge.game.state import start_run
    from neverdeads_revenge.world.tiles import Tile

    from neverdeads_revenge.mobile.screens.game import GameScreen

    app.run = start_run(HEROES["noxx"], 3)
    square = (app.run.player.position[0] + 1, app.run.player.position[1])
    app.run.dungeon_map.set_tile(square, Tile.FLOOR)
    enemy = make_enemy(ENEMIES["ghoul"], square)
    enemy.stats.damage = (4, 4)
    enemy.stats.accuracy = 99  # this blow lands, or the test is about dodging
    app.run.enemies.append(enemy)
    app.run.turn_queue.add(enemy)
    app.screens = [GameScreen(app.run)]

    hp = app.run.player.hp
    for _ in range(8):
        app.handle(key_event("space", text=" "))  # wait: the ghoul answers
        if app.run.player.hp < hp:
            break
    assert app.run.player.hp < hp, "the ghoul never landed a blow"
    assert app.view.is_shaking(), "a wound did not shake the frame"
