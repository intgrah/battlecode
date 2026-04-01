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


def eliminate_symmetry(player: Player, ct: Controller, w: int, h: int) -> None:

    for tile in ct.get_nearby_tiles():
        if tile not in player.known_env:
            env = ct.get_tile_env(tile)
            player.known_env[tile] = env
            for s in SYM_TYPES:
                if s in player.sym_eliminated:
                    continue

                mirrored = mirror_pos(tile, s, w, h)

                if mirrored in player.known_env:
                    if player.known_env[mirrored] != env:
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
        if etype in SHOULD_FIRE_AT and ct.get_team() != ct.get_team(bid):
            if ct.can_fire(pos):
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

    if player.mode in ("advance", "secure"):
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
        best_dist = 999999
        for o in player.known_ore:
            if ct.is_in_vision(o):
                bid = ct.get_tile_building_id(o)
                if bid is not None and ct.get_entity_type(bid) == EntityType.HARVESTER:
                    continue
                d = chebyshev(o, player.core_pos)
                if d < best_dist:
                    best_dist = d
                    best = o
        if best is not None:
            player.nearest_ore = best

    # for p in player.known_env.keys():
    #    ct.draw_indicator_dot(p, 255, 0, 0)

    # ── Mode transitions ────────────────────────────────────────────

    if player.mode is None:
        my_team = ct.get_team()
        if ct.get_current_round() > 2:
            player.mode = "advance"
        elif ct.get_current_round() > 1:
            player.mode = "secure"
        else:
            player.mode = "advance"

    # Core damaged — drop everything and heal
    if player.core_pos is not None and ct.is_in_vision(player.core_pos):
        core_id = ct.get_tile_building_id(player.core_pos)
        if core_id is not None and ct.get_hp(core_id) < ct.get_max_hp(core_id):
            if player.mode not in ("heal", "bridge"):
                player.mode = "heal"
                player.heal_target = player.core_pos

    # Friendly bridge damaged — heal it (skip if another builder is already on it)
    if player.mode not in ("heal", "bridge"):
        my_team = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) != EntityType.BRIDGE
                or ct.get_team(bid) != my_team
            ):
                continue
            if ct.get_hp(bid) < ct.get_max_hp(bid):
                bp = ct.get_position(bid)
                other = ct.get_tile_builder_bot_id(bp)
                if other is not None and other != ct.get_id():
                    continue
                player.mode = "heal"
                player.heal_target = bp
                break

    if (
        player.mode == "advance"
        and player.core_pos is not None
        and player.nearest_ore is not None
    ):
        coverage = 0.95
        if len(player.known_env) >= coverage * w * h:
            player.mode = "protect"
            player.wander_target = None

    # ── Broken bridge / orphan harvester detection ──────────────────
    if player.mode not in ("bridge", "heal"):
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
                    if ttype == EntityType.BRIDGE and tteam == my_team:
                        continue
                    if ttype == EntityType.CORE and tteam == my_team:
                        continue
                print("bridge leads nowhere, panic!")
                player.mode = "bridge"
                player.bridge_target = bt
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
                        player.bridge_target = bt
                        player.launcher_target = None
                        player.launcher_failed = None
                        break

    # ── Advance: explore map and pathfind to unclaimed ore ─────────
    if player.mode == "advance":
        if player.target is not None:
            player.wander_target = None
            pf_move(player, ct, player.target)
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
            pf_move(player, ct, player.wander_target)
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
                player.mode = "secure"
            pf_move(player, ct, player.wander_target)
        return

    # ── Secure: barrier cardinal neighbors of ore before placing harvester
    if player.mode == "secure":
        if (
            player.secure_target is None
            or player.secure_target not in player.known_ore
            or (
                ct.is_in_vision(player.secure_target)
                and ct.get_entity_type(ct.get_tile_building_id(player.secure_target))
                == EntityType.HARVESTER
            )
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
            if pos == player.wander_target:
                for d in _ALL_DIRS:
                    if try_move_smart(ct, pos, d):
                        break
            else:
                pf_move(player, ct, player.wander_target)
        return

    # ── Bridge: chain bridges from harvester to core ──────────────
    if player.mode == "bridge":
        print(
            f"bridge target {player.bridge_target} launcher target {player.launcher_target}",
        )

        # Try to place launcher adjacent to last bridge before moving on
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
            _finish_bridge_chain(player, ct, pos)
            return

        # Check if target already has a friendly bridge — job done
        if ct.is_in_vision(player.bridge_target):
            target_bid = ct.get_tile_building_id(player.bridge_target)
            if (
                target_bid is not None
                and ct.get_entity_type(target_bid) == EntityType.BRIDGE
                and ct.get_team(target_bid) == ct.get_team()
            ):
                player.mode = "advance"
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

        if _bridge(player, ct, pos):
            if player.launcher_target is not None:
                return  # place launcher next tick before switching mode
            _finish_bridge_chain(player, ct, pos)
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
                    player.mode = "advance"
                    player.target = None
                    player.wander_target = None
                    player.heal_target = None
                    return
            if ct.is_in_vision(ht):
                bid = ct.get_tile_building_id(ht)
                if bid is not None and ct.get_hp(bid) < ct.get_max_hp(bid):
                    if ct.can_heal(pos):
                        ct.heal(pos)
                elif ht == player.core_pos:
                    player.mode = "advance"
                    player.target = None
                    player.wander_target = None
                    player.heal_target = None
                    return
            pf_move(player, ct, ht)
            if ct.can_heal(pos):
                ct.heal(pos)
        return

    # ── Protect: patrol along bridge chain ────────────────────────
    if player.mode == "protect":
        player.visited_bridges.add(pos)
        my_team = ct.get_team()
        core = player.core_pos

        # Only re-pick if no target, target visited, or target occupied
        need_repick = (
            player.wander_target is None
            or player.wander_target in player.known_ore
            or player.wander_target in player.visited_bridges
            or (
                ct.is_in_vision(player.wander_target)
                and ct.get_tile_builder_bot_id(player.wander_target) is not None
            )
        )

        if need_repick:
            on_target = pos == player.wander_target
            min_core_dist = (
                chebyshev(pos, core) if on_target and core is not None else 0
            )
            best = None
            best_dist = -1
            occupied_fallback = None
            occupied_dist = -1
            for bid in ct.get_nearby_buildings():
                if (
                    ct.get_entity_type(bid) != EntityType.BRIDGE
                    or ct.get_team(bid) != my_team
                ):
                    continue
                bp = ct.get_position(bid)
                if bp in player.visited_bridges or bp == player.wander_target:
                    continue
                d = chebyshev(bp, core) if core is not None else chebyshev(pos, bp)
                if d < min_core_dist:
                    continue
                if ct.get_tile_builder_bot_id(bp) is not None:
                    if d > occupied_dist:
                        occupied_dist = d
                        occupied_fallback = bp
                    continue
                if d > best_dist:
                    best_dist = d
                    best = bp
            # Fall back to occupied bridge only if not standing on target and we've visited at least one
            if (
                best is None
                and occupied_fallback is not None
                and not on_target
                and len(player.visited_bridges) > 1
            ):
                best = occupied_fallback
            if best is not None or not on_target:
                player.wander_target = best

        if player.wander_target is not None:
            pf_move(player, ct, player.wander_target)
        elif core is not None:
            pf_move(player, ct, core)
        # elif ct.get_current_round() > 1000 and core is not None and king_dist(pos, core) <= 1:
        #        player.mode = "secure"
        #        player.target = None
        #        player.wander_target = None
        #        return
        return


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
            cd = chebyshev(p, core)
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


def _is_buildable(ct: Controller, tile: Position) -> bool:
    """Check if a tile is empty or only has a marker/road (can be built over)."""
    if ct.get_tile_env(tile) != Environment.EMPTY:
        return False
    bid = ct.get_tile_building_id(tile)
    if bid is None:
        return True
    etype = ct.get_entity_type(bid)
    return (
        etype in (EntityType.ROAD, EntityType.BARRIER, EntityType.LAUNCHER)
    ) and ct.get_team(bid) == ct.get_team()


def _secure(player: Player, ct: Controller, pos: Position) -> bool:
    """Barrier all cardinal neighbors of wander_target, firing to clear
    obstacles if standing on one. Then place harvester and enter bridge mode.
    """
    if player.secure_target is None:
        return False

    # Try to barrier or fire on every cardinal neighbor each turn
    my_team = ct.get_team()
    all_secured = True
    target_adj = False
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

        all_secured = False
        player.wander_target = adj
        target_adj = True

        if ct.can_destroy(adj):
            ct.destroy(adj)
        if ct.can_build_barrier(adj):
            ct.build_barrier(adj)
            return False
        if pos == adj and ct.can_fire(pos):
            ct.fire(pos)
            return False

    print(f"all secured {all_secured}")
    if not all_secured:
        return True

    if target_adj:
        player.wander_target = player.secure_target

    # All cardinal neighbors secured — clear ore tile and place harvester
    if player.secure_target is not None and ct.is_in_vision(player.secure_target):
        bid = ct.get_tile_building_id(player.secure_target)
        if bid is not None and ct.can_destroy(player.secure_target):
            ct.destroy(player.secure_target)

        if pos == player.secure_target:
            for d in _ALL_DIRS:
                if try_move_smart(ct, pos, d):
                    return False

        if ct.can_build_harvester(player.secure_target):
            ct.build_harvester(player.secure_target)
            player.bridge_target = _pick_bridge_start(ct, player.secure_target)
            player.secure_target = None
            player.mode = "bridge"

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
        if not _is_buildable(ct, bp):
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


def _finish_bridge_chain(player: Player, ct: Controller, pos: Position) -> None:
    """Called when the bridge chain is complete. Go back to failed launcher spot or advance."""
    if player.launcher_failed is not None:
        pf_move(player, ct, player.launcher_failed)
    else:
        player.mode = "advance"


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
        if bid is not None and ct.get_entity_type(bid) == EntityType.BRIDGE:
            # Chain already connected at this tile — done
            if king_dist(bt, player.core_pos) <= 1:
                player.bridge_target = None
                return True

    # Adjacent to bridge_target — try to build the next bridge
    if pos.distance_squared(bt) <= 2:
        # Destroy whatever is on the bridge tile (road, marker, etc.)
        if ct.can_destroy(bt):
            ct.destroy(bt)

        # Scan bridge-range tiles (r² <= 9) for the best target closest to core
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

                # Core tile — direct bridge target
                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) == EntityType.CORE
                    and ct.get_team(tbid) == ct.get_team()
                ):
                    core_target = t
                    continue

                # Existing friendly bridge nearer to core
                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) == EntityType.BRIDGE
                    and ct.get_team(tbid) == ct.get_team()
                ):
                    if king_dist(t, player.core_pos) < king_dist(bt, player.core_pos):
                        bridge_candidates.append((king_dist(t, player.core_pos), t))
                    continue

                # Enemy building we can clear
                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) in SHOULD_FIRE_AT
                    and ct.get_team(tbid) != ct.get_team()
                ):
                    enemy_candidates.append((king_dist(t, player.core_pos), t))
                    continue

                if _is_buildable(ct, t):
                    candidates.append((king_dist(t, player.core_pos), t))

        # Priority 1: bridge directly to core
        if core_target is not None and ct.can_build_bridge(bt, core_target):
            ct.build_bridge(bt, core_target)
            player.launcher_target = bt
            player.bridge_target = None
            return True

        # Priority 2: bridge to existing friendly bridge nearer to core
        bridge_candidates.sort()
        for _, target in bridge_candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.launcher_target = bt
                player.bridge_target = None
                return True

        # Priority 3: bridge to tile closest to core
        candidates.sort()
        for _, target in candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.launcher_target = bt
                player.bridge_target = target
                return False

        # Priority 4: bridge onto enemy tile closest to core, then destroy it
        enemy_candidates.sort()
        for _, target in enemy_candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.launcher_target = bt
                player.bridge_target = target
                return False

        print("can't build anywhere")
        return False

    # Not adjacent yet — pathfind to bridge_target
    pf_move(player, ct, bt)
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

    for d in _ALL_DIRS:
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
