"""Core unit logic for trollbot — spawn one builder bot."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, EntityType, Environment, Position
from pathfinding import _ALL_DIRS, _rotate, chebyshev
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

    (funds, _) = ct.get_global_resources()
    (builder_cost, _) = ct.get_builder_bot_cost()
    (harvester_cost, _) = ct.get_builder_bot_cost()

    print(f"funds {funds}. bb {builder_cost}")

    can_afford = funds > builder_cost * 3 + harvester_cost + 100

    if can_afford and ct.get_current_round() > 300:
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) == EntityType.BRIDGE
                and ct.get_team(bid) == my_team
            ) and ct.get_bridge_target(bid).distance_squared(ct.get_position()) <= 2:
                player.expansion_cooldown += 1
                if player.expansion_cooldown > 50 and can_afford:
                    sp = _best_spawn_pos(player, ct, pos)
                    if sp is not None:
                        ct.spawn_builder(sp)
                        player.spawned += 1
                        player.seen_bridge = True
                        player.expansion_cooldown = 0
                        return
                break

    # Emergency spawn if enemy builder on a friendly conveyor
    enemy_builder_dir = None
    for uid in ct.get_nearby_units():
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT or ct.get_team(uid) == my_team:
            continue
        bp = ct.get_position(uid)
        bid = ct.get_tile_building_id(bp)
        if bid is not None and ct.get_entity_type(bid) == EntityType.CONVEYOR and ct.get_team(bid) == my_team:
            enemy_builder_dir = pos.direction_to(bp)
            break
    if enemy_builder_dir is not None:
        sp = pos.add(enemy_builder_dir)
        if ct.can_spawn(sp):
            ct.spawn_builder(sp)
            player.spawned += 1
            return

    # Spawn builder if a friendly gunner is facing an empty tile
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.GUNNER or ct.get_team(bid) != my_team:
            continue
        gp = ct.get_position(bid)
        facing = ct.get_direction(bid)
        front = gp.add(facing)
        if not in_bounds(ct, front) or not ct.is_in_vision(front):
            continue
        front_bid = ct.get_tile_building_id(front)
        if front_bid is None or ct.get_entity_type(front_bid) == EntityType.ROAD:
            sp = pos.add(pos.direction_to(front))
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                player.spawned += 1
                return
            break

    imminent = player.spawned < 1 or player.spawned < 2 and rnd > 10 or ct.get_hp() < ct.get_max_hp()
    if imminent:
        sp = _best_spawn_pos(player, ct, pos)
        if sp is not None:
            ct.spawn_builder(sp)
            player.spawned += 1
            return
