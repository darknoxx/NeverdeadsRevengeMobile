"""Sound, through SDL_mixer, with the same names the game already speaks.

miniaudio does not exist on Android and the desktop's audio module is built
around it; what survives the move is the *language* -- ``play("coin")``,
``play("void")`` -- and the two tables that decide which log line makes which
noise. Those are pure Python and are copied here rather than re-thought, so the
two builds sound like the same game because they are reading the same rules.

SDL_mixer is the right engine for a handheld: one mixer, a handful of channels,
and a real "how busy am I" answer (``get_busy``) instead of a ring buffer the
game has to measure itself.
"""

from __future__ import annotations

from pathlib import Path

import pygame

from neverdeads_revenge.game.state import LogKind

__all__ = [
    "Sfx",
    "BY_KIND",
    "LOUDNESS",
    "URGENT",
    "sound_for_kind",
    "loudest_kind",
    "SOUNDS_DIR",
]

#: Where the generated sounds live. Inside the package rather than in assets:
#: they are read at runtime, so they have to travel with the code.
SOUNDS_DIR = Path(__file__).resolve().parent.parent / "sounds"

#: Set this to anything to start with the sound off. It can only ever mute --
#: a setting that says "on" cannot override it, because the one caller that
#: matters is the test suite.
MUTE_ENV = "NEVERDEADS_REVENGE_MUTE"

#: Which sound a message gets, by the log's own classification. The plainer
#: kinds are silent on purpose: a sound for every line is a sound for none.
BY_KIND: dict[LogKind, str] = {
    LogKind.CRIT: "crit",
    LogKind.COMBAT: "hit",
    LogKind.DAMAGE: "hurt",
    LogKind.BAD: "curse",
    LogKind.GOOD: "item",
    LogKind.COIN: "coin",
}

#: Which sound wins when one turn produces several messages: the worst thing
#: that happened, not all of them at once.
LOUDNESS: dict[LogKind, int] = {
    LogKind.DAMAGE: 5,
    LogKind.CRIT: 4,
    LogKind.COMBAT: 3,
    LogKind.BAD: 2,
    LogKind.COIN: 1,
    LogKind.GOOD: 1,
}

#: Sounds that are never dropped, however busy the mixer is.
URGENT: frozenset[str] = frozenset({"level", "death", "victory", "chest", "stairs"})


def sound_for_kind(kind: LogKind) -> str | None:
    """The sound a message of this kind makes, or ``None`` for silence."""
    return BY_KIND.get(kind)


def loudest_kind(kinds) -> LogKind | None:
    """The kind worth making a noise about, out of everything that happened."""
    best = None
    best_score = 0
    for kind in kinds:
        score = LOUDNESS.get(kind, 0)
        if score > best_score:
            best, best_score = kind, score
    return best


class Sfx:
    """The mixer, the clips, and the mute.

    Clips are loaded once, on first use: a run that never hears a chest should
    not pay for reading one, and on a handheld the first load of everything at
    once is a visible hitch at startup.
    """

    def __init__(self, muted: bool | None = None) -> None:
        self._muted = bool(__import__("os").environ.get(MUTE_ENV)) or bool(muted)
        self._clips: dict[str, pygame.mixer.Sound | None] = {}
        self._ready = False
        if not self._muted:
            self._open()

    def _open(self) -> None:
        """Open the mixer once. Raises nothing: a silent machine plays on."""
        if self._ready:
            return
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self._ready = True
        except pygame.error:
            self._ready = False

    # -- the outside world ---------------------------------------------------
    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        """Turn the sound off or on again, from the pause menu."""
        self._muted = muted
        if not muted:
            self._open()
        elif self._ready:
            pygame.mixer.stop()

    def toggle(self) -> bool:
        """Flip the mute and report the new state."""
        self.set_muted(not self._muted)
        return self._muted

    # -- playing -------------------------------------------------------------
    def _clip(self, name: str) -> pygame.mixer.Sound | None:
        if name in self._clips:
            return self._clips[name]
        clip: pygame.mixer.Sound | None = None
        path = SOUNDS_DIR / f"{name}.wav"
        try:
            clip = pygame.mixer.Sound(str(path))
        except (pygame.error, FileNotFoundError):
            clip = None
        self._clips[name] = clip
        return clip

    def play(self, name: str | None) -> None:
        """Play one clip by name. Returns immediately, always."""
        if name is None or self._muted or not self._ready:
            return
        clip = self._clip(name)
        if clip is None:
            return
        if name not in URGENT and pygame.mixer.get_busy():
            # A busy mixer is a fight in progress; a quiet sound queued behind
            # it is a sound about a moment that has gone.
            free = pygame.mixer.find_channel()
            if free is None:
                return
            free.play(clip)
            return
        clip.play()
