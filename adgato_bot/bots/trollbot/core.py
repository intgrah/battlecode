"""Core unit logic for trollbot — spawn one builder bot."""

from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import Player

from cambc import Controller, EntityType, Position

from pathfinding import chebyshev

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

    # Check if the tracked bridge has been destroyed
    bridge_destroyed = player.nearest_bridge_id is not None and best_bridge is None

    print(f"resource turn {rnd - player.last_resource_turn} bridge_destroyed {bridge_destroyed}")
    # Spawn a builder if bridge has had no resources for 5+ turns, or bridge was destroyed
    if player.nearest_bridge_id is not None and (rnd - player.last_resource_turn >= 5 or bridge_destroyed):
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                p = Position(pos.x + dx, pos.y + dy)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    player.spawned += 1
                    player.last_resource_turn = rnd
                    return

    
    (funds, _) = ct.get_global_resources()
    (builder_cost, _) = ct.get_builder_bot_cost()

    can_afford = funds > builder_cost + 300

    if not can_afford or player.expansion_cooldown <= 5:
        for bid in ct.get_nearby_buildings():
            if ct.get_entity_type(bid) == EntityType.BRIDGE and ct.get_team(bid) == my_team:
                if ct.get_bridge_target(bid).distance_squared(ct.get_position()) <= 2:
                    player.expansion_cooldown += 1
                    if player.expansion_cooldown > 5 and can_afford:
                        for dx in range(-1, 2):
                            for dy in range(-1, 2):
                                p = Position(pos.x + dx, pos.y + dy)
                                if ct.can_spawn(p):
                                    ct.spawn_builder(p)
                                    player.spawned += 1
                                    player.seen_bridge = True
                                    return
                    break

    imminent = player.spawned < 2 or ct.get_hp() < ct.get_max_hp()
    if imminent:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                p = Position(pos.x + dx, pos.y + dy)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    player.spawned += 1
                    return
