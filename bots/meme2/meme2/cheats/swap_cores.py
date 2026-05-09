"""Swap our core's footprint with the enemy core's, in engine state.

Both cores are 3x3 entities. Each core's `EntityBase.position` is the
**centre** — the engine's `remove_building` walks `pos + d` for every
8-direction + Centre (`game.rs:454`), so the 9 covered tiles span
`(cx-1..cx+1, cy-1..cy+1)`. The engine asserts `tile.building == Some(id)`
in that walk, so swapping `position` alone breaks the invariant on the
next destroy/cleanup.

This swap atomically:
  - swaps `EntityBase.position` of the two cores;
  - rewrites all 9 `tile.building` pointers at the *old* our-core
    footprint to the enemy core's id;
  - rewrites all 9 `tile.building` pointers at the *old* enemy-core
    footprint to our core's id.

After this, every spatial query (entity-side or tile-side) sees the
two cores in each other's positions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType

if TYPE_CHECKING:
    from cambc import Team
    from rust import Game


def swap_cores(g: Game, my_team: Team) -> tuple[int, int] | None:
    """Swap our core and the enemy core. Returns `(our_core_id, enemy_core_id)`."""
    our_bid: int | None = None
    enemy_bid: int | None = None
    our_base = None
    enemy_base = None
    for bid, e in g.entities.items():
        if e.entity_type != EntityType.CORE:
            continue
        if e.base.team == my_team:
            our_bid = bid
            our_base = e.base
        else:
            enemy_bid = bid
            enemy_base = e.base
    if our_bid is None or enemy_bid is None or our_base is None or enemy_base is None:
        return None

    our_pos = our_base.position
    enemy_pos = enemy_base.position

    our_base.position = enemy_pos
    enemy_base.position = our_pos

    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            g.game_map.tile(our_pos.x + dx, our_pos.y + dy).building = enemy_bid
            g.game_map.tile(enemy_pos.x + dx, enemy_pos.y + dy).building = our_bid

    return our_bid, enemy_bid
