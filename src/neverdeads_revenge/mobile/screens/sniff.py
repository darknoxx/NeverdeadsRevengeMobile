"""The pad, shown raw.

A bench, not a menu: it answers one question, and only a device in hand can
answer it -- what does *this* pad actually send? A mapping written from a spec
sheet is a mapping that gets debugged twice, so this shows every axis, button
and hat as SDL reports them, beside the name the game gives them. Reachable with
``--sniff``, and it changes nothing: B (or escape) leaves.
"""

from __future__ import annotations

import pygame

from ..chrome import ASH, BLOOD, BONE, PURPLE, box
from ..input import button_name, describe_pad, dpad_direction, stick_direction
from ..theme import parse_style
from .base import Screen

__all__ = ["SniffScreen"]

#: How many raw events to keep on show. Enough to see a sequence -- a stick
#: sweeping, a button pressed and released -- without becoming a log.
_MAX_EVENTS = 10


class SniffScreen(Screen):
    """Every axis, button and hat, live, with the game's name for each."""

    modal = True

    def __init__(self) -> None:
        self.events: list[str] = []

    # -- what the app feeds it ----------------------------------------------
    def note(self, event, app) -> None:
        """Record one raw event, before any screen has read it.

        Called by the app for *every* event, which is the point: the question
        is what arrives, not what survived a mapping.
        """
        text = _describe(event)
        if text is not None:
            self.events.append(text)
            del self.events[:-_MAX_EVENTS]

    # -- drawing -------------------------------------------------------------
    def draw(self, buffer, app) -> None:
        buffer.clear()
        width, height = buffer.cols - 4, buffer.rows - 2
        x, y = 2, 1
        box(buffer, x, y, width, height, border=BLOOD, fill=True)
        buffer.text(x + 2, y + 1, "PAD SNIFF", parse_style(f"bold {PURPLE}"))
        buffer.text(
            x + 2, y + 2, "raw from SDL, beside the name the game gives it",
            parse_style(ASH),
        )
        render_ms, post_ms, present_ms = app.timings()
        render_pk, post_pk, present_pk = app.peaks()
        buffer.text(
            x + 2,
            y + 3,
            f"{app.fps():4.0f}fps   render {render_ms:4.1f}/{render_pk:4.1f}   "
            f"post {post_ms:4.1f}/{post_pk:4.1f}   "
            f"present {present_ms:4.1f}/{present_pk:4.1f} ms",
            parse_style(f"bold {BONE}"),
        )
        buffer.text(
            x + 2,
            y + 4,
            f"map {app.map_zoom}x   scanlines {'on' if app.scanlines_on else 'off'}   "
            f"bloom {'on' if app.bloom_on else 'off'}   "
            f"(last/peak; live: pause -> SHOW FPS)",
            parse_style(ASH),
        )

        row = y + 6
        if not app.joysticks:
            buffer.text(
                x + 2, row, "no pad seen -- a keyboard is all there is",
                parse_style(f"bold {BONE}"),
            )
            row += 1
        for stick in app.joysticks:
            buffer.text(x + 2, row, describe_pad(stick), parse_style(f"bold {BONE}"))
            row += 1
            direction = dpad_direction(stick)
            buffer.text(
                x + 2, row, f"dpad  -> {direction or 'rest'}", parse_style(f"bold {BONE}")
            )
            row += 1
            direction = stick_direction(stick)
            buffer.text(
                x + 2, row, f"stick -> {direction or 'rest'}", parse_style(ASH)
            )
            row += 1
            for axis in range(stick.get_numaxes()):
                value = stick.get_axis(axis)
                buffer.text(
                    x + 2, row, f"ax{axis} {value:+.2f} {_bar(value)}",
                    parse_style(BONE),
                )
                row += 1
            for hat in range(stick.get_numhats()):
                buffer.text(
                    x + 2, row, f"hat{hat} {stick.get_hat(hat)}", parse_style(BONE)
                )
                row += 1
            down = [
                f"{index}:{button_name(index) or '?'}"
                for index in range(stick.get_numbuttons())
                if stick.get_button(index)
            ]
            buffer.text(
                x + 2, row, f"buttons down: {'  '.join(down) or 'none'}",
                parse_style(f"bold {BONE}"),
            )
            row += 1
        if app.joysticks:
            buffer.text(x + 2, row, app.trigger_state(), parse_style(f"bold {BONE}"))
            row += 1
        row += 1

        buffer.text(x + 2, row, "LAST EVENTS", parse_style(f"bold {BONE}"))
        row += 1
        for line in self.events:
            if row >= y + height - 2:
                break
            buffer.text(x + 2, row, line, parse_style(ASH))
            row += 1
        buffer.text(x + 2, y + height - 2, "B / escape to leave", parse_style(ASH))

    # -- input ---------------------------------------------------------------
    def key(self, name: str, event, app) -> bool:
        if name == "escape":
            if len(app.screens) > 1:
                app.pop()
            else:
                app._quit = True
        return True


def _describe(event) -> str | None:
    """One raw event as a line, or ``None`` for the ones this bench ignores."""
    kind = event.type
    if kind == pygame.JOYBUTTONDOWN:
        return f"BUTTON DOWN {event.button:>3}  -> {button_name(event.button) or '-'}"
    if kind == pygame.JOYBUTTONUP:
        return f"BUTTON UP   {event.button:>3}  -> {button_name(event.button) or '-'}"
    if kind == pygame.JOYAXISMOTION:
        return f"AXIS        {event.axis:>3}  {event.value:+.2f}"
    if kind == pygame.JOYHATMOTION:
        return f"HAT         {event.hat:>3}  {event.value}"
    if kind == pygame.KEYDOWN:
        return f"KEY DOWN    {event.key:>10}  {getattr(event, 'unicode', '')!r}"
    if kind == pygame.KEYUP:
        return f"KEY UP      {event.key:>10}"
    return None


def _bar(value: float, width: int = 20) -> str:
    """A stick axis as a bar, with the deadzone's centre marked.

    The mark is the whole reason the bar exists: a stick that rests *near* the
    centre and one that rests a little off it look the same as two numbers and
    different as two bars.
    """
    centre = width // 2
    pos = round((max(-1.0, min(1.0, value)) + 1.0) / 2 * (width - 1))
    cells = ["-"] * width
    for index in range(min(centre, pos), max(centre, pos) + 1):
        cells[index] = "="
    cells[centre] = "|"
    return "[" + "".join(cells) + "]"
