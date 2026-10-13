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
        "--scale",
        type=float,
        default=1.0,
        metavar="X",
        help="show the window at X times the device's size (dev on a laptop: 0.5)",
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="start with the sound off, whatever the save file says",
    )
    parser.add_argument(
        "--testrun",
        action="store_true",
        help="unlock the chronicle, fill the purse, and let the ultimates answer from level 1",
    )
    parser.add_argument(
        "--screenshot",
        metavar="DIR",
        default=None,
        help="draw one frame per zoom into DIR and exit (no window needed)",
    )
    args = parser.parse_args(argv)

    if args.testrun:
        from .persistence import grant_test_save

        grant_test_save()

    if args.screenshot:
        # Headless: SDL's dummy driver, so this works over SSH and in CI.
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        # A screenshot is a photograph, not a session: it must not read or
        # write the player's own progress, and it must be the *same* moment at
        # all three zooms. So it gets a throwaway home and a fixed seed.
        import tempfile

        os.environ["NEVERDEADS_REVENGE_HOME"] = tempfile.mkdtemp(prefix="ndrm-shots-")
        if args.testrun:
            from .persistence import grant_test_save

            grant_test_save()

        from .mobile.app import ZOOMS, MobileApp
        from .mobile.shots import stage_a_moment

        os.makedirs(args.screenshot, exist_ok=True)
        seed = args.seed if args.seed is not None else 1
        for zoom in ("S", "M", "L"):
            app = MobileApp(
                zoom=zoom,
                seed=seed,
                hero=args.hero,
                headless=True,
                testrun=args.testrun,
            )
            # The premise is told once, between the choice and the floor; a
            # photograph is taken after it. begin_run is what builds the run
            # stage_a_moment then dresses.
            app.prologue_seen = True
            app.begin_run(args.hero)
            stage_a_moment(app)
            app.screenshot(f"{args.screenshot.rstrip('/')}/zoom_{zoom}.png")
            print(
                f"{zoom}: {app.cols}x{app.rows} cells at {ZOOMS[zoom]}px "
                f"({app.frame[0]}x{app.frame[1]} px)"
            )
        return 0

    from .mobile.app import MobileApp

    app = MobileApp(
        zoom=args.zoom,
        seed=args.seed,
        hero=args.hero,
        scale=args.scale,
        no_sound=args.no_sound,
        testrun=args.testrun,
    )
    app.redraw()
    app.loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
