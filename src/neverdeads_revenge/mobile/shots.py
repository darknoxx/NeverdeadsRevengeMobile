"""A real moment, staged for a screenshot.

The zoom question is answered by pictures, and a picture of an empty first
floor answers nothing: it has to show the HUD under pressure (a wound, a
draught in the pack), the map with something on it (blood, coin, a wall of the
dungeon's own), and the log with words in it. So this stages exactly that --
with the engine's own verbs, on a fixed seed, so the three zooms are the same
moment at three sizes.
"""

from __future__ import annotations

from neverdeads_revenge.game.actions import Action, drink, perform_action
from neverdeads_revenge.game.actors import ENEMIES, make_enemy
from neverdeads_revenge.world.items import ITEMS, make_item
from neverdeads_revenge.world.tiles import Tile

__all__ = ["stage_a_moment"]

#: Where the staged enemies stand, relative to the hero: two in reach, one
#: further off so the map has something at a distance.
_KILLS = ((1, 0), (1, 1), (0, 1), (3, -2))


def stage_a_moment(app) -> None:
    """Give the app a run worth photographing."""
    state = app.run
    here = state.player.position

    # A few things to kill, in reach and one out of it.
    for dx, dy in _KILLS:
        square = (here[0] + dx, here[1] + dy)
        state.dungeon_map.set_tile(square, Tile.FLOOR)
        enemy = make_enemy(ENEMIES["ghoul"], square)
        enemy.stats.hp = 1
        enemy.stats.damage = (0, 0)
        state.enemies.append(enemy)
        state.turn_queue.add(enemy)

    # Kill two of them the way a player would, so coin and blood are real.
    for _ in range(2):
        perform_action(state, Action.MOVE_EAST)
    perform_action(state, Action.MOVE_SOUTH)

    # A wound, so the health bar is neither full nor red.
    state.player.stats.hp = max(1, int(state.player.max_hp * 0.55))

    # The pack: one medicine and one rule, and the rule is *working*, so the
    # HUD's marks line and the map's blood stains both have something to say.
    state.inventory.append(make_item(ITEMS["potion"]))
    state.inventory.append(make_item(ITEMS["carrion_tongue"]))
    drink(state, "carrion_tongue")

    # The level the ultimates answer at, so the prompt is live and breathing
    # rather than greyed: the one line the thread insisted must stay visible.
    state.level = max(state.level, state.ultimate_level)

    # And something for the log's tail.
    perform_action(state, Action.WAIT)
    app._dirty = True
