"""Builder bot unit logic for v5."""

from cambc import Controller, Direction, EntityType, Environment, Position
from pathfinding import _ALL_DIRS, _DIR_IDX, bug2_step, has_line_of_sight
from utils import (
    SYM_TYPES,
    build_walkable,
    get_symmetry_candidates,
    in_bounds,
    king_dist,
    mirror_pos,
    read_comms,
    try_move_smart,
)


def _is_buildable(ct: Controller, tile: Position) -> bool:
    """Check if a tile has empty environment, or only a marker (which can be overwritten)."""
    env = ct.get_tile_env(tile)
    if env == Environment.EMPTY:
        return True
    bid = ct.get_tile_building_id(tile)
    return bool(bid is not None and ct.get_entity_type(bid) == EntityType.MARKER)


# ── Comms ─────────────────────────────────────────────────────────────


def _check_comms(player, ct: Controller) -> None:
    if player.core_pos is None:
        return
    sym, _phase, epos, _ = read_comms(ct, player.core_pos)
    if sym is not None and player.enemy_core is None:
        player.sym_resolved = sym
        player.enemy_core = epos


# ── Symmetry detection ───────────────────────────────────────────────


def _detect_symmetry(player, ct: Controller, pos: Position) -> None:
    if player.sym_resolved:
        return
    if player.sym_candidates is None:
        return

    w, h = ct.get_map_width(), ct.get_map_height()
    my_team = ct.get_team()

    # Direct vision of candidate core tiles
    for s in SYM_TYPES:
        if s in player.sym_eliminated:
            continue
        epos = player.sym_candidates[s]
        if not ct.is_in_vision(epos):
            continue
        bid = ct.get_tile_building_id(epos)
        if bid is not None:
            if (
                ct.get_entity_type(bid) == EntityType.CORE
                and ct.get_team(bid) != my_team
            ):
                player.sym_resolved = s
                player.enemy_core = epos
                print(
                    f"Scout {ct.get_id()}: FOUND enemy core at ({epos.x},{epos.y}) [{s}]",
                )
                return
            player.sym_eliminated.add(s)
        else:
            # No building at candidate centre — core is 3x3 so also
            # check tiles within 1 of the candidate for the core
            found_core = False
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    cp = Position(epos.x + dx, epos.y + dy)
                    if not ct.is_in_vision(cp):
                        continue
                    cbid = ct.get_tile_building_id(cp)
                    if cbid is not None and (
                        ct.get_entity_type(cbid) == EntityType.CORE
                        and ct.get_team(cbid) != my_team
                    ):
                        actual_pos = ct.get_position(cbid)
                        player.sym_resolved = s
                        player.enemy_core = actual_pos
                        print(
                            f"Scout {ct.get_id()}: FOUND enemy core at "
                            f"({actual_pos.x},{actual_pos.y}) [{s}]",
                        )
                        found_core = True
                        break
                if found_core:
                    break
            if found_core:
                return
            # Candidate area visible, no core found — eliminate
            player.sym_eliminated.add(s)

    # Environment mismatch elimination
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

    player.try_resolve(w, h, f"Scout {ct.get_id()}")


# ── Pathfinding helpers ──────────────────────────────────────────────


def _pf_draw_debug(player, ct: Controller, walkable: set) -> None:
    """Draw debug indicators for Bug2 pathfinding state."""
    a = player.pf_agent

    ct.draw_indicator_line(a.current, a.goal, 255, 255, 0)
    return

    # Walkable set — dark grey
    for p in walkable:
        ct.draw_indicator_dot(p, 60, 60, 60)

    # Goal — red
    ct.draw_indicator_dot(a.goal, 255, 0, 0)

    # Obstacle start position — yellow
    if a.obstacle_start_pos is not None:
        ct.draw_indicator_dot(a.obstacle_start_pos, 255, 255, 0)

    # Last open (lookahead) — blue
    if a.dbg_last_open is not None:
        ct.draw_indicator_dot(a.dbg_last_open, 80, 120, 255)

    # First wall — dark red
    if a.dbg_first_wall is not None:
        ct.draw_indicator_dot(a.dbg_first_wall, 200, 40, 40)

    # Trace heads
    if a.trace_heads is not None:
        lp = a.trace_heads[0][0]
        ll = a.trace_heads[0][2]
        ct.draw_indicator_dot(lp, 0, 255, 255)
        if ll != a.current:
            ct.draw_indicator_dot(ll, 0, 180, 180)
        rp = a.trace_heads[1][0]
        rl = a.trace_heads[1][2]
        ct.draw_indicator_dot(rp, 255, 165, 0)
        if rl != a.current:
            ct.draw_indicator_dot(rl, 200, 120, 0)

    # Current position — green (drawn last so it's on top)
    ct.draw_indicator_dot(a.current, 0, 200, 0)


def _pf_step(player, ct: Controller, pos: Position) -> bool:
    """Execute one Bug2 step via AgentState/bug2_step. Returns True if moved."""
    # Build walkable set from visible tiles
    walkable = build_walkable(ct)
    walkable.add(pos)

    # Build occupied set (other allied builders)
    occupied = set()
    my_id = ct.get_id()
    for uid in ct.get_nearby_units():
        if uid != my_id and ct.get_entity_type(uid) == EntityType.BUILDER_BOT:
            occupied.add(ct.get_position(uid))

    # If stuck for 5- turns, treat occupied cells as unwalkable
    if player.pf_stuck <= 5:
        walkable -= occupied
        occupied.clear()

    if player.pf_stuck >= 0:
        print(f"stuck {player.pf_stuck}")

    # Run bug2_step — returns desired next Position
    next_pos = bug2_step(player.pf_agent, pos, walkable, occupied)

    # Debug indicators
    # _pf_draw_debug(player, ct, walkable)

    if next_pos == pos:
        player.pf_stuck += 1
        player.pf_agent.current = pos
        return False

    # Execute the move in the game
    direction = pos.direction_to(next_pos)
    if direction == Direction.CENTRE:
        # bug2_step returned a non-adjacent cell — shouldn't happen
        player.pf_agent.current = pos
        return False

    if try_move_smart(ct, pos, direction):
        player.pf_agent.current = next_pos
        player.last_dir = direction
        if (
            next_pos in (player.pf_prev_pos, player.pf_prev_pos2, player.pf_prev_pos3)
        ):
            player.pf_stuck += 1
        else:
            player.pf_stuck = max(0, player.pf_stuck - 1)
        player.pf_prev_pos3 = player.pf_prev_pos2
        player.pf_prev_pos2 = player.pf_prev_pos
        player.pf_prev_pos = pos
        return True

    # Move failed — revert agent position so it retries next turn
    player.pf_agent.current = pos
    player.pf_stuck += 1
    return False


# ── Ore scanning (runs every turn for all builders) ──────────────────


def _scan_ore(player, ct: Controller) -> None:
    """Record any ore tiles visible this turn."""
    for tile in ct.get_nearby_tiles():
        env = ct.get_tile_env(tile)
        if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            player.known_ore.add(tile)


# ── Economy ──────────────────────────────────────────────────────────


# ── Bridge chain ────────────────────────────────────────────────────


def _start_bridge_chain(
    player,
    ct: Controller,
    pos: Position,
    source_pos: Position,
) -> None:
    """Enter bridge state: pick first bridge tile adjacent to source, closest to core."""

    print(f"Looking for bridges. core: {player.core_pos}")
    if player.core_pos is None:
        return

    best = None
    best_dist = 999999
    for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
        bp = source_pos.add(d)
        if not in_bounds(ct, bp) or not ct.is_in_vision(bp):
            continue
        if ct.get_tile_env(bp) == Environment.WALL:
            continue
        bid = ct.get_tile_building_id(bp)

        if not _is_buildable(ct, bp):
            continue
        if bid is not None:
            etype = ct.get_entity_type(bid)
            friendly = ct.get_team() == ct.get_team(bid)
            if (
                not (friendly and etype == EntityType.ROAD)
                and etype != EntityType.MARKER
            ):
                continue
        dist = king_dist(bp, player.core_pos)
        if dist < best_dist:
            best_dist = dist
            best = bp
    if best is not None:
        player.state = "bridge"
        player.bridge_target = best
        player.pf_agent.retarget(pos, best)
        _pf_step(player, ct, pos)
        print(f"Bridge E{ct.get_id()}: chain start, first bridge at {best}")


def _bridge(player, ct: Controller, pos: Position) -> None:
    """Build a chain of bridges from harvester to core."""
    if player.bridge_target is None or player.core_pos is None:
        player.state = "economy"
        player.target = None
        return

    can_patch = player.can_patch and ct.get_current_round() > 750

    # If no friendly bridge is visible, switch to advance (or suicide if enemy bridge visible)
    my_team = ct.get_team()
    has_friendly_bridge = False
    has_enemy_bridge = False
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) == EntityType.BRIDGE:
            if ct.get_team(bid) == my_team:
                has_friendly_bridge = True
                break
            has_enemy_bridge = True
    if has_enemy_bridge and not has_friendly_bridge:
        print(
            f"Bridge E{ct.get_id()}: no friendly bridge but enemy bridge visible, entering suicide",
        )
        player.state = "suicide"
        player.state_seen_enemy = False
        player.target = None
        player.bridge_target = None
        return

    # If bridge_target already has a bridge, chain is connected — return to economy
    bt = player.bridge_target
    if ct.is_in_vision(bt):
        bid = ct.get_tile_building_id(bt)
        if bid is not None and ct.get_entity_type(bid) == EntityType.BRIDGE:
            player.state = "economy"
            player.target = None
            player.bridge_target = None
            return

    # If adjacent to bridge_target, try to build
    if pos.distance_squared(player.bridge_target) <= 2:
        if ct.get_action_cooldown() > 0:
            return

        # Destroy road on bridge tile if present
        bt = player.bridge_target
        bid = ct.get_tile_building_id(bt)
        if bid is not None and ct.get_entity_type(bid) != EntityType.SPLITTER:
            if ct.can_destroy(bt):
                ct.destroy(bt)
            else:
                player.state = "economy"
                player.target = None
                return

        # Scan bridge-range tiles: look for splitter, existing bridge, or normal candidates
        bt_core_dist = king_dist(bt, player.core_pos)
        splitter_target = None
        splitter_dist = 999999
        core_target = None
        bridge_shortcut = None
        bridge_shortcut_dist = bt_core_dist
        candidates = []
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                t = Position(bt.x + dx, bt.y + dy)
                t_dist = bt.distance_squared(t)
                if t_dist > 9 or t_dist == 0:
                    continue
                if not in_bounds(ct, t) or not ct.is_in_vision(t):
                    continue
                tbid = ct.get_tile_building_id(t)

                if tbid is not None:
                    if not _is_buildable(ct, t):
                        continue

                    # Core tile?
                    if (
                        ct.get_entity_type(tbid) == EntityType.CORE
                        and ct.get_team(tbid) == ct.get_team()
                    ):
                        if core_target is None:
                            core_target = t
                        continue

                    td = king_dist(t, player.core_pos)
                    etype = ct.get_entity_type(tbid)
                    friendly = ct.get_team() == ct.get_team(tbid)

                    # Marker — treat as empty candidate
                    if etype == EntityType.MARKER:
                        candidates.append((king_dist(t, player.core_pos), t))
                        continue

                    # Nearest friendly splitter = terminal target
                    if etype == EntityType.SPLITTER and friendly and td < splitter_dist:
                        splitter_target = t
                        splitter_dist = td

                    # Existing friendly bridge closer to core?
                    elif (
                        can_patch
                        and etype == EntityType.BRIDGE
                        and friendly
                        and td < bridge_shortcut_dist
                    ):
                        bridge_shortcut = t
                        bridge_shortcut_dist = td

                    if friendly and etype == EntityType.ROAD:
                        candidates.append((king_dist(t, player.core_pos), t))

                    continue
                # Normal candidate (empty or enemy marker)
                if _is_buildable(ct, t):
                    candidates.append((king_dist(t, player.core_pos), t))

        # Priority 1: bridge to nearest splitter
        if splitter_target is not None and ct.can_build_bridge(bt, splitter_target):
            ct.build_bridge(bt, splitter_target)
            print(
                f"Bridge E{ct.get_id()}: built at {bt} -> {splitter_target} (splitter)",
            )
            player.state = "idle"
            player.bridge_target = None
            _pf_step(player, ct, pos)
            return

        # Priority 2: direct to core (if no splitters)
        if (
            splitter_target is None
            and core_target is not None
            and ct.can_build_bridge(bt, core_target)
        ):
            ct.build_bridge(bt, core_target)
            print(
                f"Bridge E{ct.get_id()}: built at {bt} -> {core_target} (direct to core)",
            )
            player.state = "idle"
            player.bridge_target = None
            _pf_step(player, ct, pos)
            return

        # Priority 3: shortcut to existing bridge
        if (
            can_patch
            and bridge_shortcut is not None
            and ct.can_build_bridge(bt, bridge_shortcut)
        ):
            ct.build_bridge(bt, bridge_shortcut)
            print(
                f"Bridge E{ct.get_id()}: built at {bt} -> {bridge_shortcut} (shortcut)",
            )
            player.state = "economy"
            player.target = None
            player.bridge_target = None
            return

        # Priority 3: closest to core
        candidates.sort()

        built = False
        for _, target in candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                print(f"Bridge E{ct.get_id()}: built at {bt} -> {target}")
                player.bridge_target = target
                player.pf_agent.retarget(pos, target)
                built = True
                break

        if not built:
            # If tile is empty, wait (probably just need resources/cooldown)
            bid2 = ct.get_tile_building_id(bt)
            if bid2 is None:
                return
            # Tile blocked by something we can't remove — abort
            print(f"Bridge E{ct.get_id()}: can't build at {bt}, aborting")
            player.state = "economy"
            player.target = None
            player.bridge_target = None
            return

    # Pathfind to bridge_target
    if player.pf_agent.goal != player.bridge_target:
        player.pf_agent.retarget(pos, player.bridge_target)
    _pf_step(player, ct, pos)


# ── Wander ──────────────────────────────────────────────────────────


def _wander(player, ct: Controller, pos: Position) -> None:
    """Wander without a target: prefer away from friendly builders, maintain
    momentum from last step, and stay away from map borders."""
    w, h = ct.get_map_width(), ct.get_map_height()
    my_id = ct.get_id()
    my_team = ct.get_team()

    near_friend_dist = 999999
    near_friend = pos
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != my_team:
            continue

        friend_pos = ct.get_position(uid)
        friend_dist = king_dist(friend_pos, pos)
        if friend_dist < near_friend_dist:
            near_friend_dist = friend_dist
            near_friend = friend_pos

    best_dir = None
    best_score = -999999

    for d in _ALL_DIRS:
        tile = pos.add(d)

        if not in_bounds(ct, tile) or (
            not ct.can_move(d) and ct.get_tile_env(tile) != Environment.EMPTY
        ):
            continue

        # Away from friendly builders
        score = king_dist(tile, near_friend) * 8

        # Momentum: prefer similar direction to last step
        if player.last_dir is not None:
            diff = abs(_DIR_IDX[d] - _DIR_IDX[player.last_dir])
            diff = min(diff, 8 - diff)
            score -= diff * 8

        # Away from border
        score += 25 - (5 - min(tile.x, tile.y, w - 1 - tile.x, h - 1 - tile.y, 5)) ** 2

        if score > best_score:
            best_score = score
            best_dir = d

    if best_dir is not None:
        best_idx = _DIR_IDX[best_dir]
        for offset in [0, -1, 1, -2, 2, -3, 3, 4]:
            d = _ALL_DIRS[(best_idx + offset) % 8]
            if try_move_smart(ct, pos, d):
                player.last_dir = d
                break


def _has_adjacent_gunner(ct: Controller, tile: Position) -> bool:
    """Check if any enemy gunner is cardinally adjacent to tile."""
    for d in (
        Direction.NORTHEAST,
        Direction.SOUTHEAST,
        Direction.SOUTHWEST,
        Direction.NORTHWEST,
    ):
        adj = tile.add(d)
        if not in_bounds(ct, adj) or not ct.is_in_vision(adj):
            continue
        bid = ct.get_tile_building_id(adj)
        if bid is not None and ct.get_entity_type(bid) == EntityType.GUNNER:
            return True
    return False


def _is_conveyorable(ct: Controller, tile: Position) -> bool:
    """Check if a tile is empty, has a friendly building, or has a marker."""
    if (
        not in_bounds(ct, tile)
        or not ct.is_in_vision(tile)
        or ct.get_tile_env(tile) != Environment.EMPTY
    ):
        return False
    bid = ct.get_tile_building_id(tile)
    return (
        bid is None
        or ct.get_team(bid) == ct.get_team()
        or ct.get_entity_type(bid) == EntityType.MARKER
    )


_CARDINAL_WITH_DIAGS = {
    Direction.NORTH: (Direction.NORTHEAST, Direction.NORTHWEST),
    Direction.SOUTH: (Direction.SOUTHEAST, Direction.SOUTHWEST),
    Direction.EAST: (Direction.NORTHEAST, Direction.SOUTHEAST),
    Direction.WEST: (Direction.NORTHWEST, Direction.SOUTHWEST),
}


def _has_adjacent_conveyorable(ct: Controller, tile: Position) -> bool:
    """Check if any cardinal neighbor and its two adjacent diagonals are all conveyorable."""
    for d, (d1, d2) in _CARDINAL_WITH_DIAGS.items():
        if _is_conveyorable(ct, tile.add(d)) and (
            _is_conveyorable(ct, tile.add(d1)) or _is_conveyorable(ct, tile.add(d2))
        ):
            return True
    return False


def update_claimed_ore(player, ct: Controller) -> None:
    # Check current ore target — abort if already harvested
    if player.target is not None and ct.is_in_vision(player.target):
        bid = ct.get_tile_building_id(player.target)
        bbid = ct.get_tile_builder_bot_id(player.target)

        if bbid is not None and bbid != ct.get_id():
            player.claimed_ore.add(player.target)
            player.target = None
        elif bid is not None:
            etype = ct.get_entity_type(bid)
            near_core = (
                player.core_pos is None
                or king_dist(player.core_pos, player.target) <= 3
            )
            if (
                (etype == EntityType.HARVESTER and not player.can_patch)
                or ct.get_team(bid) != ct.get_team()
                or (etype == EntityType.BARRIER and not near_core)
            ):
                player.claimed_ore.add(player.target)
                player.target = None
            elif (
                etype == EntityType.ROAD
                or (etype == EntityType.BARRIER and near_core)
            ) and ct.can_destroy(player.target):
                ct.destroy(player.target)
        elif _has_adjacent_gunner(ct, player.target):
            player.claimed_ore.add(player.target)
            player.target = None


def update_advance_ore(player, ct: Controller) -> None:
    # Check current ore target — abort if already harvested
    if player.target is not None and ct.is_in_vision(player.target):
        bid = ct.get_tile_building_id(player.target)
        bbid = ct.get_tile_builder_bot_id(player.target)

        if (
            bbid is not None
            or _has_adjacent_gunner(ct, player.target)
            or not _has_adjacent_conveyorable(ct, player.target)
        ):
            player.advance_ore.add(player.target)
            player.target = None

        elif bid is not None:
            etype = ct.get_entity_type(bid)
            same_team = ct.get_team(bid) == ct.get_team()
            if (
                (etype == EntityType.HARVESTER) == same_team
                or etype != EntityType.HARVESTER
            ) and (
                (etype == EntityType.FOUNDRY) == same_team
                or etype != EntityType.FOUNDRY
            ):
                player.advance_ore.add(player.target)
                player.target = None


def _economy(player, ct: Controller, pos: Position) -> None:
    """Economy mode: harvest nearest ore, opportunistically switch to LOS ore,
    or wander to discover more."""

    update_claimed_ore(player, ct)

    # Early game: rush away from friendly core
    if (
        player.core_pos is not None
        and king_dist(pos, player.core_pos) <= 4
        and ct.get_current_round() < 10
    ):
        print("rush away")
        away_dir = player.core_pos.direction_to(pos)
        if away_dir == Direction.CENTRE:
            away_dir = Direction.NORTH
        away_idx = _DIR_IDX[away_dir]
        for offset in [0, -1, 1, -2, 2]:
            d = _ALL_DIRS[(away_idx + offset) % 8]
            if try_move_smart(ct, pos, d):
                player.last_dir = d
                break
        return

    # Check current ore target — abort if already harvested
    if player.target is not None:
        if ct.is_in_vision(player.target):
            bid = ct.get_tile_building_id(player.target)
            bbid = ct.get_tile_builder_bot_id(player.target)

            if bbid is not None and bbid != ct.get_id():
                player.claimed_ore.add(player.target)
                player.target = None
            elif bid is not None:
                etype = ct.get_entity_type(bid)
                near_core = (
                    player.core_pos is None
                    or king_dist(player.core_pos, player.target) <= 3
                )
                if etype == EntityType.HARVESTER or ct.get_team(bid) != ct.get_team():
                    player.claimed_ore.add(player.target)
                    player.target = None
                elif (
                    etype == EntityType.ROAD
                    or (etype == EntityType.BARRIER and near_core)
                ) and ct.can_destroy(player.target):
                    ct.destroy(player.target)

        # Build harvester if adjacent to ore target
        if player.target is not None and pos.distance_squared(player.target) <= 2:
            (ti, _) = ct.get_global_resources()
            (h_ti, _) = ct.get_harvester_cost()
            # Check every empty cardinal neighbour of the ore has a building
            cardinal_covered = True
            for cd in (
                Direction.NORTH,
                Direction.EAST,
                Direction.SOUTH,
                Direction.WEST,
            ):
                adj = player.target.add(cd)
                if in_bounds(ct, adj):
                    env = ct.get_tile_env(adj)
                    bid = ct.get_tile_building_id(adj)
                    if env == Environment.EMPTY and (
                        bid is None or ct.get_entity_type(bid) == EntityType.MARKER
                    ):
                        cardinal_covered = False
                        break
            if 100 + h_ti <= ti and cardinal_covered:
                # Move off ore if standing on it
                if pos == player.target and ct.get_move_cooldown() == 0:
                    for d in _ALL_DIRS:
                        if try_move_smart(ct, pos, d):
                            return

                if ct.can_build_harvester(player.target):
                    ct.build_harvester(player.target)
                    print(f"Econ E{ct.get_id()}: built harvester at {player.target}")
                    player.claimed_ore.add(player.target)
                    ore_pos = player.target
                    # Enter bridge mode: connect harvester to core
                    _start_bridge_chain(player, ct, pos, ore_pos)
                return
            # wait until we can build or ore is claimed
            try_move_smart(ct, pos, pos.direction_to(player.target))
            if pos == player.target:
                # While waiting, build roads on adjacent tiles
                for d in (
                    Direction.NORTH,
                    Direction.EAST,
                    Direction.SOUTH,
                    Direction.WEST,
                ):
                    tile = pos.add(d)
                    if ct.can_build_road(tile):
                        ct.build_road(tile)
                        break
            return

    # Look for opportunistic ore switches
    has_ore_target = player.target is not None and player.target in player.known_ore
    best_ore = None
    best_ore_dist = 999999

    if has_ore_target:
        # Only switch to visible ore we have line-of-sight to
        walkable = build_walkable(ct)
        walkable.add(pos)
        if not has_line_of_sight(pos, player.target, walkable):
            for ore in player.known_ore:
                if ore in player.claimed_ore or ore == player.target:
                    continue
                if not ct.is_in_vision(ore):
                    continue
                bid = ct.get_tile_building_id(ore)
                if bid is not None and (
                    ct.get_entity_type(bid) == EntityType.HARVESTER
                    or ct.get_team(bid) != ct.get_team()
                ):
                    player.claimed_ore.add(ore)
                    continue
                d = king_dist(pos, ore)
                if d < best_ore_dist and has_line_of_sight(pos, ore, walkable):
                    best_ore_dist = d
                    best_ore = ore
    else:
        # No ore target — any visible ore is good enough
        for ore in player.known_ore:
            if ore in player.claimed_ore:
                continue
            if not ct.is_in_vision(ore):
                continue
            bid = ct.get_tile_building_id(ore)
            if bid is not None and (
                ct.get_entity_type(bid) == EntityType.HARVESTER
                or ct.get_team(bid) != ct.get_team()
            ):
                player.claimed_ore.add(ore)
                continue
            d = king_dist(pos, ore)
            if d < best_ore_dist:
                best_ore_dist = d
                best_ore = ore

    if best_ore is not None:
        player.target = best_ore
        player.pf_agent.retarget(pos, best_ore)

    # If still no target, pick nearest known unclaimed ore
    if player.target is None:
        best = None
        best_dist = 999999
        for ore in player.known_ore:
            if ore in player.claimed_ore:
                continue
            d = king_dist(pos, ore)
            if d < best_dist:
                best_dist = d
                best = ore
        if best is not None:
            player.target = best
            player.pf_agent.retarget(pos, best)

    if ct.get_move_cooldown() > 0:
        return

    # Check for incomplete bridge chains — bridge whose target has no building
    my_team = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.BRIDGE or ct.get_team(bid) != my_team:
            continue
        bt = ct.get_bridge_target(bid)
        if not ct.is_in_vision(bt):
            continue
        tbid = ct.get_tile_building_id(bt)
        if tbid is None or (
            ct.get_entity_type(tbid) == EntityType.ROAD and ct.get_team(tbid) == my_team
        ):
            player.state = "bridge"
            player.bridge_target = bt
            player.pf_agent.retarget(pos, bt)
            print(f"Bridge E{ct.get_id()}: resuming chain at {bt}")
            return

    # Check for friendly harvesters without adjacent bridges
    for bid in ct.get_nearby_buildings():
        if (
            ct.get_entity_type(bid) != EntityType.HARVESTER
            or ct.get_team(bid) != my_team
        ):
            continue
        hp = ct.get_position(bid)
        has_bridge = False
        for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
            adj = hp.add(d)
            if not ct.is_in_bounds(adj) or not ct.is_in_vision(adj):
                continue
            abid = ct.get_tile_building_id(adj)
            if (
                abid is not None
                and ct.get_entity_type(abid) == EntityType.BRIDGE
                and ct.get_team(abid) == my_team
            ):
                has_bridge = True
                break
        if not has_bridge:
            _start_bridge_chain(player, ct, pos, hp)
            if player.state == "bridge":
                print(
                    f"Bridge E{ct.get_id()}: starting chain for unconnected harvester at {hp}",
                )
                return

    if player.target is not None:
        player.economy_wandering = 0
        if player.pf_agent.goal != player.target:
            player.pf_agent.retarget(pos, player.target)
        _pf_step(player, ct, pos)
    else:
        player.economy_wandering += 1
        if player.economy_wandering > 200:
            # If no friendly bridge is visible, switch to advance (or suicide if enemy bridge visible)
            my_team = ct.get_team()
            has_friendly_bridge = False
            has_enemy_bridge = False
            for bid in ct.get_nearby_buildings():
                if ct.get_entity_type(bid) == EntityType.BRIDGE:
                    if ct.get_team(bid) == my_team:
                        has_friendly_bridge = True
                        break
                    has_enemy_bridge = True
            if has_enemy_bridge and not has_friendly_bridge:
                print(
                    f"Bridge E{ct.get_id()}: no friendly bridge but enemy bridge visible, entering suicide",
                )
                player.state = "suicide"
                player.state_seen_enemy = False
                player.target = None
                player.bridge_target = None
                return

        _wander(player, ct, pos)


# ── Base builder state ───────────────────────────────────────────────


def _has_adjacent_friendly_builder(ct: Controller, tile: Position) -> bool:
    """Check if a tile is adjacent to any friendly builder bot."""
    my_id = ct.get_id()
    my_team = ct.get_team()
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        if (
            ct.get_entity_type(uid) == EntityType.BUILDER_BOT
            and ct.get_team(uid) == my_team
        ) and tile.distance_squared(ct.get_position(uid)) <= 2:
            return True
    return False


def _base_builder(player, ct: Controller, pos: Position) -> None:
    """Move one step cardinally away from core, then place barriers in all 8
    directions before hibernating."""
    if player.core_pos is None:
        return

    if ct.is_in_vision(player.core_pos):
        core_id = ct.get_tile_building_id(player.core_pos)
        if (ct.get_hp() < ct.get_max_hp() or (
            core_id is not None and ct.get_hp(core_id) < ct.get_max_hp(core_id)
        )) and ct.can_heal(player.core_pos):
            print("healing")
            ct.heal(player.core_pos)
            player.base_phase = 6
            return

    print(f"phase {player.base_phase}")

    # Phase 0: move one step away from core
    if player.base_phase == 0:
        dx = pos.x - player.core_pos.x
        dy = pos.y - player.core_pos.y

        if abs(dx) >= abs(dy):
            away_dir = Direction.EAST if dx > 0 else Direction.WEST
        else:
            away_dir = Direction.SOUTH if dy > 0 else Direction.NORTH

        split_pos = pos.add(away_dir)

        player.base_phase = 1
        if in_bounds(ct, split_pos):
            bid = ct.get_tile_building_id(split_pos)
            if bid is not None:
                is_splitter = ct.get_entity_type(bid) == EntityType.SPLITTER
                if is_splitter:
                    player.base_phase = 16
                elif ct.can_destroy(split_pos):
                    ct.destroy(split_pos)

            if player.base_phase == 1:
                if ct.can_build_splitter(split_pos, away_dir.opposite()):
                    ct.build_splitter(split_pos, away_dir.opposite())

                try_move_smart(ct, pos, away_dir)

        if player.base_phase == 1:
            return

    # Phase 1: place barriers in all 8 directions (wait 8 turns total)
    if player.base_phase == 1:
        built = False
        for d in _ALL_DIRS:
            tile = pos.add(d)
            if in_bounds(ct, tile):
                bid = ct.get_tile_building_id(tile)
                if bid is not None:
                    hurt = ct.get_entity_type(bid) == EntityType.BARRIER and ct.get_hp(
                        bid,
                    ) < ct.get_max_hp(bid)
                    if (
                        ct.get_entity_type(bid) == EntityType.ROAD or hurt
                    ) and ct.can_destroy(tile):
                        ct.destroy(tile)
            if ct.can_build_barrier(tile):
                ct.build_barrier(tile)
                built = True
                break

        init_mode = ct.get_current_round() < 20
        player.base_wait += 1
        if built or (init_mode and player.base_wait < 8):
            return

        if not init_mode:
            player.base_phase = 6
        else:
            player.base_phase = 2

    # Phase 2: move diagonally (clockwise from core-to-builder direction)
    if player.base_phase == 2:
        away_dir = pos.direction_to(player.core_pos)
        if away_dir == Direction.CENTRE:
            away_dir = Direction.NORTH
        away_idx = _DIR_IDX[away_dir]
        # One step clockwise from the cardinal = the diagonal
        if pos.distance_squared(player.core_pos) <= 2:
            diag = _ALL_DIRS[(away_idx + 2) % 8]
        else:
            diag = _ALL_DIRS[(away_idx + 1) % 8]
        target = pos.add(diag)
        try_move_smart(ct, pos, diag)
        player.base_phase = 3
        return

    # Phase 3: move two steps away from core
    if player.base_phase >= 3 and player.base_phase < 5:
        away_dir = player.core_pos.direction_to(pos)
        if away_dir == Direction.CENTRE:
            away_dir = Direction.NORTH
        away_idx = _DIR_IDX[away_dir]
        for offset in [0, -1, 1, -2, 2, -3, 3, 4]:
            d = _ALL_DIRS[(away_idx + offset) % 8]
            target = pos.add(d)
            if _has_adjacent_friendly_builder(ct, target):
                continue
            if try_move_smart(ct, pos, d):
                break
        player.base_phase += 1
        return

    # Phase 5: build a launcher (if none seen) or barrier on a tile adjacent to the core
    if player.base_phase == 5:
        for d in _ALL_DIRS:
            tile = pos.add(d)
            if king_dist(tile, player.core_pos) > 2 or not in_bounds(ct, tile):
                continue
            bid = ct.get_tile_building_id(tile)
            if (
                bid is not None
                and ct.get_entity_type(bid) == EntityType.ROAD
                and ct.can_destroy(tile)
            ):
                ct.destroy(tile)

            if not player.seen_launcher and ct.can_build_launcher(tile):
                ct.build_launcher(tile)
            elif ct.can_build_barrier(tile):
                ct.build_barrier(tile)

            player.base_phase = 6

    # Phase 6+: if outside core, hibernate. Otherwise walk toward launcher/splitter.
    if player.base_phase >= 6 and player.base_phase < 15:
        if king_dist(pos, player.core_pos) > 2:
            if player.base_round == 1:
                player.state = "advance"
            else:
                player.state = "economy"
            player.target = None
            return

        # Find a target: prefer launcher, fall back to nearest visible splitter
        walk_target = None
        if player.seen_launcher:
            for bid in ct.get_nearby_buildings():
                if (
                    ct.get_entity_type(bid) == EntityType.LAUNCHER
                    and ct.get_team(bid) == ct.get_team()
                ):
                    walk_target = ct.get_position(bid)
                    break
        if walk_target is None:
            enemy = player.sym_candidates["rotational"]
            best_key = (999999, 999999, 999999)
            for bid in ct.get_nearby_buildings():
                if (
                    ct.get_entity_type(bid) == EntityType.SPLITTER
                    and ct.get_team(bid) == ct.get_team()
                ):
                    sp = ct.get_position(bid)
                    ed = king_dist(sp, enemy) if enemy else 999999
                    key = (ed, sp.x, sp.y)
                    if key < best_key:
                        best_key = key
                        walk_target = sp

        player.base_phase += 1
        if walk_target is None:
            return
        preferred = pos.direction_to(walk_target)
        if preferred != Direction.CENTRE:
            pref_idx = _DIR_IDX[preferred]
            for offset in [0, 1, -1]:
                d = _ALL_DIRS[(pref_idx + offset) % 8]
                if try_move_smart(ct, pos, d):
                    break
        return

    # Phase 11+: walk toward enemy base, destroying barriers in the way
    if player.base_phase == 15:
        enemy = player.sym_candidates["rotational"]
        preferred = pos.direction_to(enemy)
        if king_dist(pos, player.core_pos) > 2 or preferred == Direction.CENTRE:
            if player.base_round == 1:
                player.state = "advance"
            else:
                player.state = "economy"
            player.target = None
            return
        pref_idx = _DIR_IDX[preferred]
        for offset in [0, 1, -1, 2, -2, 3, -3, 4]:
            d = _ALL_DIRS[(pref_idx + offset) % 8]
            target = pos.add(d)
            if not in_bounds(ct, target):
                continue
            bid = ct.get_tile_building_id(target)
            if bid is not None and ct.get_entity_type(bid) == EntityType.BARRIER:
                if king_dist(player.core_pos, target) > 2 and ct.can_destroy(target):
                    ct.destroy(target)
                else:
                    continue
            if try_move_smart(ct, pos, d):
                break

    if player.base_phase == 16:
        (ti, _) = ct.get_global_resources()
        (fti, _) = ct.get_foundry_cost()
        if ti > fti:
            # Replace a barrier adjacent to the core with a foundry
            for d in _ALL_DIRS:
                tile = pos.add(d)
                if not in_bounds(ct, tile) or not ct.is_in_vision(tile):
                    continue
                if player.core_pos is None or king_dist(tile, player.core_pos) > 2:
                    continue
                bid = ct.get_tile_building_id(tile)
                if (
                    bid is not None
                    and ct.get_entity_type(bid) == EntityType.BARRIER
                    and ct.can_destroy(tile)
                ):
                    ct.destroy(tile)
                if ct.can_build_foundry(tile):
                    ct.build_foundry(tile)
                    print(f"Base E{ct.get_id()}: built foundry at {tile}")
                    player.base_phase = 6
                    break


# ── Advance state ────────────────────────────────────────────────────


def _advance(player, ct: Controller, pos: Position) -> None:
    """Pathfind toward the enemy base, diverting to ore if any is known.
    Once the enemy base is visible, switch to hibernate."""

    update_advance_ore(player, ct)

    # Early game: rush away from friendly core
    if (
        player.core_pos is not None
        and king_dist(pos, player.core_pos) <= 4
        and ct.get_current_round() < 10
    ):
        print("rush away")
        away_dir = player.core_pos.direction_to(pos)
        if away_dir == Direction.CENTRE:
            away_dir = Direction.NORTH
        away_idx = _DIR_IDX[away_dir]
        for offset in [0, -1, 1, -2, 2]:
            d = _ALL_DIRS[(away_idx + offset) % 8]
            if try_move_smart(ct, pos, d):
                player.last_dir = d
                break
        return

    # Enemy base visible — stop targeting it, just wander from now on
    if player.enemy_core is not None and ct.is_in_vision(player.enemy_core):
        player.state_seen_enemy = True

    my_team = ct.get_team()

    print(f"target ore {player.advance_targeting_ore} {player.target}")

    # If targeting enemy harvester, try to place a gunner diagonally adjacent to it
    if (
        player.advance_targeting_ore
        and player.target is not None
        and ct.is_in_vision(player.target)
    ):
        bid = ct.get_tile_building_id(player.target)

        print(f"{bid} {ct.get_entity_type(bid)} {ct.get_team(bid)}")

        if (
            bid is not None
            and (
                ct.get_entity_type(bid) == EntityType.HARVESTER
                or ct.get_entity_type(bid) == EntityType.FOUNDRY
            )
            and ct.get_team(bid) != my_team
        ):
            hp = player.target

            print("found harvester")

            # Step 1: if cardinally adjacent to harvester, place conveyor under self facing a diagonal gunner spot
            if pos.distance_squared(hp) == 1:
                pos_bid = ct.get_tile_building_id(pos)
                pos_etype = ct.get_entity_type(pos_bid) if pos_bid is not None else None

                # Check if we're already on a conveyor facing a valid gunner spot
                if pos_etype == EntityType.CONVEYOR:
                    conv_dir = ct.get_direction(pos_bid)
                    bp = pos.add(conv_dir)
                    if bp.distance_squared(hp) == 2 and ct.is_in_vision(bp):
                        facing = bp.direction_to(hp)
                        tbid = ct.get_tile_building_id(bp)
                        if tbid is not None and ct.can_destroy(bp):
                            ct.destroy(bp)
                        if ct.can_build_gunner(bp, facing):
                            ct.build_gunner(bp, facing)
                            player.state = "heal"
                            player.suicide_countdown = 0
                            print(
                                f"Advance E{ct.get_id()}: built gunner at {bp} facing {facing}",
                            )
                            return
                        # player.advance_ore.add(hp)

                        player.suicide_countdown += 5
                        if player.suicide_countdown >= 25:
                            player.state = "suicide"
                            player.state_seen_enemy = False
                            print(
                                f"Advance E{ct.get_id()}: suicide countdown reached, entering suicide mode",
                            )

                        return

                # Replace road with conveyor facing a valid diagonal gunner spot
                if pos_etype == EntityType.ROAD and ct.get_team(pos_bid) == my_team:
                    for gd in (
                        Direction.NORTH,
                        Direction.SOUTH,
                        Direction.EAST,
                        Direction.WEST,
                    ):
                        bp = pos.add(gd)
                        if bp.distance_squared(hp) != 2:
                            continue
                        if not in_bounds(ct, bp) or not ct.is_in_vision(bp):
                            continue
                        if not _is_buildable(ct, bp):
                            continue
                        tbid = ct.get_tile_building_id(bp)
                        if tbid is not None:
                            etype = ct.get_entity_type(tbid)
                            friendly = ct.get_team(tbid) == my_team
                            if (
                                not (friendly and etype == EntityType.ROAD)
                                and etype != EntityType.MARKER
                            ):
                                continue
                        # Valid gunner spot found — destroy road and build conveyor facing it
                        if ct.can_destroy(pos):
                            ct.destroy(pos)
                        if ct.can_build_conveyor(pos, gd):
                            ct.build_conveyor(pos, gd)

                            print(
                                f"Advance E{ct.get_id()}: placed conveyor at {pos} facing {gd}",
                            )
                            player.suicide_countdown = 0
                        return

    if player.advance_targeting_ore:
        # Ore target was claimed — switch back
        if player.target is None or player.target not in player.known_ore:
            player.advance_targeting_ore = False
            player.target = None

    # Look for nearest visible unclaimed ore, preferring LOS
    # (re-evaluates even while targeting ore to switch to a closer one)
    walkable = build_walkable(ct)
    walkable.add(pos)
    best_los = None
    best_los_dist = 999999
    best_any = None
    best_any_dist = 999999
    for ore in player.known_ore:
        if ore in player.advance_ore:
            continue
        if not ct.is_in_vision(ore):
            continue
        d = king_dist(pos, ore)
        if d < best_any_dist:
            best_any_dist = d
            best_any = ore
        if d < best_los_dist and has_line_of_sight(pos, ore, walkable):
            best_los_dist = d
            best_los = ore

    # Scan for enemy foundries, preferring LOS
    best_foundry = None
    best_foundry_dist = 999999
    best_foundry_no_los = None
    best_foundry_no_los_dist = 999999
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.FOUNDRY:
            continue
        if ct.get_team(bid) == my_team:
            continue
        fp = ct.get_position(bid)
        d = king_dist(pos, fp)
        if has_line_of_sight(pos, fp, walkable):
            if d < best_foundry_dist:
                best_foundry_dist = d
                best_foundry = fp
        elif d < best_foundry_no_los_dist:
            best_foundry_no_los_dist = d
            best_foundry_no_los = fp

    # Priority: foundry LOS > ore LOS > foundry no-LOS > ore no-LOS
    best_target = best_foundry or best_los or best_foundry_no_los or best_any
    if (best_target is not None and best_target != player.target) or (
        best_target is not None and not player.advance_targeting_ore
    ):
        player.target = best_target
        player.advance_targeting_ore = True
        print(f"Advance E{ct.get_id()}: diverting to target at {best_target}")

    # If targeting ore, pathfind to it; otherwise wander
    if player.advance_targeting_ore and player.target is not None:
        if player.pf_agent.goal != player.target:
            player.pf_agent.retarget(pos, player.target)
        _pf_step(player, ct, pos)
    elif not player.state_seen_enemy:
        # Haven't seen enemy yet — pathfind toward a candidate
        if player.target is None or player.target in player.known_ore:
            if player.enemy_core is not None:
                player.target = player.enemy_core
            elif player.sym_candidates:
                remaining = [
                    s
                    for s in SYM_TYPES
                    if s not in player.sym_eliminated and s in player.sym_candidates
                ]
                if len(remaining) > 0:
                    player.target = player.sym_candidates[
                        remaining[ct.get_current_round() % len(remaining)]
                    ]
            # Update if enemy core resolved while targeting old candidate
        elif player.enemy_core is not None and player.target != player.enemy_core:
            player.target = player.enemy_core
            player.advance_targeting_ore = False
        if player.target is not None:
            if player.pf_agent.goal != player.target:
                player.pf_agent.retarget(pos, player.target)
            _pf_step(player, ct, pos)
    else:
        player.advance_targeting_ore = False
        print("wandering")
        _wander(player, ct, pos)

    if not player.advance_targeting_ore:
        player.suicide_countdown += 1
        if player.suicide_countdown >= 25:
            player.state = "suicide"
            player.state_seen_enemy = False
            print(
                f"Advance E{ct.get_id()}: suicide countdown reached, entering suicide mode",
            )
            return


# ── Suicide state ─────────────────────────────────────────────────


def _suicide(player, ct: Controller, pos: Position) -> None:
    """Pathfind to enemy base, then find an enemy bridge/conveyor to self-destruct on."""

    # Standing on enemy bridge/conveyor with resources — self-destruct
    pos_bid = ct.get_tile_building_id(pos)
    if pos_bid is not None:
        pos_etype = ct.get_entity_type(pos_bid)
        if (
            pos_etype
            in (
                EntityType.BRIDGE,
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
            )
            and ct.get_team(pos_bid) != ct.get_team()
            and ct.get_stored_resource(pos_bid) is not None
        ):
            print(f"Suicide E{ct.get_id()}: self-destructing on {pos_etype} at {pos}")
            ct.self_destruct()
            return

    enemy = player.enemy_core
    if enemy is None:
        if player.sym_candidates:
            remaining = [
                s
                for s in SYM_TYPES
                if s not in player.sym_eliminated and s in player.sym_candidates
            ]
            if remaining:
                enemy = player.sym_candidates[remaining[0]]
        if enemy is None:
            return

    # Find nearest enemy bridge/conveyor without a builder bot on it

    occupied = set()
    my_id = ct.get_id()
    for uid in ct.get_nearby_units():
        if uid != my_id and ct.get_entity_type(uid) == EntityType.BUILDER_BOT:
            occupied.add(ct.get_position(uid))

    my_team = ct.get_team()
    walkable = build_walkable(ct) - occupied
    walkable.add(pos)

    if player.target is not None:
        # Already have a target — only check if there's a closer one in line of sight
        best = player.target
        best_dist = king_dist(best, enemy)
        for bid in ct.get_nearby_buildings():
            etype = ct.get_entity_type(bid)
            if etype not in (
                EntityType.BRIDGE,
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
            ):
                continue
            if ct.get_team(bid) == my_team:
                continue
            if ct.get_stored_resource(bid) is None:
                continue
            bp = ct.get_position(bid)
            bbid = ct.get_tile_builder_bot_id(bp)
            if bbid is not None:
                continue
            d = king_dist(bp, enemy)
            if d < best_dist and has_line_of_sight(pos, bp, walkable):
                best_dist = d
                best = bp
    else:
        # No target yet — full scan, prioritise line of sight
        best_los = None
        best_los_dist = 999999
        best_no_los = None
        best_no_los_dist = 999999
        for bid in ct.get_nearby_buildings():
            etype = ct.get_entity_type(bid)
            if etype not in (
                EntityType.BRIDGE,
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
            ):
                continue
            if ct.get_team(bid) == my_team:
                continue
            if ct.get_stored_resource(bid) is None:
                continue
            bp = ct.get_position(bid)
            bbid = ct.get_tile_builder_bot_id(bp)
            if bbid is not None:
                continue
            d = king_dist(bp, enemy)
            if has_line_of_sight(pos, bp, walkable):
                if d < best_los_dist:
                    best_los_dist = d
                    best_los = bp
            elif d < best_no_los_dist:
                best_no_los_dist = d
                best_no_los = bp
        best = best_los if best_los is not None else best_no_los

    if best is not None:
        if player.pf_agent.goal != best:
            player.pf_agent.retarget(pos, best)
        _pf_step(player, ct, pos)
    else:
        # No target found, just pathfind closer to enemy
        if player.pf_agent.goal != enemy:
            player.pf_agent.retarget(pos, enemy)
        _pf_step(player, ct, pos)


# ── Idle state ────────────────────────────────────────────────────


def _idle(player, ct: Controller, pos: Position) -> None:
    # Monitor conveyor/bridge we're standing on
    print(f"Idle empty turns {player.idle_empty_turns}")
    pos_bid = ct.get_tile_building_id(pos)
    if pos_bid is not None:
        pos_etype = ct.get_entity_type(pos_bid)
        if pos_etype in (
            EntityType.CONVEYOR,
            EntityType.ARMOURED_CONVEYOR,
            EntityType.BRIDGE,
            EntityType.SPLITTER,
        ):
            if ct.get_stored_resource(pos_bid) is not None:
                player.idle_empty_turns = 0
            else:
                player.idle_empty_turns += 1
                if player.idle_empty_turns >= 5:
                    player.state = "economy"
                    player.target = None
                    player.can_patch = True
                    player.idle_empty_turns = 0
                    return
        else:
            player.state = "economy"
            player.target = None
            player.can_patch = True
            player.idle_empty_turns = 0
            return
    else:
        player.state = "economy"
        player.target = None
        player.idle_empty_turns = 0
        return

    # Check for incomplete bridge chains — switch to economy to handle them
    my_team = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) != EntityType.BRIDGE or ct.get_team(bid) != my_team:
            continue
        bt = ct.get_bridge_target(bid)
        if not ct.is_in_vision(bt):
            continue
        tbid = ct.get_tile_building_id(bt)
        if tbid is None or (
            ct.get_entity_type(tbid) == EntityType.ROAD and ct.get_team(tbid) == my_team
        ):
            player.state = "economy"
            player.target = None
            player.idle_empty_turns = 0
            print(f"Idle E{ct.get_id()}: spotted incomplete bridge, entering economy")
            return

    # Opportunistic bridge: if adjacent to an incomplete bridge target, build one bridge
    if ct.get_action_cooldown() == 0:
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) != EntityType.BRIDGE
                or ct.get_team(bid) != my_team
            ):
                continue
            bt = ct.get_bridge_target(bid)
            if pos.distance_squared(bt) > 2:
                continue
            if not ct.is_in_vision(bt):
                continue
            tbid = ct.get_tile_building_id(bt)
            if tbid is None or (
                ct.get_entity_type(tbid) == EntityType.ROAD
                and ct.get_team(tbid) == my_team
            ):
                old_target = player.bridge_target
                player.bridge_target = bt
                _bridge(player, ct, pos)
                player.bridge_target = old_target
                player.state = "idle"
                return
    _pf_step(player, ct, pos)


# ── Heal state ────────────────────────────────────────────────────


def _heal(player, ct: Controller, pos: Position) -> None:
    # Check if enemy harvester and friendly gunner still adjacent to builder

    bid = ct.get_tile_building_id(player.target)
    has_harvester = bid is not None and (
        ct.get_entity_type(bid) == EntityType.HARVESTER
        or ct.get_entity_type(bid) == EntityType.FOUNDRY
    )
    is_enemy = bid is not None and ct.get_team(bid) != ct.get_team()

    if has_harvester and is_enemy:
        if ct.can_heal(pos):
            ct.heal(pos)
        return

    # destroy gunners, barrier ore, suicide
    if ct.can_destroy(pos):
        ct.destroy(pos)
    for bid in ct.get_nearby_buildings():
        if ct.get_entity_type(bid) == EntityType.GUNNER:
            gp = ct.get_position(bid)
            if ct.can_destroy(gp):
                ct.destroy(gp)

    if not has_harvester and ct.can_destroy(player.target):
        ct.destroy(player.target)

    if ct.can_build_barrier(player.target):
        ct.build_barrier(player.target)

    player.state = "suicide"
    player.state_seen_enemy = False


# ── Main entry point ─────────────────────────────────────────────────


def run_builder(player, ct: Controller) -> None:
    pos = ct.get_position()
    w, h = ct.get_map_width(), ct.get_map_height()

    # Init core position
    if player.core_pos is None:
        my_team = ct.get_team()
        for eid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(eid) == EntityType.CORE
                and ct.get_team(eid) == my_team
            ):
                player.core_pos = ct.get_position(eid)
                break

    # Init symmetry candidates
    if player.sym_candidates is None and player.core_pos:
        player.sym_candidates = get_symmetry_candidates(player.core_pos, w, h)
        for s, epos in player.sym_candidates.items():
            if epos == player.core_pos:
                player.sym_eliminated.add(s)

    # Check for friendly launchers
    if not player.seen_launcher:
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) == EntityType.LAUNCHER
                and ct.get_team(bid) == ct.get_team()
            ):
                player.seen_launcher = True
                break

    # Scan for ore every turn
    _scan_ore(player, ct)

    # Check comms markers for enemy core info from other scouts
    _check_comms(player, ct)

    # Symmetry elimination from vision
    _detect_symmetry(player, ct, pos)

    # Init state
    if player.state is None:
        cur_round = ct.get_current_round()
        print(cur_round)
        player.base_round = cur_round - 1
        if player.core_pos is not None:
            dx = pos.x - player.core_pos.x
            dy = pos.y - player.core_pos.y
            is_cardinal = (dx == 0) != (dy == 0)
            is_centre = dx == 0 and dy == 0
        else:
            is_cardinal = False
            is_centre = False

        if cur_round <= 1:
            player.state = "advance"
        elif is_centre:
            player.state = "advance" if ct.get_current_round() % 2 == 0 else "economy"
        else:
            player.state = "base_builder" if is_cardinal else "hibernate"

    print(player.state)

    # Reset state_turns on state change
    if player.state != player.prev_state:
        player.state_turns = 0
        player.prev_state = player.state

    # If standing on a splitter (non-base_builder), stay still unless a friendly bot is near core
    if player.state != "base_builder" and player.core_pos is not None:
        if ct.get_hp() < ct.get_max_hp() and ct.can_heal(pos):
            ct.heal(pos)

        my_team = ct.get_team()
        for bid_here in ct.get_nearby_buildings():
            if ct.get_position(bid_here) == pos:
                if (
                    ct.get_entity_type(bid_here) == EntityType.SPLITTER
                    and ct.get_team(bid_here) == my_team
                ):
                    for uid in ct.get_nearby_units():
                        if uid == ct.get_id():
                            continue
                        if ct.get_team(uid) == my_team:
                            upos = ct.get_position(uid)
                            if (
                                ct.get_tile_builder_bot_id(upos) is not None
                                and king_dist(upos, player.core_pos) <= 1
                            ):
                                break
                    else:
                        if ct.can_heal(pos):
                            ct.heal(pos)
                        return
                break

    # Run state
    if player.state == "heal":
        _heal(player, ct, pos)
    if player.state == "base_builder":
        _base_builder(player, ct, pos)
    elif player.state == "hibernate":
        if player.core_pos is not None and king_dist(pos, player.core_pos) > 1:
            player.state = "advance" if ct.get_current_round() % 2 == 0 else "economy"
    elif player.state == "idle":
        player.state_turns += 1
        if player.state_turns >= 100:
            player.state = "economy"
            player.target = None
            player.can_patch = True
            player.state_turns = 0
            return
        _idle(player, ct, pos)
    elif player.state == "advance":
        player.state_turns += 1
        if player.state_turns >= 150:
            player.state = "suicide"
            player.state_seen_enemy = False
            player.state_turns = 0
            return
        _advance(player, ct, pos)
    elif player.state == "bridge":
        _bridge(player, ct, pos)
    elif player.state == "economy":
        _economy(player, ct, pos)
    elif player.state == "suicide":
        player.state_turns += 1
        print(player.state_turns)
        if player.state_turns >= 50:
            player.state = "advance"
            player.state_seen_enemy = False
            player.target = None
            player.state_turns = 0
            return
        _suicide(player, ct, pos)
