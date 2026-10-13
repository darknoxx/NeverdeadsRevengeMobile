"""The mobile layout, and everything drawn on it.

The screen is nearly square (1240x1080), so the desktop's arrangement -- a wide
map with a 34-column sidebar -- does not fit. What fits is three stacked bands:

    HUD      the numbers the player acts on, always visible
    MAP      the dungeon, full width
    LOG      the last few lines, full width

Nothing that changes a decision lives in a submenu. The *reference* does: the
legend, the chronicle, the sheet, the pack, and the long lists of curses, gifts
and statuses are menus, opened from the pad. HP, the ultimate, the draughts and
the level stay on the screen at every zoom, because a handheld that hides the
health bar behind a button is a handheld that gets put down.

Everything is drawn into the buffer, one face, no pasting: at these sizes the
log strip is 5 to 14 rows of cells, which is 5 to 14 lines of text -- a second
smaller font would buy rows the screen does not need and cost the port a whole
sub-system.
"""

from __future__ import annotations

import math
import time

import pygame

from neverdeads_revenge.game.prologue import legend_rows
from neverdeads_revenge.game.state import GameState, LogKind
from neverdeads_revenge.world.generator import ESCAPE_DEPTH
from neverdeads_revenge.world.items import (
    AMULET_GLYPH,
    ARMOUR_GLYPH,
    CHEST_GLYPH,
    COIN_GLYPH,
    WEAPON_GLYPH,
)
from neverdeads_revenge.world.tiles import Tile

from .buffer import PatternBuffer
from .theme import Style, blend, parse_style

__all__ = [
    "regions",
    "viewport",
    "map_crop",
    "zoom_map",
    "screen_point",
    "pulse_level",
    "draw_game",
    "hud_lines",
    "log_style",
    "marks_line",
    "ultimate_prompt",
    "ultimate_ready",
    "legend_lines",
    "FROST",
    "BLOOD_TINT",
]

#: LogKind -> style, the same mapping the terminal log used.
_KIND_STYLES: dict[LogKind, str] = {
    LogKind.PLAIN: "white",
    LogKind.COMBAT: "bright_white",
    LogKind.CRIT: "bold yellow",
    LogKind.DAMAGE: "orange1",
    LogKind.GOOD: "bold green",
    LogKind.BAD: "bold red",
    LogKind.SYSTEM: "bold cyan",
    LogKind.COIN: "bold yellow",
}

#: The blood the floor keeps while the carrion tongue works.
BLOOD_TINT = (58, 15, 18)
#: The cold the floor goes while the Frozen Fortress stands.
FROST = (191, 206, 210)

#: Each hero's promise: the name, and the colour it is said in.
ULTIMATE_PROMPTS: dict[str, tuple[str, tuple[int, int, int]]] = {
    "noxx": ("give in to the void", (14, 111, 111)),
    "yeti": ("build the Frozen Fortress", (159, 227, 239)),
    "walkyrion": ("shatter the golden bell", (212, 175, 55)),
}

_BAR_CELLS = 14

#: How long one step of the ultimate's breath lasts, in seconds. See
#: :func:`pulse_level` for why the breath is stepped and not smooth.
PULSE_SECONDS = 0.3
#: How much of a worn item's name the HUD shows: the last word, clipped.
_SHORT_NAME = 12
_SLOT_GLYPH = {"weapon": WEAPON_GLYPH, "armour": ARMOUR_GLYPH, "amulet": AMULET_GLYPH}


#: How many lines the log shows: the last three things said. The rest of the
#: height goes to the map, which is what the player is looking at.
_LOG_LINES = 3


# -- layout -------------------------------------------------------------------
def regions(cols: int, rows: int) -> dict[str, tuple[int, int, int, int]]:
    """The three bands, in cells: ``hud``, ``map``, ``log``.

    No rules between them. Each rule cost a row, and the bands read apart
    without them -- the log is a different thing whether or not a line says so.
    The log is three lines, and everything else goes to the map.

    The HUD is: health, the level and the floor, the numbers, the gold, the
    gear, what is working, and the charge. Seven lines, and a screen with fewer
    rows keeps the top of the list, which is the order that matters.
    """
    hud = 7 if rows >= 30 else 6 if rows >= 22 else 5
    map_h = rows - hud - _LOG_LINES
    return {
        "hud": (0, 0, cols, hud),
        "map": (0, hud, cols, map_h),
        "log": (0, hud + map_h, cols, _LOG_LINES),
    }


def viewport(state: GameState, map_w: int, map_h: int) -> tuple[int, int, int, int]:
    """The dungeon window the map shows: ``(left, top, view_w, view_h)``."""
    dungeon = state.dungeon_map
    view_w = min(map_w, dungeon.width)
    view_h = min(map_h, dungeon.height)
    left = max(0, min(state.player.position[0] - view_w // 2, dungeon.width - view_w))
    top = max(0, min(state.player.position[1] - view_h // 2, dungeon.height - view_h))
    return left, top, view_w, view_h


def map_band(
    cols: int, rows: int, cell_w: int, cell_h: int
) -> tuple[int, int, int, int]:
    """The map band in pixels: ``(x, y, width, height)``."""
    x0, y0, width, height = regions(cols, rows)["map"]
    return x0 * cell_w, y0 * cell_h, width * cell_w, height * cell_h


def map_crop(
    state: GameState,
    cols: int,
    rows: int,
    cell_w: int,
    cell_h: int,
    zoom: int,
) -> tuple[int, int]:
    """The top-left of the zoomed map band to show, so the hero stays centred.

    The map is drawn at ``zoom`` times its size and then a window of the
    *unzoomed* band size is shown; where that window sits is the whole question.
    Centring it on the band would push the hero out of view whenever he stands
    at the edge of the floor -- the viewport is already clamped there, so he is
    off-centre in the band. So the window follows the hero, and is clamped to
    the scaled image so it never shows past the map.
    """
    band_x, band_y, band_w, band_h = map_band(cols, rows, cell_w, cell_h)
    if zoom <= 1:
        return 0, 0
    _, _, map_w, map_h = regions(cols, rows)["map"]
    left, top, _, _ = viewport(state, map_w, map_h)
    px, py = state.player.position
    hero_x = (px - left + 0.5) * cell_w * zoom
    hero_y = (py - top + 0.5) * cell_h * zoom
    crop_x = round(hero_x - band_w / 2)
    crop_y = round(hero_y - band_h / 2)
    crop_x = max(0, min(crop_x, zoom * band_w - band_w))
    crop_y = max(0, min(crop_y, zoom * band_h - band_h))
    return crop_x, crop_y


def zoom_map(
    image,
    state: GameState,
    cols: int,
    rows: int,
    cell_w: int,
    cell_h: int,
    zoom: int,
) -> None:
    """Magnify the map band of an already-drawn frame, in place.

    The fast way to a bigger playfield: the whole frame is drawn as it always
    was, and only the map's own band is scaled and windowed back into place, so
    the HUD and the log keep their size. The window follows the hero -- see
    :func:`map_crop`.

    Only the *visible* piece of the band is scaled, not the whole band scaled
    and then cropped: at 2x that is a quarter of the pixels moved, and the
    nearest-neighbour ``scale`` keeps it crisp, which is what a doubled bitmap
    font wants anyway.
    """
    if zoom <= 1:
        return
    band_x, band_y, band_w, band_h = map_band(cols, rows, cell_w, cell_h)
    crop_x, crop_y = map_crop(state, cols, rows, cell_w, cell_h, zoom)

    src_w = max(1, round(band_w / zoom))
    src_h = max(1, round(band_h / zoom))
    src_x = max(0, min(round(crop_x / zoom), band_w - src_w))
    src_y = max(0, min(round(crop_y / zoom), band_h - src_h))
    # Views, not copies: ``scale`` reads the patch and returns a new surface, so
    # the blit below never reads and writes the same pixels.
    band = image.subsurface((band_x, band_y, band_w, band_h))
    patch = band.subsurface((src_x, src_y, src_w, src_h))
    image.blit(pygame.transform.scale(patch, (band_w, band_h)), (band_x, band_y))


def screen_point(
    state: GameState,
    position,
    cols: int,
    rows: int,
    cell_w: int,
    cell_h: int,
    zoom: int = 1,
) -> tuple[float, float] | None:
    """The centre of a dungeon square, as buffer pixels -- or ``None``.

    The buffer is the *camera*, not the dungeon: every moving pixel needs this
    translation, and everything that skipped it drew in the wrong place. When
    the map is zoomed, the same translation is carried through the scale and the
    window, so a particle still lands on the square it belongs to.
    """
    x0, y0, map_w, map_h = regions(cols, rows)["map"]
    left, top, view_w, view_h = viewport(state, map_w, map_h)
    x, y = position
    if not (left <= x < left + view_w and top <= y < top + view_h):
        return None
    # The map is the *middle* band, so a square's pixel is its cell inside
    # that band and not inside the frame. Skipping the band's own origin put
    # every sparkle in the HUD, a whole band above the thing it celebrated.
    point_x = (x0 + x - left + 0.5) * cell_w
    point_y = (y0 + y - top + 0.5) * cell_h
    if zoom <= 1:
        return point_x, point_y
    band_x, band_y, _, _ = map_band(cols, rows, cell_w, cell_h)
    crop_x, crop_y = map_crop(state, cols, rows, cell_w, cell_h, zoom)
    return (
        band_x + zoom * (point_x - band_x) - crop_x,
        band_y + zoom * (point_y - band_y) - crop_y,
    )


# -- the whole screen ---------------------------------------------------------
def draw_game(buffer: PatternBuffer, state: GameState, now: float | None = None) -> None:
    """The play screen: the HUD, the map, and the log. All of it in cells."""
    buffer.clear()
    areas = regions(buffer.cols, buffer.rows)
    _draw_hud(buffer, state, areas["hud"], now if now is not None else time.time())
    _draw_map(buffer, state, areas["map"])
    _draw_log(buffer, state, areas["log"])


# -- the HUD -------------------------------------------------------------------
def _draw_hud(buffer, state, area, now: float) -> None:
    """Health first, then the level and floor, then the numbers and what is worn.

    The order is the layout's opinion about what matters, and it is the same
    order the lines are *clipped* in: a screen too short for all of them keeps
    the ones at the top. There is no rule under the HUD -- it cost a row, and
    the map below it is rule enough.

    The ultimate's ask sits in the *top-right corner*, on the health line's own
    row: it is the one line that changes what the next press can do, and a
    corner is where the eye goes without spending a line of playfield on it.
    """
    x0, y0, width, height = area
    row = y0
    for text, style in hud_lines(state):
        if row >= y0 + height:
            break
        buffer.text(x0 + 1, row, text[: width - 2], parse_style(style))
        row += 1

    prompt = ultimate_prompt(state, now)
    if prompt is not None:
        text, colour = prompt
        text = text[: width // 2]
        buffer.text(
            x0 + width - 2 - len(text),
            y0,
            text,
            Style(fg=colour, bold=True),
        )

    marks = marks_line(state)
    if marks and row < y0 + height:
        buffer.text(x0 + 1, row, marks[: width - 2], parse_style("grey70"))
        row += 1

    if state.revenge_stacks and row < y0 + height:
        player = state.player
        buffer.text(
            x0 + 1,
            row,
            f"{player.trait.title} x{state.revenge_stacks}/{player.trait.cap}",
            parse_style("bold green"),
        )
        row += 1


def hud_lines(state: GameState) -> list[tuple[str, str]]:
    """The numbers a decision needs, in the order they must survive a clip.

    Returned as ``(text, style)`` rather than drawn, so a test can read the HUD
    without a screen. The order is the layout's opinion about what matters:
    health, then the run's shape, then the charge the hero collects.
    """
    player = state.player
    lines: list[tuple[str, str]] = []

    ratio = player.hp / player.max_hp if player.max_hp else 0.0
    filled = max(0, min(_BAR_CELLS, round(ratio * _BAR_CELLS)))
    bar_colour = "green" if ratio > 0.5 else "yellow" if ratio > 0.25 else "red"
    # Health is its own line: the ask lives in the corner beside it and the
    # level and floor have the line under it, so nothing crowds the bar.
    lines.append(
        (
            f"HP {'█' * filled}{'░' * (_BAR_CELLS - filled)} {player.hp}/{player.max_hp}",
            bar_colour,
        )
    )
    lines.append(
        (f"Lv {state.level}   Floor {state.depth}/{ESCAPE_DEPTH}", "bold white")
    )

    # The numbers a fight is decided with. The desktop had them in a sidebar
    # and the thread asked for them here: the top strip has the room, and a
    # handheld should not make the player open a sheet to know how hard they
    # hit or how well they dodge.
    low, high = player.damage_range
    lines.append(
        (
            f"DMG {low}-{high}  CRT {player.crit_chance:.0%}  SPD {player.speed:.2f}"
            f"  ARM {player.armor}  EVA {player.evasion}",
            "bold white",
        )
    )

    healing = sum(1 for item in state.inventory if item.heal > 0)
    draughts = f"Gold {state.gold}   Draughts {len(state.inventory)}/{state.pack_capacity}"
    if healing:
        draughts += " q"
    lines.append((f"{draughts}   Kills {state.kills}", "bold yellow"))

    # What is worn, by its glyph and the last word of its name -- the same
    # shorthand the desktop's sidebar used, so the map's alphabet and the HUD's
    # agree about what a `)` is.
    gear = []
    for slot in ("weapon", "armour", "amulet"):
        item = player.equipment.get(slot)
        name = item.name.split()[-1][:_SHORT_NAME] if item else "—"
        gear.append(f"{_SLOT_GLYPH[slot]} {name}")
    lines.append(("  ".join(gear), "bold white"))

    return lines


def marks_line(state: GameState) -> str:
    """What is working, in one line: the bottles, the statuses, the curses.

    The desktop keeps these as three columns in a sidebar. There is no sidebar
    here, and the *counts* are what a player checks mid-fight -- the full lists
    are the status menu's job.
    """
    from neverdeads_revenge.game.draughts import draught_by_key

    parts: list[str] = []
    for key in sorted(state.floor_draughts):
        draught = draught_by_key(key)
        if draught is not None:
            parts.append(draught.name)
    for key, turns in state.player.statuses.items():
        from neverdeads_revenge.game.statuses import status_by_key

        status = status_by_key(key)
        if status is not None:
            parts.append(f"{status.name} {turns}")
    if state.curses:
        parts.append(f"curses {len(state.curses)}")
    if state.gifts:
        parts.append(f"gifts {len(state.gifts)}")
    return "   ".join(parts)


def ultimate_ready(state: GameState) -> bool:
    """Whether the hero's ask is live: available, and the level is there."""
    return (
        state.ultimate_available
        and state.atritas is None
        and state.fortress is None
        and state.level >= state.ultimate_level
    )


def pulse_level(now: float) -> float:
    """The ultimate's breath, in *steps*: 0.0, 0.5 or 1.0.

    Stepped rather than smooth on purpose. A smooth breath changed the HUD text
    every frame, and every frame of change is a whole buffer re-rendered -- the
    single most expensive thing this renderer does, spent on a shimmer. Three
    steps a second still catches the eye and lets the frame be cached.
    """
    return (int(now / PULSE_SECONDS) % 3) / 2.0


def ultimate_prompt(state: GameState, now: float) -> tuple[str, tuple[int, int, int]] | None:
    """The hero's promise, in the state it is in -- or ``None`` for a hero the
    dark has nothing for.

    Grey before the level, breathing in the hero's own colour once it is live,
    grey again once the floor has had its ask. The breath is a *brightness*, on
    purpose: it is what the eye catches from across the screen.
    """
    entry = ULTIMATE_PROMPTS.get(state.hero.key)
    if entry is None:
        return None
    name, base = entry

    if state.fortress is not None:
        fortress = state.fortress
        return (
            f"the fortress stands {fortress.stats.hp}/{fortress.stats.max_hp}",
            base,
        )
    if state.atritas is not None or not state.ultimate_available:
        return name, parse_style("grey35").fg
    if state.level < state.ultimate_level:
        return f"{name} (lvl {state.ultimate_level})", parse_style("grey30").fg

    breathing = 0.35 + 0.95 * pulse_level(now)
    lit = tuple(max(0, min(255, int(round(channel * breathing)))) for channel in base)
    return f"{name} (f)", lit  # type: ignore[return-value]


def rule(buffer: PatternBuffer, x: int, y: int, width: int, style: str) -> None:
    for i in range(width):
        buffer.put(x + i, y, "─", parse_style(style))


# -- the map ------------------------------------------------------------------
def _draw_map(buffer, state, area) -> None:
    x0, y0, width, height = area
    dungeon = state.dungeon_map
    left, top, view_w, view_h = viewport(state, width, height)
    frosted = state.fortress is not None
    tongue = state.has_draught("carrion_tongue")

    for y in range(view_h):
        for x in range(view_w):
            position = (left + x, top + y)
            glyph, style = _cell_content(position, state)
            if position in state.hits:
                style = parse_style("reverse", style)
            if tongue and position in state.death_squares and style.bg is None:
                style = _restyle(style, bg=BLOOD_TINT)
            if frosted and style.bg is None:
                fg = style.fg
                if dungeon.display_tile(position) is Tile.WALL:
                    fg = parse_style("grey15").fg
                elif (
                    state.actor_at(position) is not None
                    or dungeon.item_at(position) is not None
                ):
                    fg = parse_style("black").fg
                style = _restyle(style, fg=fg, bg=FROST)
            buffer.put(x0 + x, y0 + y, glyph, style)


def _restyle(style: Style, *, fg=None, bg=None) -> Style:
    return Style(
        fg=fg if fg is not None else style.fg,
        bg=bg if bg is not None else style.bg,
        bold=style.bold,
        dim=style.dim,
        reverse=style.reverse,
        italic=style.italic,
    )


def _cell_content(position, state: GameState) -> tuple[str, Style]:
    """One map cell: an actor, else loot, else the glass, else terrain."""
    dungeon = state.dungeon_map
    visible = dungeon.is_visible(position)

    actor = state.actor_at(position)
    if actor is not None:
        if visible:
            return actor.glyph, parse_style(f"bold {actor.color}")
        if actor.kind.name == "ENEMY" and state.has_gift("dark_knows"):
            return actor.glyph, parse_style(actor.color)

    item = dungeon.item_at(position)
    if item is not None and visible:
        return item.glyph, parse_style(f"bold {item.color}")

    if visible and position in state.trail:
        return ",", parse_style("red")
    if (
        visible
        and state.has_draught("carrion_tongue")
        and position in state.death_squares
    ):
        return "·", parse_style("dim #8b1a1a")

    tile = dungeon.display_tile(position)
    if visible:
        return tile.glyph, parse_style(tile.color)
    if (dungeon.is_explored(position) or state.void_sight) and (
        tile.blocks_movement
        or tile in (Tile.STAIRS_DOWN, Tile.RIFT, Tile.SPRING)
    ):
        return tile.glyph, parse_style("grey30")
    return " ", Style()


# -- the log ------------------------------------------------------------------
def log_style(kind: LogKind) -> str:
    """The style a log line is drawn in, by what kind of line it is."""
    return _KIND_STYLES.get(kind, "white")


def _wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap. A word longer than the line is left to overflow.

    The log used to be clipped at the edge, which is how a sentence about the
    carrion tongue lost its last word. On a handheld the log is the only place
    the game *speaks*, so its words get the rows they need -- the newest ones,
    when there are more than the strip can hold.
    """
    lines: list[str] = []
    line = ""
    for word in text.split():
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _draw_log(buffer, state, area) -> None:
    x0, y0, width, height = area
    rows = height
    if rows < 1:
        return

    # Wrapped first, then the tail: the last thing said is the thing on the
    # screen, even when a long line pushed the earlier ones out.
    wrapped: list[tuple[str, str]] = []
    for entry in state.log:
        style = log_style(entry.kind)
        for piece in _wrap(entry.text, width - 2):
            wrapped.append((piece, style))
    for i, (text, style) in enumerate(wrapped[-rows:]):
        buffer.text(x0 + 1, y0 + i, text, parse_style(style))


# -- the reference (the legend, for its own menu) -------------------------------
def legend_lines(state: GameState) -> list[tuple[str, str]]:
    """``(text, style)`` for the legend menu: every glyph, in its own colour."""
    rows: list[tuple[str, str]] = []
    for glyph, text in legend_rows(state.depth, state.hero):
        if glyph:
            rows.append((f"{glyph}   {text}", _legend_colour(glyph)))
        elif text:
            rows.append((f"    {text}", "grey70"))
        else:
            rows.append(("", ""))
    return rows


def _legend_colour(glyph: str) -> str:
    """The colour the map draws this glyph in -- the same walker the desktop
    build uses, so a legend row promises what the map shows."""
    from neverdeads_revenge.game.npcs import NPC_COLOR, NPC_GLYPH
    from neverdeads_revenge.world.items import ITEMS

    if glyph == NPC_GLYPH:
        return NPC_COLOR
    if glyph == CHEST_GLYPH:
        return "#8b6f47"
    if glyph == COIN_GLYPH:
        return "#ffd700"
    for template in ITEMS.values():
        if template.glyph == glyph:
            return template.color
    return "grey70"


#: Kept for the app: the glyphs a legend row may carry, in the order the
#: reference lists them.
LEGEND_ORDER = (WEAPON_GLYPH, ARMOUR_GLYPH, AMULET_GLYPH, CHEST_GLYPH, COIN_GLYPH)
