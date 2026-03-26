from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

import random

from cambc import Controller, Direction, EntityType, Environment, Position
from known_maps import MAPS, decode
from pathfinding import _ALL_DIRS, _rotate, chebyshev, has_line_of_sight
from utils import (
    BLOCKED_BUILDINGS,
    SYM_TYPES,
    BuilderMode,
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

                if mirrored in player.known_env and player.known_env[mirrored] != env:
                    player.sym_eliminated.add(s)

    if player.sym_resolved is not None:
        print(player.sym_resolved.value)
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

        print(player.sym_resolved.value)
    else:
        print(remaining)


def scan_ore(player: Player, ct: Controller, w: int, h: int) -> None:
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) == Environment.ORE_TITANIUM:
            player.known_ore.add(tile)
            if player.sym_resolved:
                player.known_ore.add(mirror_pos(tile, player.sym_resolved, w, h))


def update_claimed_ore(player: Player, ct: Controller, pos: Position) -> None:
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

    remove_ore: set[Position] = set()
    for ore in list(player.claimed_ore):
        if not ct.is_in_vision(ore):
            continue
        bid = ct.get_tile_building_id(ore)
        if bid is None:
            remove_ore.add(ore)
        else:
            etype = ct.get_entity_type(bid)
            same_team = my_team == ct.get_team(bid)
            if same_team and etype == EntityType.ROAD:
                remove_ore.add(ore)
            if not same_team and etype == EntityType.HARVESTER:
                remove_ore.add(ore)

    player.claimed_ore.difference_update(remove_ore)

    if player.target is not None and player.target in player.claimed_ore:
        player.target = None


def pick_ore_target(player: Player, ct: Controller, pos: Position) -> None:
    best_los = None
    best_los_dist = 999999
    best_any = None
    best_any_dist = 999999

    for ore in player.known_ore:
        if ore in player.claimed_ore:
            continue
        d = chebyshev(pos, ore)
        if d < best_any_dist and player.target is None:
            best_any_dist = d
            best_any = ore
        if d < best_los_dist and has_line_of_sight(pos, ore, player.walkable):
            best_los_dist = d
            best_los = ore

    best = best_los if best_los is not None else best_any
    if best is not None:
        player.target = best


def destroy_enemy_road(
    _player: Player,
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
    if bid is None:
        return False
    etype = ct.get_entity_type(bid)
    if etype != EntityType.HARVESTER or ct.get_team() == ct.get_team(bid):
        return False

    hp = ct.get_position(bid)
    my_team = ct.get_team()

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


def _try_hardcode(player: Player, w: int, h: int) -> None:
    if player.core_pos is None:
        return
    key = (w, h, player.core_pos.x, player.core_pos.y)
    known = MAPS.get(key)
    if known is None:
        return
    encoded, (ecx, ecy) = known
    n = w * h
    tiles = decode(encoded, n)
    for i in range(n):
        x, y = i % w, i // w
        p = Position(x, y)
        player.known_env[p] = tiles[i]
        if tiles[i] == Environment.ORE_TITANIUM:
            player.known_ore.add(p)
    player.enemy_core = Position(ecx, ecy)
    player.sym_eliminated = set(SYM_TYPES)
    for s in SYM_TYPES:
        cands = get_symmetry_candidates(player.core_pos, w, h)
        if cands[s] == player.enemy_core:
            player.sym_resolved = s
            player.sym_eliminated.discard(s)
            break

    if player.known_ore:
        best = None
        best_dist = 999999
        for o in player.known_ore:
            d = chebyshev(o, player.core_pos)
            if d < best_dist:
                best_dist = d
                best = o
        player.nearest_ore = best

    print(f"hardcoded map {w}x{h}, enemy core at ({ecx},{ecy})")


def run_builder(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    w, h = ct.get_map_width(), ct.get_map_height()

    player.walkable = build_walkable(ct)
    prev = player.prev_pos if player.prev_pos is not None else pos
    player.prev_pos = pos

    print(player.mode.value if player.mode is not None else None)

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
                _try_hardcode(player, w, h)
                break

    if player.mode in (BuilderMode.ADVANCE, BuilderMode.SECURE):
        eliminate_symmetry(player, ct, w, h)
        scan_ore(player, ct, w, h)
        update_claimed_ore(player, ct, pos)

    if player.mode == BuilderMode.ADVANCE:
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

    if player.mode is None:
        if player.nearest_ore is not None and player.enemy_core is not None:
            player.mode = BuilderMode.SECURE
        elif ct.get_current_round() > 2:
            player.mode = BuilderMode.ADVANCE
        elif ct.get_current_round() > 1:
            player.mode = BuilderMode.SECURE
        else:
            player.mode = BuilderMode.ADVANCE

    if player.core_pos is not None and ct.is_in_vision(player.core_pos):
        core_id = ct.get_tile_building_id(player.core_pos)
        if (
            core_id is not None
            and ct.get_hp(core_id) < ct.get_max_hp(core_id)
            and player.mode not in (BuilderMode.HEAL, BuilderMode.BRIDGE)
        ):
            player.mode = BuilderMode.HEAL

    if (
        player.mode == BuilderMode.ADVANCE
        and player.core_pos is not None
        and player.nearest_ore is not None
    ):
        ti, _ = ct.get_global_resources()
        coverage = 0.95
        if len(player.known_env) >= coverage * w * h and ti > 1000:
            player.mode = BuilderMode.PROTECT
            player.wander_target = None

    _check_broken_bridges(player, ct)

    match player.mode:
        case BuilderMode.ADVANCE:
            _run_advance(player, ct, pos, prev, w, h)
        case BuilderMode.RETURN:
            _run_return(player, ct, pos)
        case BuilderMode.SECURE:
            _run_secure(player, ct, pos, prev, w, h)
        case BuilderMode.BRIDGE:
            _run_bridge(player, ct, pos)
        case BuilderMode.HEAL:
            _run_heal(player, ct, pos)
        case BuilderMode.PROTECT:
            _run_protect(player, ct, pos)


def _check_broken_bridges(player: Player, ct: Controller) -> None:
    if player.mode in (BuilderMode.BRIDGE, BuilderMode.HEAL):
        return

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
            player.mode = BuilderMode.BRIDGE
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
                    player.mode = BuilderMode.BRIDGE
                    player.bridge_target = bt
                    player.launcher_target = None
                    player.launcher_failed = None
                    break


def _run_advance(
    player: Player,
    ct: Controller,
    pos: Position,
    prev: Position,
    w: int,
    h: int,
) -> None:
    if player.target is not None:
        player.wander_target = None
        pf_move(player, ct, player.target)
        return

    prev_wander = player.wander_target
    if player.wander_target is not None and player.wander_target in player.known_env:
        player.wander_target = None
    if player.wander_target is None:
        player.wander_target = _pick_frontier_target(player, pos, prev_wander, w, h)
    if player.wander_target is not None:
        pf_move(player, ct, player.wander_target)
    else:
        _random_walk(ct, pos, prev)


def _run_return(player: Player, ct: Controller, pos: Position) -> None:
    if player.wander_target is None or player.wander_target not in player.known_ore:
        player.wander_target = player.nearest_ore
    if player.wander_target is not None:
        if ct.is_in_vision(player.wander_target):
            for bid in ct.get_nearby_buildings():
                if ct.get_entity_type(
                    bid,
                ) == EntityType.HARVESTER and ct.get_team() == ct.get_team(bid):
                    return
            player.mode = BuilderMode.SECURE
        pf_move(player, ct, player.wander_target)


def _run_secure(
    player: Player,
    ct: Controller,
    pos: Position,
    prev: Position,
    w: int,
    h: int,
) -> None:
    if (
        player.secure_target is None
        or player.secure_target not in player.known_ore
        or (
            ct.is_in_vision(player.secure_target)
            and ct.get_entity_type(ct.get_tile_building_id(player.secure_target))
            == EntityType.HARVESTER
        )
    ):
        if player.nearest_ore is not None:
            player.secure_target = player.nearest_ore
        else:
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


def _run_bridge(player: Player, ct: Controller, pos: Position) -> None:
    print(
        f"bridge target {player.bridge_target} launcher target {player.launcher_target}",
    )

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

    if ct.is_in_vision(player.bridge_target):
        target_bid = ct.get_tile_building_id(player.bridge_target)
        if (
            target_bid is not None
            and ct.get_entity_type(target_bid) == EntityType.BRIDGE
            and ct.get_team(target_bid) == ct.get_team()
        ):
            player.mode = BuilderMode.ADVANCE
            player.bridge_target = None
            return

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
            return
        _finish_bridge_chain(player, ct, pos)


def _run_heal(player: Player, ct: Controller, pos: Position) -> None:
    if player.core_pos is None:
        return
    if ct.is_in_vision(player.core_pos):
        core_id = ct.get_tile_building_id(player.core_pos)
        if core_id is not None and ct.get_hp(core_id) < ct.get_max_hp(core_id):
            if ct.can_heal(player.core_pos):
                ct.heal(player.core_pos)
        else:
            player.mode = BuilderMode.SECURE
            player.target = None
            player.wander_target = None
    pf_move(player, ct, player.core_pos)


def _run_protect(player: Player, ct: Controller, pos: Position) -> None:
    player.visited_bridges.add(pos)
    my_team = ct.get_team()
    core = player.core_pos

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
        min_core_dist = chebyshev(pos, core) if on_target and core is not None else 0
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


def _pick_frontier_target(
    player: Player,
    pos: Position,
    prev_target: Position | None,
    w: int,
    h: int,
) -> Position | None:
    cx, cy = w / 2.0, h / 2.0
    centre = Position(cx, cy)

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
            align = (dx * pdx + dy * pdy) / pmag
            score = centre_dist / 2 + radius - align * (w + h) / 4
            if score < best_score:
                best_score = score
                best = p
            break

    return best


def _pick_frontier_near_core(
    player: Player,
    pos: Position,
    core: Position,
    w: int,
    h: int,
) -> Position | None:
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
            break

    return best


def _random_walk(ct: Controller, pos: Position, prev: Position) -> None:
    dirs = list(_ALL_DIRS)
    random.shuffle(dirs)
    if random.randint(0, 1) == 0:
        for d in dirs:
            if pos.add(d) == prev:
                continue
            if ct.can_move(d):
                ct.move(d)
                return
    for d in dirs:
        if pos.add(d) == prev:
            continue
        if try_move_smart(ct, pos, d):
            return
    for d in dirs:
        if try_move_smart(ct, pos, d):
            return


def _is_buildable(ct: Controller, tile: Position) -> bool:
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
    if player.secure_target is None:
        return False

    if not ct.is_in_vision(player.secure_target):
        player.wander_target = player.secure_target
        return True

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
            player.mode = BuilderMode.BRIDGE

    return True


def _pick_bridge_start(ct: Controller, harvester_pos: Position) -> Position | None:
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
    return best if best is not None else fallback


def _finish_bridge_chain(player: Player, ct: Controller, pos: Position) -> None:
    if player.launcher_failed is not None:
        pf_move(player, ct, player.launcher_failed)
    else:
        player.mode = BuilderMode.ADVANCE


def _bridge(player: Player, ct: Controller, pos: Position) -> bool:
    bt = player.bridge_target
    if bt is None or player.core_pos is None:
        player.bridge_target = None
        return False

    if ct.is_in_vision(bt):
        bid = ct.get_tile_building_id(bt)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.BRIDGE
            and king_dist(bt, player.core_pos) <= 1
        ):
            player.bridge_target = None
            return True

    if pos.distance_squared(bt) <= 2:
        if ct.can_destroy(bt):
            ct.destroy(bt)

        core_target = None
        bridge_candidates: list[tuple[int, Position]] = []
        candidates: list[tuple[int, Position]] = []
        enemy_candidates: list[tuple[int, Position]] = []

        for dx in range(-3, 4):
            for dy in range(-3, 4):
                t = Position(bt.x + dx, bt.y + dy)
                t_dist = bt.distance_squared(t)
                if t_dist > 9 or t_dist == 0:
                    continue
                if not in_bounds(ct, t) or not ct.is_in_vision(t):
                    continue

                tbid = ct.get_tile_building_id(t)

                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) == EntityType.CORE
                    and ct.get_team(tbid) == ct.get_team()
                ):
                    core_target = t
                    continue

                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) == EntityType.BRIDGE
                    and ct.get_team(tbid) == ct.get_team()
                ):
                    if king_dist(t, player.core_pos) < king_dist(bt, player.core_pos):
                        bridge_candidates.append((king_dist(t, player.core_pos), t))
                    continue

                if (
                    tbid is not None
                    and ct.get_entity_type(tbid) in SHOULD_FIRE_AT
                    and ct.get_team(tbid) != ct.get_team()
                ):
                    enemy_candidates.append((king_dist(t, player.core_pos), t))
                    continue

                if _is_buildable(ct, t):
                    candidates.append((king_dist(t, player.core_pos), t))

        if core_target is not None and ct.can_build_bridge(bt, core_target):
            ct.build_bridge(bt, core_target)
            player.launcher_target = bt
            player.bridge_target = None
            return True

        bridge_candidates.sort()
        for _, target in bridge_candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.launcher_target = bt
                player.bridge_target = None
                return True

        candidates.sort()
        for _, target in candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.launcher_target = bt
                player.bridge_target = target
                return False

        enemy_candidates.sort()
        for _, target in enemy_candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                player.launcher_target = bt
                player.bridge_target = target
                return False

        print("can't build anywhere")
        return False

    pf_move(player, ct, bt)
    return False


def _place_launcher_by_bridge(
    player: Player,
    ct: Controller,
    pos: Position,
    bridge_pos: Position,
) -> bool | None:
    if not ct.is_in_vision(bridge_pos):
        pf_move(player, ct, bridge_pos)
        return False

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

    return None
