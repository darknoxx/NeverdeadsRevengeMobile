"""Entry point: ``python -m neverdeads_revenge``, or the ``ndrm`` script.

Development happens on a desktop, in a window the size of the handheld's
screen, so the layout is judged at the size it will be played at. The pad is
optional; the keyboard stands in for it.
"""

from __future__ import annotations

import argparse
import os
import sys

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ndrm",
        description="Neverdead's Revenge Mobile -- the dungeon, on a handheld.",
    )
    parser.add_argument(
        "--zoom",
        choices=("S", "M", "L"),
        default="M",
        help="S is more of the dungeon, L is bigger letters (default M)",
    )
    parser.add_argument("--seed", type=int, default=None, help="a repeatable run")
    parser.add_argument(
        "--hero",
        choices=("noxx", "yeti", "walkyrion"),
        default="noxx",
        help="who goes down (default noxx)",
    )
    parser.add_argument(
        "--screenshot",
        metavar="DIR",
        default=None,
        help="draw one frame per zoom into DIR and exit (no window needed)",
    )
    args = parser.parse_args(argv)

    if args.screenshot:
        # Headless: SDL's dummy driver, so this works over SSH and in CI.
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        from .mobile.app import ZOOMS, MobileApp
        from .mobile.shots import stage_a_moment

        for zoom in ("S", "M", "L"):
            app = MobileApp(zoom=zoom, seed=args.seed, hero=args.hero, headless=True)
            stage_a_moment(app)
            app.screenshot(f"{args.screenshot.rstrip('/')}/zoom_{zoom}.png")
            print(
                f"{zoom}: {app.cols}x{app.rows} cells at {ZOOMS[zoom]}px "
                f"({app.frame[0]}x{app.frame[1]} px)"
            )
        return 0

    from .mobile.app import MobileApp

    app = MobileApp(zoom=args.zoom, seed=args.seed, hero=args.hero)
    app.redraw()
    app.loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
