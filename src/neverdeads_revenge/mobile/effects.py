"""The moving pixels: blood, coins, sparks, and the shake.

The same field of particles the desktop build draws, with the same numbers --
heavy red for a death, light gold for money, a rising green for a rule gained
-- and one difference: it paints with pygame instead of a QPainter, and its
colours are tuples.

Per-particle gravity is the whole trick and it is kept: a spark is not made of
the same stuff as blood, and one shared gravity makes both look like gravel.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from .theme import _colour, parse_style

__all__ = ["Effects", "Particle"]


@dataclass(slots=True)
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    ttl: float
    colour: tuple[int, int, int]
    size: int
    #: This particle's own gravity, because a spark is not made of the same
    #: stuff as blood: it is light, and it should hang in the air before it
    #: sinks, not thump straight to the floor with everything else.
    g: float


class Effects:
    """A field of particles, in buffer pixels."""

    def __init__(self, cell_w: int, cell_h: int) -> None:
        self.cell_w = cell_w
        self.cell_h = cell_h
        self.particles: list[Particle] = []
        self._rng = random.Random()

    @property
    def active(self) -> bool:
        return bool(self.particles)

    def clear(self) -> None:
        self.particles.clear()

    # -- the three the game asks for ----------------------------------------
    def blood(self, point, count: int = 22) -> None:
        """A thing came apart. Heavy, red, and it falls."""
        self.burst_at(
            point[0], point[1], count=count, colour="#c81e1e",
            speed=70.0, life=0.7, size=2, gravity=220.0, rise=4.0,
        )

    def coin(self, point, count: int = 16) -> None:
        """Money came into the hero's hand. It gleams and drifts."""
        self.spark(point, "#ffb000", count)

    def spark(self, point, colour: str = "bright_green", count: int = 18) -> None:
        """A rule was gained, or a level. Light, and it rises."""
        self.burst_at(
            point[0], point[1], count=count, colour=colour,
            speed=45.0, life=1.0, size=1, gravity=60.0, rise=35.0,
        )

    # -- the machine --------------------------------------------------------
    def burst_at(
        self,
        x: float,
        y: float,
        *,
        count: int,
        colour: str,
        speed: float,
        life: float,
        size: int,
        gravity: float,
        rise: float = 0.0,
    ) -> None:
        """Throw ``count`` pixels at ``(x, y)``, in buffer pixels.

        ``rise`` is a bias upward against the scatter, so blood gets a small
        upward kick before it falls and a spark steps off the floor.
        """
        tint = _colour(colour) or parse_style(colour).fg
        for _ in range(count):
            angle = self._rng.uniform(0.0, math.tau)
            power = speed * self._rng.uniform(0.35, 1.0)
            span = life * self._rng.uniform(0.6, 1.15)
            # Scattered around the point rather than born at it, so the very
            # first frame already reads as a burst and not as a dot.
            self.particles.append(
                Particle(
                    x=x + self._rng.uniform(-self.cell_w * 0.5, self.cell_w * 0.5),
                    y=y + self._rng.uniform(-self.cell_h * 0.5, self.cell_h * 0.5),
                    vx=math.cos(angle) * power,
                    vy=math.sin(angle) * power - rise,
                    life=span,
                    ttl=span,
                    colour=tint,
                    size=size,
                    g=gravity,
                )
            )

    def step(self, dt: float) -> None:
        """Advance every particle, and drop the dead ones."""
        alive: list[Particle] = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0.0:
                continue
            p.vy += p.g * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

    def draw(self, image: pygame.Surface) -> None:
        """Paint the particles onto a rendered frame.

        No alpha blending on the particles themselves: a phosphor dot is lit or
        it is not, and a translucent pixel on an AMOLED is a pixel the panel
        has to think about. The fade is in the *life*, which decides how big
        the dot still is, not in a per-pixel alpha.
        """
        for p in self.particles:
            fade = max(0.0, min(1.0, p.life / p.ttl))
            size = max(1, int(round(p.size * (0.4 + 0.6 * fade))))
            image.fill(p.colour, (int(p.x), int(p.y), size, size))


class Shake:
    """A decaying jitter of the whole frame, in pixels.

    The desktop build shakes the *sampling* of the CRT; there is no shader
    here, so the frame itself is nudged when it is blitted. Same rule, same
    decay, one less pass.
    """

    def __init__(self) -> None:
        self._until = 0.0
        self._span = 0.2
        self._strength = 0
        self._rng = random.Random()

    def shake(self, strength: int = 6, seconds: float = 0.25) -> None:
        """Rattle the frame. Repeated calls keep it going, not bigger."""
        now = __import__("time").monotonic()
        if not self.is_shaking():
            self._strength = strength
            self._span = max(seconds, 0.05)
        self._until = max(self._until, now + seconds)

    def is_shaking(self) -> bool:
        return __import__("time").monotonic() < self._until

    def offset(self) -> tuple[int, int]:
        """The nudge for this frame, or zero."""
        now = __import__("time").monotonic()
        if now >= self._until:
            self._strength = 0
            return (0, 0)
        fraction = (self._until - now) / max(self._span, 1e-6)
        wobble = self._strength * min(1.0, fraction)
        return (
            int(round(self._rng.uniform(-wobble, wobble))),
            int(round(self._rng.uniform(-wobble, wobble))),
        )
