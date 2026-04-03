"""Core unit logic for trollbot — spawn one builder bot."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, EntityType, Environment, Position
from pathfinding import _rotate, chebyshev
from utils import in_bounds


def _best_spawn_pos(
    player: Player,
    ct: Controller,
    pos: Position,
) -> Position | None:
    """Pick the best spawnable tile around the core.

    Prefer tiles toward visible ore (round-robin), else toward map centre.
    """
    # Collect visible ore positions
    ore_positions: list[Position] = []
    for dx in range(-6, 7):
        for dy in range(-6, 7):
            t = Position(pos.x + dx, pos.y + dy)
            if pos.distance_squared(t) > 36:
                continue
            if not in_bounds(ct, t):
                continue
            if ct.is_in_vision(t) and ct.get_tile_env(t) == Environment.ORE_TITANIUM:
                # Skip ore that already has a harvester
                bid = ct.get_tile_building_id(t)
                if bid is not None and ct.get_entity_type(bid) == EntityType.HARVESTER:
                    continue
                ore_positions.append(t)

    if ore_positions:
        # Round-robin through ore positions
        idx = player.spawned % len(ore_positions)
        target_dir = pos.direction_to(ore_positions[idx])
    else:
        # Aim toward map centre
        cx = ct.get_map_width() // 2
        cy = ct.get_map_height() // 2
        target_dir = pos.direction_to(Position(cx, cy))

    # Try target direction first, then rotate outward
    for rot in (0, 1, -1, 2, -2, 3, -3, 4):
        d = _rotate(target_dir, rot)
        p = pos.add(d)
        if ct.can_spawn(p):
            return p
    return None


def run_core(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    rnd = ct.get_current_round()

    if player.core_pos is None:
        player.core_pos = pos

    my_team = ct.get_team()

    # Track nearest friendly bridge and whether it's carrying resources
    best_bridge = None
    best_bridge_dist = 999999
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.BRIDGE or ct.get_team(bid) != my_team:
            continue
        d = chebyshev(ct.get_position(bid), pos)
        if d < best_bridge_dist:
            best_bridge_dist = d
            best_bridge = bid

    if best_bridge is not None:
        player.nearest_bridge_id = best_bridge
        if ct.get_stored_resource(best_bridge) is not None:
            player.last_resource_turn = rnd

    # Check if the tracked bridge has been destroyed or damaged
    bridge_destroyed = player.nearest_bridge_id is not None and best_bridge is None
    bridge_damaged = best_bridge is not None and ct.get_hp(best_bridge) < ct.get_max_hp(
        best_bridge,
    )

    print(
        f"resource turn {rnd - player.last_resource_turn} bridge_destroyed {bridge_destroyed} bridge_damaged {bridge_damaged}",
    )
    # Spawn a builder if bridge has had no resources for 5+ turns, bridge was destroyed, or bridge is damaged
    if player.nearest_bridge_id is not None and (
        rnd - player.last_resource_turn >= 5 or bridge_destroyed or bridge_damaged
    ):
        sp = _best_spawn_pos(player, ct, pos)
        if sp is not None:
            ct.spawn_builder(sp)
            player.spawned += 1
            player.last_resource_turn = rnd
            return

    (funds, _) = ct.get_global_resources()
    (builder_cost, _) = ct.get_builder_bot_cost()
    (harvester_cost, _) = ct.get_builder_bot_cost()

    print(f"funds {funds}. bb {builder_cost}")

    can_afford = funds > builder_cost * 3 + harvester_cost + 100

    if can_afford and ct.get_current_round() > 100:
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) == EntityType.BRIDGE
                and ct.get_team(bid) == my_team
            ) and ct.get_bridge_target(bid).distance_squared(ct.get_position()) <= 2:
                player.expansion_cooldown += 1
                if player.expansion_cooldown > 5 and can_afford:
                    sp = _best_spawn_pos(player, ct, pos)
                    if sp is not None:
                        ct.spawn_builder(sp)
                        player.spawned += 1
                        player.seen_bridge = True
                        player.expansion_cooldown = 0
                        return
                break

    imminent = player.spawned < 2 or ct.get_hp() < ct.get_max_hp()
    if imminent:
        sp = _best_spawn_pos(player, ct, pos)
        if sp is not None:
            ct.spawn_builder(sp)
            player.spawned += 1
            return
