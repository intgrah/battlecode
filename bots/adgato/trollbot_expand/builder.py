"""Builder bot logic for trollbot — symmetry detection + walk to unvisited titanium ore."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

import random

from cambc import Controller, Direction, EntityType, Environment, Position
from pathfinding import _ALL_DIRS, _rotate, chebyshev, has_line_of_sight
from utils import (
    BLOCKED_BUILDINGS,
    SYM_TYPES,
    build_walkable,
    get_symmetry_candidates,
    in_bounds,
    king_dist,
    mirror_pos,
    pf_move,
    try_move_smart,
)

SHOULD_FIRE_AT = frozenset(
    {EntityType.ROAD, EntityType.CONVEYOR, EntityType.BRIDGE, EntityType.SPLITTER},
)

# Cardinals first, then diagonals — used for launcher placement priority
_CARDINAL_FIRST = [
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
]


def eliminate_symmetry(player: Player, ct: Controller, w: int, h: int) -> None:

    for tile in ct.get_nearby_tiles():
        if tile not in player.known_env:
            env = ct.get_tile_env(tile)
            player.known_env[tile] = env
            for s in SYM_TYPES:
                if s in player.sym_eliminated:
                    continue

                mirrored = mirror_pos(tile, s, w, h)

                if mirrored in player.known_env and player.known_env[mirrored] != env:
                    player.sym_eliminated.add(s)

    if player.sym_resolved is not None:
        print(player.sym_resolved)
        return

    if player.sym_candidates is None:
        if player.core_pos is not None:
            player.sym_candidates = get_symmetry_candidates(player.core_pos, w, h)
        else:
            print("no candidates")
            return

    remaining = [s for s in SYM_TYPES if s not in player.sym_eliminated]

    resolved_sym = None
    resolved_pos = None
    if len(remaining) == 1:
        resolved_sym = remaining[0]
        resolved_pos = player.sym_candidates[remaining[0]]
    elif len(remaining) > 1:
        positions = {player.sym_candidates[s] for s in remaining}
        if len(positions) == 1:
            resolved_sym = remaining[0]
            resolved_pos = positions.pop()

    if resolved_sym and resolved_pos:
        player.sym_resolved = resolved_sym
        player.enemy_core = resolved_pos

        player.known_ore.update(
            {mirror_pos(ore, player.sym_resolved, w, h) for ore in player.known_ore},
        )

        print(player.sym_resolved)
    else:
        print(remaining)


def scan_ore(player: Player, ct: Controller, w: int, h: int) -> None:
    """Record visible titanium ore tiles."""
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) == Environment.ORE_TITANIUM:
            player.known_ore.add(tile)
            if player.sym_resolved:
                player.known_ore.add(mirror_pos(tile, player.sym_resolved, w, h))


def update_claimed_ore(player: Player, ct: Controller, pos: Position) -> None:
    """Claim ore we're standing on, and mark visible ore as claimed if already taken."""
    my_team = ct.get_team()
    for ore in list(player.known_ore):
        if not ct.is_in_vision(ore):
            continue

        other = ct.get_tile_builder_bot_id(ore)
        if other is not None and other != ct.get_id() and ct.get_team(other) == my_team:
            player.claimed_ore.add(ore)
            continue

        bid = ct.get_tile_building_id(ore)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            if (my_team == ct.get_team(bid) and etype != EntityType.ROAD) or (
                etype not in SHOULD_FIRE_AT and etype != EntityType.HARVESTER
            ):
                player.claimed_ore.add(ore)

    remove_ore = set()
    for ore in list(player.claimed_ore):
        if not ct.is_in_vision(ore):
            continue

        other = ct.get_tile_builder_bot_id(ore)
        if other is not None and other != ct.get_id() and ct.get_team(other) == my_team:
            continue

        bid = ct.get_tile_building_id(ore)
        if bid is None:
            remove_ore.add(ore)
        else:
            etype = ct.get_entity_type(bid)
            same_team = my_team == ct.get_team(bid)
            if etype in (EntityType.ROAD, EntityType.CONVEYOR) or (
                not same_team and etype == EntityType.HARVESTER
            ):
                remove_ore.add(ore)

    player.claimed_ore.difference_update(remove_ore)

    if player.target is not None and player.target in player.claimed_ore:
        player.target = None


def pick_ore_target(player: Player, ct: Controller, pos: Position) -> None:
    """Pick nearest unclaimed ore, preferring tiles with line of sight."""
    best_los = None
    best_los_dist = 999999
    best_any = None
    best_any_dist = 999999

    my_id = ct.get_id()
    for ore in player.known_ore:
        if ore in player.claimed_ore:
            continue
        if ct.is_in_vision(ore):
            other = ct.get_tile_builder_bot_id(ore)
            if other is not None and other != my_id:
                continue
        d = chebyshev(pos, ore)
        if d < best_any_dist and player.target is None:
            best_any_dist = d
            best_any = ore
        if d < best_los_dist and has_line_of_sight(pos, ore, player.walkable):
            best_los_dist = d
            best_los = ore

    # Prefer LOS target, fall back to nearest known
    best = best_los if best_los is not None else best_any
    if best is not None:
        player.target = best


def destroy_enemy_road(
    player: Player,
    ct: Controller,
    pos: Position,
    move_after: bool = True,
) -> bool:

    bid = ct.get_tile_building_id(pos)
    if bid is not None:
        etype = ct.get_entity_type(bid)
        if (
            etype in SHOULD_FIRE_AT
            and ct.get_team() != ct.get_team(bid)
            and ct.can_fire(pos)
        ):
            ct.fire(pos)
            return True
    elif move_after:
        for d in _ALL_DIRS:
            if try_move_smart(ct, pos, d):
                break

    return False


def build_sentinel_by_harvester(player: Player, ct: Controller, pos: Position) -> bool:

    if player.target is None or not ct.is_in_vision(player.target):
        return False

    bid = ct.get_tile_building_id(player.target)
    if bid is not None:
        etype = ct.get_entity_type(bid)
        if etype == EntityType.HARVESTER and ct.get_team() != ct.get_team(bid):
            hp = ct.get_position(bid)
            my_team = ct.get_team()

            # Skip if there's already a friendly sentinel adjacent to this harvester
            for d in _ALL_DIRS:
                adj = hp.add(d)
                if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
                    continue
                adj_bid = ct.get_tile_building_id(adj)
                if (
                    adj_bid is not None
                    and ct.get_entity_type(adj_bid) == EntityType.SENTINEL
                    and ct.get_team(adj_bid) == my_team
                ):
                    return False

            # If no adjacent tile to harvester is free or a friendly road,
            # and we are adjacent to harvester and standing on an enemy road,
            # destroy it to make space
            has_free_adj = False
            for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
                sp = hp.add(d)
                if not in_bounds(ct, adj) or not ct.is_in_vision(sp):
                    continue
                sp_bid = ct.get_tile_building_id(sp)
                if sp_bid is None:
                    if ct.get_tile_env(sp) == Environment.WALL:
                        continue
                    has_free_adj = True
                    break
                etype = ct.get_entity_type(sp_bid)
                if etype == EntityType.MARKER or (
                    ct.get_entity_type(sp_bid) == EntityType.ROAD
                    and ct.get_team(sp_bid) == my_team
                ):
                    has_free_adj = True
                    break
            if not has_free_adj and pos.distance_squared(hp) <= 1:
                destroy_enemy_road(player, ct, pos)
                return True

            (sentinel_cost, _) = ct.get_sentinel_cost()
            (funds, _) = ct.get_global_resources()

            for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
                sp = hp.add(d)

                if not in_bounds(ct, adj) or not ct.is_in_vision(sp):
                    continue

                sp_bid = ct.get_tile_building_id(sp)
                if ct.get_entity_type(sp_bid) == EntityType.ROAD and ct.can_destroy(sp):
                    ct.destroy(sp)

                if ct.can_build_sentinel(sp, _rotate(d, 3)):
                    ct.build_sentinel(sp, _rotate(d, 3))
                    return True
                if ct.can_build_sentinel(sp, _rotate(d, 5)):
                    ct.build_sentinel(sp, _rotate(d, 5))
                    return True
                if sentinel_cost > funds:
                    return True
    return False


def run_builder(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    w, h = ct.get_map_width(), ct.get_map_height()

    player.walkable = build_walkable(ct)
    prev = player.prev_pos if player.prev_pos is not None else pos
    player.prev_pos = pos

    print(player.mode)

    if player.core_pos is None:
        for bid in ct.get_nearby_units():
            if ct.get_entity_type(
                bid,
            ) == EntityType.CORE and ct.get_team() == ct.get_team(bid):
                player.core_pos = ct.get_position(bid)
                for s in SYM_TYPES:
                    if s in player.sym_eliminated:
                        continue
                    mirrored = mirror_pos(player.core_pos, s, w, h)
                    if mirrored == player.core_pos:
                        player.sym_eliminated.add(s)
                break

    if player.mode is None or player.mode in ("advance", "secure", "builder"):
        eliminate_symmetry(player, ct, w, h)
        scan_ore(player, ct, w, h)
        update_claimed_ore(player, ct, pos)

    if player.mode == "advance":
        pick_ore_target(player, ct, pos)

        if (
            player.target is not None
            and pos == player.target
            and destroy_enemy_road(player, ct, pos)
        ):
            return

        if build_sentinel_by_harvester(player, ct, pos):
            return
        if player.target is not None and ct.is_in_vision(player.target):
            bid = ct.get_tile_building_id(player.target)
            if (
                bid is not None
                and ct.get_entity_type(bid) == EntityType.ROAD
                and ct.can_destroy(player.target)
            ):
                ct.destroy(player.target)

            if ct.can_build_barrier(player.target):
                ct.build_barrier(player.target)

    # Track nearest ore to core
    if player.core_pos is not None and player.known_ore:
        best = None
        any_in_vision = False
        best_dist = 999999
        for o in player.known_ore:
            if ct.is_in_vision(o):
                any_in_vision = True
                bid = ct.get_tile_building_id(o)
                bbid = ct.get_tile_builder_bot_id(o)
                if bid is not None and ct.get_entity_type(bid) == EntityType.HARVESTER:
                    continue
                if (
                    bid is not None
                    and ct.get_entity_type(bid) in BLOCKED_BUILDINGS
                    and ct.get_team() != ct.get_team(bid)
                ):
                    continue
                if bbid is not None and bbid != ct.get_id():
                    continue
                d = chebyshev(o, player.core_pos)
                if d < best_dist:
                    best_dist = d
                    best = o
        if best is not None or any_in_vision:
            player.nearest_ore = best

    # for p in player.known_env.keys():
    #    ct.draw_indicator_dot(p, 255, 0, 0)

    # ── Mode transitions ────────────────────────────────────────────

    if player.mode is None:
        my_team = ct.get_team()

        # Guard mode: enemy builder cardinally adjacent, or friendly gunner facing empty tile
        should_guard = False
        for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
            adj = pos.add(d)
            if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
                continue
            bbid = ct.get_tile_builder_bot_id(adj)
            if bbid is not None and ct.get_team(bbid) != my_team:
                should_guard = True
                break
        if not should_guard:
            for bid in ct.get_nearby_buildings():
                if (
                    ct.get_entity_type(bid) != EntityType.GUNNER
                    or ct.get_team(bid) != my_team
                ):
                    continue
                gp = ct.get_position(bid)
                facing = ct.get_direction(bid)
                front = gp.add(facing)
                if not in_bounds(ct, front) or not ct.is_in_vision(front):
                    continue
                front_bid = ct.get_tile_building_id(front)
                if (
                    front_bid is None
                    or ct.get_entity_type(front_bid) == EntityType.ROAD
                ):
                    should_guard = True
                    break
        if should_guard:
            player.mode = "guard"
            player.original_mode = "secure"
        elif ct.get_current_round() > 2:
            player.mode = "secure"
            player.original_mode = "secure"
        else:
            player.mode = "builder"
            player.original_mode = "advance"

    # Core damaged — drop everything and heal
    if player.core_pos is not None and ct.is_in_vision(player.core_pos):
        core_id = ct.get_tile_building_id(player.core_pos)
        if (
            core_id is not None
            and ct.get_hp(core_id) < ct.get_max_hp(core_id)
            and player.mode not in ("heal", "bridge", "guard")
        ):
            player.mode = "heal"
            player.heal_target = player.core_pos

    # Friendly bridge damaged — heal it (skip if another builder is already on it)
    # if player.mode not in ("heal", "bridge", "guard"):
    #    my_team = ct.get_team()
    #    for bid in ct.get_nearby_buildings():
    #        if (
    #            ct.get_entity_type(bid) != EntityType.BRIDGE
    #            or ct.get_team(bid) != my_team
    #        ):
    #            continue
    #        if ct.get_hp(bid) < ct.get_max_hp(bid):
    #            bp = ct.get_position(bid)
    #            other = ct.get_tile_builder_bot_id(bp)
    #            if other is not None and other != ct.get_id():
    #                continue
    #            player.mode = "heal"
    #            player.heal_target = bp
    #            break

    # Opportunistic: place launcher next to any friendly bridge missing one
    my_team = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.BRIDGE or ct.get_team(bid) != my_team:
            continue
        bp = ct.get_position(bid)
        if _has_launcher_adjacent(ct, bp):
            continue
        for d in _CARDINAL_FIRST:
            adj = bp.add(d)
            if in_bounds(ct, adj) and ct.can_build_launcher(adj):
                ct.build_launcher(adj)
                break
        else:
            continue
        break

    # if player.mode == "advance" and ct.get_current_round() > 100:
    #    player.mode = "secure"
    #    player.wander_target = None

    if (
        player.mode == "advance"
        and player.core_pos is not None
        and player.nearest_ore is not None
    ):
        coverage = 0.95
        if len(player.known_env) >= coverage * w * h:
            player.mode = "secure"
            player.wander_target = None

    # ── Broken bridge / orphan harvester detection ──────────────────
    if player.mode not in ("bridge", "heal", "builder", "guard"):
        my_team = ct.get_team()
        for bid in ct.get_nearby_buildings():
            etype = ct.get_entity_type(bid)
            if ct.get_team(bid) != my_team:
                continue

            if etype == EntityType.BRIDGE:
                bt = ct.get_bridge_target(bid)
                if not ct.is_in_vision(bt):
                    continue
                target_bid = ct.get_tile_building_id(bt)
                if target_bid is not None:
                    ttype = ct.get_entity_type(target_bid)
                    tteam = ct.get_team(target_bid)
                    if (
                        ttype in (EntityType.BRIDGE, EntityType.SPLITTER)
                    ) and tteam == my_team:
                        continue
                    if ttype == EntityType.CORE and tteam == my_team:
                        continue
                print("bridge leads nowhere, panic!")
                player.mode = "bridge"
                player.bridge_target = bt
                player.bridge_chain_starter = False
                player.launcher_target = None
                player.launcher_failed = None
                break

            if etype == EntityType.HARVESTER:
                hp = ct.get_position(bid)
                has_adj_bridge = False
                for d in (
                    Direction.NORTH,
                    Direction.EAST,
                    Direction.SOUTH,
                    Direction.WEST,
                ):
                    adj = hp.add(d)
                    if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
                        has_adj_bridge = True
                        break
                    adj_bid = ct.get_tile_building_id(adj)
                    if (
                        adj_bid is not None
                        and ct.get_entity_type(adj_bid) == EntityType.BRIDGE
                        and ct.get_team(adj_bid) == my_team
                    ):
                        has_adj_bridge = True
                        break
                if not has_adj_bridge:
                    bt = _pick_bridge_start(ct, hp)
                    if bt is not None:
                        print("orphan harvester, entering bridge mode")
                        player.mode = "bridge"
                        player.secure_target = hp
                        player.bridge_target = bt
                        player.bridge_chain_starter = True
                        player.launcher_target = None
                        player.launcher_failed = None
                        break

    # ── Advance: explore map and pathfind to unclaimed ore ─────────
    if player.mode == "advance":
        if player.target is not None:
            player.wander_target = None
            pf_move(player, ct, player.target, destroy_road=True)
            if pos == player.target:
                destroy_enemy_road(player, ct, pos)
            return

        # Pathfind toward unexplored territory
        prev_wander = player.wander_target
        if (
            player.wander_target is not None
            and player.wander_target in player.known_env
        ):
            player.wander_target = None
        if player.wander_target is None:
            player.wander_target = _pick_frontier_target(player, pos, prev_wander, w, h)
        if player.wander_target is not None:
            pf_move(player, ct, player.wander_target, destroy_road=True)
        else:
            _random_walk(ct, pos, prev)

        return

    # ── Return: go to nearest ore to core and place a harvester ───
    if player.mode == "return":
        if player.wander_target is None or player.wander_target not in player.known_ore:
            player.wander_target = player.nearest_ore
        if player.wander_target is not None:
            if ct.is_in_vision(player.wander_target):
                for bid in ct.get_nearby_buildings():
                    if ct.get_entity_type(
                        bid,
                    ) == EntityType.HARVESTER and ct.get_team() == ct.get_team(bid):
                        return
                player.mode = player.original_mode
            pf_move(player, ct, player.wander_target)
        return

    # ── Secure: barrier cardinal neighbors of ore before placing harvester
    if player.mode == "secure":
        another_claimed_ore = False
        enemy_barrier_on_ore = False
        harvester_on_ore = False

        if player.secure_target is not None and ct.is_in_vision(player.secure_target):
            bbid = ct.get_tile_builder_bot_id(player.secure_target)
            bid = ct.get_tile_building_id(player.secure_target)
            harvester_on_ore = (
                bid is not None and ct.get_entity_type(bid) == EntityType.HARVESTER
            )
            enemy_barrier_on_ore = (
                bid is not None
                and ct.get_entity_type(bid) == EntityType.BARRIER
                and ct.get_team(bid) != ct.get_team()
            )
            another_claimed_ore = bbid is not None and bbid != ct.get_id()
            another_claimed_ore = bbid is not None and bbid != ct.get_id()

        print(
            f"h_on_ore {harvester_on_ore} b_on_ore {enemy_barrier_on_ore} bb_on_ore {another_claimed_ore}",
        )

        if (
            player.secure_target is not None
            or player.secure_target not in player.known_ore
            or enemy_barrier_on_ore
            or harvester_on_ore
            or another_claimed_ore
        ):
            # Pick ore if available, otherwise wander to explore
            if player.nearest_ore is not None:
                player.secure_target = player.nearest_ore
            else:
                prev_wander = player.wander_target
                if (
                    player.wander_target is not None
                    and player.wander_target in player.known_env
                ):
                    player.wander_target = None
                if player.wander_target is None:
                    player.wander_target = _pick_frontier_near_core(
                        player,
                        pos,
                        player.core_pos,
                        w,
                        h,
                    )
                if player.wander_target is not None:
                    pf_move(player, ct, player.wander_target)
                else:
                    _random_walk(ct, pos, prev)
                return
        if _secure(player, ct, pos):
            if player.secure_target is not None and ct.can_destroy(
                player.secure_target,
            ):
                ct.destroy(player.secure_target)
            pf_move(player, ct, player.secure_target)
        return

    # ── Bridge: chain bridges from harvester to core ──────────────
    if player.mode == "bridge":
        print(
            f"bridge target {player.bridge_target} launcher target {player.launcher_target}"
            f" chain_starter={player.bridge_chain_starter}",
        )

        # Try to place launcher adjacent to bridge target before building bridge
        if player.launcher_target is not None:
            result = _place_launcher_by_bridge(player, ct, pos, player.launcher_target)
            if result is True:
                player.launcher_target = None
            elif result is None:
                player.launcher_failed = player.launcher_target
                player.launcher_target = None
            else:
                return

        if player.bridge_target is None:
            player.mode = player.original_mode
            return

        # Check if target already has a friendly bridge — job done
        if ct.is_in_vision(player.bridge_target):
            target_bid = ct.get_tile_building_id(player.bridge_target)
            if (
                target_bid is not None
                and ct.get_entity_type(target_bid) == EntityType.BRIDGE
                and ct.get_team(target_bid) == ct.get_team()
            ):
                player.mode = player.original_mode
                player.bridge_target = None
                return

        # Enemy road on bridge target — move to it and destroy
        if ct.is_in_vision(player.bridge_target):
            target_bid = ct.get_tile_building_id(player.bridge_target)
            if target_bid is not None:
                ttype = ct.get_entity_type(target_bid)
                tteam = ct.get_team(target_bid)
                if ttype in SHOULD_FIRE_AT and tteam != ct.get_team():
                    if pos == player.bridge_target:
                        destroy_enemy_road(player, ct, pos, move_after=False)
                    else:
                        pf_move(player, ct, player.bridge_target)
                    return

        _bridge(player, ct, pos)
        return

    # ── Heal: pathfind to target and heal it ─────────────────────────
    if player.mode == "heal":
        # Re-evaluate: core damage always takes priority
        if player.core_pos is not None and ct.is_in_vision(player.core_pos):
            core_id = ct.get_tile_building_id(player.core_pos)
            if core_id is not None and ct.get_hp(core_id) < ct.get_max_hp(core_id):
                player.heal_target = player.core_pos
        ht = player.heal_target
        if ht is not None:
            # If another builder is already on our bridge target, give up
            if ht != player.core_pos and ct.is_in_vision(ht):
                other = ct.get_tile_builder_bot_id(ht)
                if other is not None and other != ct.get_id():
                    player.mode = player.original_mode
                    player.target = None
                    player.wander_target = None
                    player.heal_target = None
                    return
            if ct.is_in_vision(ht):
                bid = ct.get_tile_building_id(ht)
                if bid is not None and ct.get_hp(bid) < ct.get_max_hp(bid):
                    if ct.can_heal(pos):
                        ct.heal(pos)
                        return
                elif pos == player.heal_target:
                    player.mode = player.original_mode
                    player.target = None
                    player.wander_target = None
                    player.heal_target = None
                    return
            pf_move(player, ct, ht)
            if ct.can_heal(pos):
                ct.heal(pos)
        return

    # ── Guard: defend core from enemy builder ───────────────────────
    if player.mode == "guard":
        _guard(player, ct, pos)
        return

    # ── Builder: place defences around core ─────────────────────────
    if player.mode == "builder":
        _builder(player, ct, pos, w, h)
        return


def _guard(player: Player, ct: Controller, pos: Position) -> None:
    """Defend core from enemy builder bot."""
    for d in _ALL_DIRS:
        t = pos.add(d)
        if not in_bounds(ct, t) or not ct.is_in_vision(t):
            continue
        bbid = ct.get_tile_builder_bot_id(t)
        if (
            bbid is None or ct.get_team(bbid) == ct.get_team()
        ) and ct.can_build_conveyor(t, Direction.NORTH):
            ct.build_conveyor(t, Direction.NORTH)


def _builder(player: Player, ct: Controller, pos: Position, w: int, h: int) -> None:
    """Place defences around core: conveyor on cardinal spots, gunners/launchers/barriers around them."""
    core = player.core_pos
    if core is None:
        player.mode = player.original_mode
        return

    if not player.builder_targets:
        tx = player.nearest_ore.x if player.nearest_ore is not None else w / 2
        ty = player.nearest_ore.y if player.nearest_ore is not None else h / 2
        target_pos = Position(int(tx), int(ty))
        candidates = [
            Position(core.x, core.y - 2),
            Position(core.x + 2, core.y),
            Position(core.x, core.y + 2),
            Position(core.x - 2, core.y),
        ]
        valid = [
            p
            for p in candidates
            if in_bounds(ct, p)
            and (not ct.is_in_vision(p) or ct.get_tile_env(p) != Environment.WALL)
        ]
        valid.sort(key=lambda p: king_dist(p, target_pos))
        player.builder_targets = valid[:1]
        player.builder_target_idx = 0

    if player.builder_target_idx >= len(player.builder_targets):
        # Find a friendly gunner and target the tile opposite its facing direction
        my_team = ct.get_team()
        sp_target: Position | None = None
        sp_dir: Direction | None = None
        has_splitter = False
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) == EntityType.GUNNER
                and ct.get_team(bid) == my_team
            ):
                gp = ct.get_position(bid)
                facing = ct.get_direction(bid)
                sp_target = gp.add(facing.opposite())
                sp_dir = facing
                break
        # Check if we can already see a friendly splitter
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) == EntityType.SPLITTER
                and ct.get_team(bid) == my_team
            ):
                has_splitter = True
                break

        if has_splitter:
            # Bridge from a tile adjacent to a launcher into the core
            for bid in ct.get_nearby_buildings():
                if (
                    ct.get_entity_type(bid) != EntityType.LAUNCHER
                    or ct.get_team(bid) != my_team
                ):
                    continue
                lp = ct.get_position(bid)
                for d in _CARDINAL_FIRST:
                    bp = lp.add(d)
                    if not in_bounds(ct, bp) or not ct.is_in_vision(bp):
                        continue
                    fbid = ct.get_tile_building_id(bp)
                    if (
                        fbid is not None
                        and ct.get_entity_type(fbid) == EntityType.ROAD
                        and ct.can_destroy(bp)
                    ):
                        ct.destroy(bp)
                    for dx in range(-1, 2):
                        for dy in range(-1, 2):
                            bt = Position(core.x + dx, core.y + dy)
                            if ct.can_build_bridge(bp, bt):
                                ct.build_bridge(bp, bt)
                                player.mode = player.original_mode
                                player.builder_targets = []
                                player.builder_target_idx = 0
                                return
            # Can't build bridge yet, stay in mode
            return

        if sp_target is None:
            player.mode = player.original_mode
            player.builder_targets = []
            player.builder_target_idx = 0
            return

        # Try to build splitter each turn
        if ct.can_destroy(sp_target):
            ct.destroy(sp_target)
        if ct.can_build_splitter(sp_target, sp_dir):
            ct.build_splitter(sp_target, sp_dir)

        # Pathfind to splitter target
        pf_move(player, ct, sp_target)
        return

    target = player.builder_targets[player.builder_target_idx]

    fbid = ct.get_tile_building_id(target)
    if (
        fbid is not None
        and ct.get_entity_type(fbid) != EntityType.CONVEYOR
        and ct.can_destroy(target)
    ):
        ct.destroy(target)

    if ct.can_build_conveyor(target, Direction.NORTH):
        ct.build_conveyor(target, Direction.NORTH)

    if pos == target:
        tx = player.nearest_ore.x if player.nearest_ore is not None else w / 2
        ty = player.nearest_ore.y if player.nearest_ore is not None else h / 2
        ne_sw = (tx - core.x) * (ty - core.y) < 0
        flip = (pos.x == core.x) == ne_sw
        gun_dir = _rotate(core.direction_to(pos), 2 if flip else -2)
        launcher_dir = _rotate(core.direction_to(pos), 1 if flip else -1)

        for d in _ALL_DIRS:
            adj = pos.add(d)
            if not in_bounds(ct, adj):
                continue
            bid = ct.get_tile_building_id(adj)
            if bid is not None and ct.get_entity_type(bid) == EntityType.ROAD:
                ct.destroy(adj)

            if d == launcher_dir:
                if in_bounds(ct, adj) and ct.can_build_launcher(adj):
                    ct.build_launcher(adj)
                    break
            elif d == gun_dir:
                if in_bounds(ct, adj) and ct.can_build_gunner(adj, d.opposite()):
                    ct.build_gunner(adj, d.opposite())
                    splitter_pos = adj.add(d)
                    if (
                        not in_bounds(ct, splitter_pos)
                        or ct.get_tile_env(splitter_pos) == Environment.WALL
                    ):
                        player.mode = player.original_mode
                        return
                    sp_bid = ct.get_tile_building_id(splitter_pos)
                    if (
                        sp_bid is not None
                        and ct.get_entity_type(sp_bid) in BLOCKED_BUILDINGS
                    ):
                        player.mode = player.original_mode
                        return
                    break
            elif in_bounds(ct, adj) and ct.can_build_barrier(adj):
                ct.build_barrier(adj)
                break
        else:
            player.builder_target_idx += 1
    else:
        pf_move(player, ct, target)


def _pick_frontier_target(
    player: Player,
    pos: Position,
    prev_target: Position | None,
    w: int,
    h: int,
) -> Position | None:
    """Pick the best unexplored tile to pathfind toward.
    Biased toward the previous wander direction for continuity; falls back to
    map-centre bias when there is no previous direction.
    """
    cx, cy = w / 2.0, h / 2.0
    centre = Position(cx, cy)

    # Previous direction unit vector (if any)
    if prev_target is not None:
        pdx, pdy = prev_target.x - pos.x, prev_target.y - pos.y
        pmag = max(abs(pdx), abs(pdy), 1)
    else:
        pdx, pdy, pmag = 0, 0, 1

    best = None
    best_score = 999999

    for d in _ALL_DIRS:
        dx, dy = d.delta()
        for dist in range(4):
            radius = (1 + dist) * 4
            px, py = pos.x + radius * dx, pos.y + radius * dy
            if not (0 <= px < w and 0 <= py < h):
                break
            p = Position(px, py)
            if p in player.known_env:
                continue
            centre_dist = chebyshev(p, centre)
            # Dot product with previous direction: higher = more aligned = lower score
            # Normalised to [-1, 1] range, scaled to ±(w+h)/4 so it meaningfully
            # shifts the centre-distance score without overwhelming it.
            align = (dx * pdx + dy * pdy) / pmag
            score = centre_dist / 2 + radius - align * (w + h) / 4
            if score < best_score:
                best_score = score
                best = p
            break  # found first unexplored in this direction

    return best


def _pick_frontier_near_core(
    player: Player,
    pos: Position,
    core: Position,
    w: int,
    h: int,
) -> Position | None:
    """Pick the nearest unexplored tile to core, tie-broken by distance to player."""
    best = None
    best_core_dist = 999999
    best_player_dist = 999999

    for d in _ALL_DIRS:
        dx, dy = d.delta()
        for dist in range(4):
            radius = (1 + dist) * 4
            px, py = pos.x + radius * dx, pos.y + radius * dy
            if not (0 <= px < w and 0 <= py < h):
                break
            p = Position(px, py)
            if p in player.known_env:
                continue
            cd = chebyshev(p, core) if core is not None else 999
            pd = chebyshev(p, pos)
            if cd < best_core_dist or (cd == best_core_dist and pd < best_player_dist):
                best_core_dist = cd
                best_player_dist = pd
                best = p
            break  # found first unexplored in this direction

    return best


def _random_walk(ct: Controller, pos: Position, prev: Position) -> None:
    """Random walk, avoiding stepping back to the previous tile.
    Prefers tiles reachable via can_move (no road building).
    """
    dirs = list(_ALL_DIRS)
    random.shuffle(dirs)
    # 1. Prefer can_move (already walkable), skip prev
    if random.randint(0, 1) == 0:
        for d in dirs:
            if pos.add(d) == prev:
                continue
            if ct.can_move(d):
                ct.move(d)
                return
    # 2. Fall back to try_move_smart (builds road), skip prev
    for d in dirs:
        if pos.add(d) == prev:
            continue
        if try_move_smart(ct, pos, d):
            return
    # 3. Truly stuck — allow backtrack via try_move_smart only
    for d in dirs:
        if try_move_smart(ct, pos, d):
            return


def _is_buildable(ct: Controller, tile: Position, core: Position) -> bool:
    """Check if a tile is empty or only has a marker/road (can be built over)."""
    if ct.get_tile_env(tile) != Environment.EMPTY:
        return False
    bid = ct.get_tile_building_id(tile)
    if bid is None:
        return True
    etype = ct.get_entity_type(bid)
    near_core = core is not None and king_dist(tile, core) <= 2
    return (
        etype == EntityType.ROAD or (etype == EntityType.BARRIER and not near_core)
    ) and ct.get_team(
        bid,
    ) == ct.get_team()


def _secure(player: Player, ct: Controller, pos: Position) -> bool:
    """Barrier all cardinal neighbors of wander_target, firing to clear
    obstacles if standing on one. Then place harvester and enter bridge mode.
    """
    if player.secure_target is None:
        return False

    # Try to barrier or fire on every cardinal neighbor each turn
    my_team = ct.get_team()
    all_secured = True
    for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
        adj = player.secure_target.add(d)
        if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
            continue
        if ct.get_tile_env(adj) == Environment.WALL:
            continue
        bid = ct.get_tile_building_id(adj)

        if bid is not None:
            etype = ct.get_entity_type(bid)
            if etype in BLOCKED_BUILDINGS or etype == EntityType.MARKER:
                continue
            if etype == EntityType.BRIDGE and my_team == ct.get_team(bid):
                continue
            if my_team != ct.get_team(bid) and ct.is_tile_passable(adj):
                if (
                    king_dist(pos, adj) <= 1
                    and try_move_smart(ct, pos, pos.direction_to(adj))
                    and ct.get_position() == adj
                    and ct.can_fire(adj)
                ):
                    ct.fire(adj)
                    return False
                continue

        all_secured = False

        if ct.can_destroy(adj):
            ct.destroy(adj)
        if ct.can_build_barrier(adj):
            ct.build_barrier(adj)
            return False

    bid = ct.get_tile_building_id(pos)
    if (
        bid is not None
        and my_team != ct.get_team(bid)
        and pos == player.secure_target
        and ct.can_fire(pos)
    ):
        ct.fire(pos)
        return False

    print(f"all secured {all_secured}")
    if not all_secured:
        return True

    # All cardinal neighbors secured — clear ore tile and place harvester
    if player.secure_target is not None and ct.is_in_vision(player.secure_target):
        (h_cost, _) = ct.get_harvester_cost()
        (funds, _) = ct.get_global_resources()

        if pos == player.secure_target:
            destroy_enemy_road(player, ct, pos, move_after=False)

        if pos == player.secure_target and h_cost <= funds:
            core_dir = (
                pos.direction_to(player.core_pos)
                if player.core_pos is not None
                else Direction.NORTH
            )
            for rot in (0, 1, -1, 2, -2, 3, -3, 4):
                if try_move_smart(ct, pos, _rotate(core_dir, rot)):
                    break

        bid = ct.get_tile_building_id(player.secure_target)
        if bid is not None and ct.can_destroy(player.secure_target):
            ct.destroy(player.secure_target)

        if ct.can_build_harvester(player.secure_target):
            ct.build_harvester(player.secure_target)
            player.bridge_target = _pick_bridge_start(ct, player.secure_target)
            player.secure_target = None
            player.bridge_chain_starter = True
            player.mode = "bridge"
        else:
            d = pos.direction_to(player.secure_target)
            adj = pos.add(d)
            bar_bid = ct.get_tile_building_id(adj)
            if (
                bar_bid is not None
                and ct.get_entity_type(bar_bid) == EntityType.BARRIER
                and ct.can_destroy(adj)
            ):
                ct.destroy(adj)
            try_move_smart(ct, pos, pos.direction_to(player.secure_target))
            return False

    return True


def _pick_bridge_start(ct: Controller, harvester_pos: Position) -> Position | None:
    """Pick the best cardinal-adjacent tile to a harvester to start a bridge chain.
    Returns the buildable tile closest to the bot, or None.
    If prefer_empty, tries tiles with no building first.
    """
    pos = ct.get_position()
    best = None
    best_dist = 999999
    fallback = None
    fallback_dist = 999999
    team = ct.get_team()
    for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
        bp = harvester_pos.add(d)
        if not in_bounds(ct, bp) or not ct.is_in_vision(bp):
            continue
        if not _is_buildable(ct, bp, None):
            continue
        dist = king_dist(bp, pos)
        bid = ct.get_tile_building_id(bp)
        if bid is None or (
            ct.get_team(bid) == team and ct.get_entity_type(bid) == EntityType.ROAD
        ):
            if dist < best_dist:
                best_dist = dist
                best = bp
        elif dist < fallback_dist:
            fallback_dist = dist
            fallback = bp
    if best is not None:
        return best
    return fallback if best is None else best


def _bridge(player: Player, ct: Controller, pos: Position) -> bool:
    """Build a chain of bridges from the last bridge_target toward the core.
    Returns True if the chain has reached the core.
    """
    bt = player.bridge_target
    if bt is None or player.core_pos is None:
        player.bridge_target = None
        return False

    # If bridge_target already has a bridge on it, the chain continues from here
    if ct.is_in_vision(bt):
        bid = ct.get_tile_building_id(bt)
        # Chain already connected at this tile — done
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.BRIDGE
            and king_dist(bt, player.core_pos) <= 1
        ):
            player.bridge_target = None
            player.mode = player.original_mode
            player.wander_target = None
            return True

    # Adjacent to bridge_target — try to build the next bridge
    if pos.distance_squared(bt) <= 2:
        # Place launcher adjacent to bridge_target before building the bridge
        if not _has_launcher_adjacent(ct, bt) and player.launcher_failed != bt:
            result = _place_launcher_by_bridge(player, ct, pos, bt)
            if result is None:
                player.launcher_failed = bt
            elif result is not True:
                player.launcher_target = bt
                return False

        (funds, _) = ct.get_global_resources()
        (bc, _) = ct.get_bridge_cost()
        if bc > funds:
            print("can't afford bridge")
            return False

        tbid = ct.get_tile_building_id(bt)
        # Destroy whatever is on the bridge tile (road, marker, etc.)
        if ct.can_destroy(bt):
            ct.destroy(bt)

        # Scan bridge-range tiles (r² <= 9) for the best target closest to core
        splitter_target = None
        core_target = None
        bridge_candidates = []
        candidates = []
        enemy_candidates = []

        for dx in range(-3, 4):
            for dy in range(-3, 4):
                t = Position(bt.x + dx, bt.y + dy)
                t_dist = bt.distance_squared(t)
                if t_dist > 9 or t_dist == 0:
                    continue
                if not in_bounds(ct, t) or not ct.is_in_vision(t):
                    continue

                tbid = ct.get_tile_building_id(t)
                same_team = tbid is not None and ct.get_team(tbid) == ct.get_team()

                # Friendly splitter — highest priority target
                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) == EntityType.SPLITTER
                    and same_team
                ):
                    splitter_target = t
                    continue

                # Core tile — direct bridge target
                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) == EntityType.CORE
                    and same_team
                ):
                    core_target = t
                    continue

                # Existing friendly bridge nearer to core
                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) == EntityType.BRIDGE
                    and same_team
                ):
                    if king_dist(t, player.core_pos) < king_dist(bt, player.core_pos):
                        bridge_candidates.append((king_dist(t, player.core_pos), t))
                    continue

                # Enemy building we can clear
                if tbid is not None and (
                    (ct.get_entity_type(tbid) == EntityType.LAUNCHER and same_team)
                    or (ct.get_entity_type(tbid) in SHOULD_FIRE_AT and not same_team)
                ):
                    enemy_candidates.append((king_dist(t, player.core_pos), t))
                    continue

                if _is_buildable(ct, t, player.core_pos):
                    candidates.append((king_dist(t, player.core_pos), t))

        # Priority 0: bridge to friendly splitter
        if splitter_target is not None and ct.can_build_bridge(bt, splitter_target):
            ct.build_bridge(bt, splitter_target)
            player.bridge_target = None
            player.mode = player.original_mode
            return True

        # Priority 1: bridge directly to core
        if core_target is not None and ct.can_build_bridge(bt, core_target):
            ct.build_bridge(bt, core_target)
            player.bridge_target = None
            player.mode = player.original_mode
            return True

        # Priority 2: bridge to existing friendly bridge nearer to core
        bridge_candidates.sort()
        for _, target in bridge_candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.bridge_target = None
                player.mode = player.original_mode
                return True

        # Priority 3: bridge to tile closest to core
        candidates.sort()
        for _, target in candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.bridge_target = target
                pf_move(player, ct, target)
                return False

        # Priority 4: bridge onto enemy tile closest to core, then destroy it
        enemy_candidates.sort()
        for _, target in enemy_candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.bridge_target = target
                pf_move(player, ct, target)
                return False

        print("can't build anywhere")
        return False

    # Not adjacent yet — pathfind to bridge_target
    pf_move(player, ct, bt)
    return False


def _has_launcher_adjacent(ct: Controller, bridge_pos: Position) -> bool:
    """Check if there is already a friendly launcher adjacent to bridge_pos."""
    my_team = ct.get_team()
    for d in _ALL_DIRS:
        adj = bridge_pos.add(d)
        if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
            continue
        bid = ct.get_tile_building_id(adj)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.LAUNCHER
            and ct.get_team(bid) == my_team
        ):
            return True
    return False


def _place_launcher_by_bridge(
    player: Player,
    ct: Controller,
    pos: Position,
    bridge_pos: Position,
) -> bool:
    """Try to build a launcher adjacent to bridge_pos. Returns True if done (built or gave up)."""
    if not ct.is_in_vision(bridge_pos):
        pf_move(player, ct, bridge_pos)
        return False

    (funds, _) = ct.get_global_resources()
    (lc, _) = ct.get_launcher_cost()
    if lc > funds:
        if ct.can_build_road(bridge_pos):
            ct.build_road(bridge_pos)
        return False

    my_team = ct.get_team()

    # Already have a launcher adjacent — skip
    for d in _ALL_DIRS:
        adj = bridge_pos.add(d)
        if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
            continue
        bid = ct.get_tile_building_id(adj)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.LAUNCHER
            and ct.get_team(bid) == my_team
        ):
            return True

    # try without destroying first
    for d in _CARDINAL_FIRST:
        adj = bridge_pos.add(d)
        if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
            continue
        if ct.can_build_launcher(adj):
            ct.build_launcher(adj)
            return True

    for d in _CARDINAL_FIRST:
        adj = bridge_pos.add(d)
        if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is not None:
            etype = ct.get_entity_type(bid)
            if (
                etype in (EntityType.BARRIER, EntityType.ROAD)
                and ct.get_team(bid) == my_team
            ) and ct.can_destroy(adj):
                ct.destroy(adj)
        if ct.can_build_launcher(adj):
            ct.build_launcher(adj)
            return True

    # No valid spot — give up
    return None
