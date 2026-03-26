"""Builder bot unit logic for v5."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, Direction, EntityType, Environment, Position
from pathfinding import _ALL_DIRS, _DIR_IDX, bug2_step, has_line_of_sight
from utils import (
    PHASE_FOUND,
    SYM_TYPES,
    build_walkable,
    encode_comms,
    encode_waypoint,
    get_symmetry_candidates,
    in_bounds,
    king_dist,
    mirror_pos,
    place_comms,
    read_comms,
    try_move_smart,
)

# ── Comms ─────────────────────────────────────────────────────────────


def _check_comms(player: Player, ct: Controller) -> None:
    if player.core_pos is None:
        return
    sym, _phase, epos, scout_idx = read_comms(ct, player.core_pos)
    # On first run, read scout assignment from core's marker
    if player.state is None and 0 < scout_idx <= 3:
        player.scout_idx = scout_idx - 1
    if sym is not None and player.enemy_core is None:
        player.sym_resolved = sym
        player.enemy_core = epos


def _write_comms(
    player: Player,
    ct: Controller,
    sym_name: str,
    enemy_pos: Position,
) -> None:
    if player.comms_written or player.core_pos is None:
        return
    value = encode_comms(sym_name, PHASE_FOUND, enemy_pos.x, enemy_pos.y)
    if place_comms(ct, player.core_pos, value):
        player.comms_written = True
        print(
            f"Scout {player.scout_idx}: wrote comms [{sym_name}] "
            f"({enemy_pos.x},{enemy_pos.y})",
        )


# ── Symmetry detection ───────────────────────────────────────────────


def _detect_symmetry(player: Player, ct: Controller, pos: Position) -> None:
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
                    f"Scout {player.scout_idx}: FOUND enemy core at ({epos.x},{epos.y}) [{s}]",
                )
                _write_comms(player, ct, s, epos)
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
                            f"Scout {player.scout_idx}: FOUND enemy core at "
                            f"({actual_pos.x},{actual_pos.y}) [{s}]",
                        )
                        _write_comms(player, ct, s, actual_pos)
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

    if player.try_resolve(w, h, f"Scout {player.scout_idx}"):
        if player.sym_resolved and player.enemy_core:
            _write_comms(player, ct, player.sym_resolved, player.enemy_core)


# ── Pathfinding helpers ──────────────────────────────────────────────


def _pf_draw_debug(player: Player, ct: Controller, walkable: set) -> None:
    """Draw debug indicators for Bug2 pathfinding state."""
    a = player.pf_agent

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


def _pf_step(player: Player, ct: Controller, pos: Position) -> bool:
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

    # Run bug2_step — returns desired next Position
    next_pos = bug2_step(player.pf_agent, pos, walkable, occupied)

    # Debug indicators
    _pf_draw_debug(player, ct, walkable)

    if next_pos == pos:
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
        return True

    # Move failed — revert agent position so it retries next turn
    player.pf_agent.current = pos
    return False


# ── Ore scanning (runs every turn for all builders) ──────────────────


def _scan_ore(player: Player, ct: Controller) -> None:
    """Record any ore tiles visible this turn."""
    for tile in ct.get_nearby_tiles():
        env = ct.get_tile_env(tile)
        if env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
            player.known_ore.add(tile)


# ── Economy ──────────────────────────────────────────────────────────


# ── Bridge chain ────────────────────────────────────────────────────


def _start_bridge_chain(
    player: Player,
    ct: Controller,
    pos: Position,
    source_pos: Position,
) -> None:
    """Enter bridge state: pick first bridge tile adjacent to source, closest to core."""
    if player.core_pos is None:
        return

    best = None
    best_dist = 999999
    for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
        bp = source_pos.add(d)
        if not in_bounds(ct, bp):
            continue
        if ct.is_in_vision(bp) and ct.get_tile_env(bp) == Environment.WALL:
            continue
        dist = king_dist(bp, player.core_pos)
        if dist < best_dist:
            best_dist = dist
            best = bp
    if best is not None:
        player.state = "bridge"
        player.bridge_target = best
        player.pf_agent.retarget(pos, best)
        print(f"Bridge E{ct.get_id()}: chain start, first bridge at {best}")


def _bridge(player: Player, ct: Controller, pos: Position) -> None:
    """Build a chain of bridges from harvester to core."""
    if player.bridge_target is None or player.core_pos is None:
        player.state = "economy"
        player.target = None
        return

    # If adjacent to bridge_target, try to build
    if pos.distance_squared(player.bridge_target) <= 2:
        if ct.get_action_cooldown() > 0:
            return

        # Destroy road on bridge tile if present
        bt = player.bridge_target
        bid = ct.get_tile_building_id(bt)
        if bid is not None:
            if ct.can_destroy(bt):
                ct.destroy(bt)
            else:
                player.state = "economy"
                player.target = None
            return  # action used, try building next turn

        # Scan bridge-range tiles: look for core shortcut, existing bridge, or normal candidates
        bt_core_dist = king_dist(bt, player.core_pos)
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
                # Direct to core?
                if player.core_pos.distance_squared(t) <= 2:
                    if core_target is None:
                        core_target = t
                    continue
                # Existing friendly bridge closer to core?
                tbid = ct.get_tile_building_id(t)
                if tbid is not None:
                    td = king_dist(t, player.core_pos)
                    etype = ct.get_entity_type(tbid)
                    friendly = ct.get_team() == ct.get_team(tbid)
                    if (
                        etype == EntityType.BRIDGE
                        and friendly
                        and td < bridge_shortcut_dist
                    ):
                        bridge_shortcut = t
                        bridge_shortcut_dist = td
                    if friendly and etype != EntityType.MARKER:
                        candidates.append((king_dist(t, player.core_pos), t))
                    continue
                # Normal candidate (empty, walkable)
                if ct.get_tile_env(t) == Environment.WALL:
                    continue
                candidates.append((king_dist(t, player.core_pos), t))

        # Priority 1: direct to core
        if core_target is not None and ct.can_build_bridge(bt, core_target):
            ct.build_bridge(bt, core_target)
            print(
                f"Bridge E{ct.get_id()}: built at {bt} -> {core_target} (direct to core)",
            )
            player.state = "economy"
            player.target = None
            player.bridge_target = None
            return

        # Priority 2: shortcut to existing bridge
        if bridge_shortcut is not None and ct.can_build_bridge(bt, bridge_shortcut):
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
        candidates.sort()

        built = False
        for _, target in candidates:
            if ct.can_build_bridge(bt, target):
                ct.build_bridge(bt, target)
                print(f"Bridge E{ct.get_id()}: built at {bt} -> {target}")
                # Check if output lands on core
                if player.core_pos.distance_squared(target) <= 2:
                    player.state = "idle"
                    player.bridge_target = None
                    print(f"Bridge E{ct.get_id()}: chain complete")
                    return
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
    if ct.get_move_cooldown() > 0:
        return
    if player.pf_agent.goal != player.bridge_target:
        player.pf_agent.retarget(pos, player.bridge_target)
    _pf_step(player, ct, pos)


# ── Wander ──────────────────────────────────────────────────────────


def _wander(player: Player, ct: Controller, pos: Position) -> None:
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
        score = king_dist(tile, near_friend) * 4

        # Momentum: prefer similar direction to last step
        if player.last_dir is not None:
            diff = abs(_DIR_IDX[d] - _DIR_IDX[player.last_dir])
            diff = min(diff, 8 - diff)
            score -= diff * 2

        # Away from border
        score += min(tile.x, tile.y, w - 1 - tile.x, h - 1 - tile.y, 5)

        if score > best_score:
            best_score = score
            best_dir = d

    if best_dir is not None and try_move_smart(ct, pos, best_dir):
        player.last_dir = best_dir


def _economy(player: Player, ct: Controller, pos: Position) -> None:
    """Economy mode: harvest nearest ore, opportunistically switch to LOS ore,
    or wander to discover more."""

    # Check current ore target — abort if already harvested
    if player.target is not None:
        if ct.is_in_vision(player.target):
            bid = ct.get_tile_building_id(player.target)
            if bid is not None:
                etype = ct.get_entity_type(bid)
                if etype == EntityType.HARVESTER or ct.get_team(bid) != ct.get_team():
                    player.claimed_ore.add(player.target)
                    player.target = None
                elif etype == EntityType.ROAD and ct.can_destroy(player.target):
                    ct.destroy(player.target)

        # Move off ore if standing on it
        if player.target is not None and pos == player.target:
            if ct.get_move_cooldown() == 0:
                for d in _ALL_DIRS:
                    tile = pos.add(d)
                    if (
                        in_bounds(ct, tile)
                        and ct.get_tile_env(tile) != Environment.WALL
                    ) and try_move_smart(ct, pos, d):
                        return
            return

        # Build harvester if adjacent to ore target
        if player.target is not None and pos.distance_squared(player.target) <= 2:
            if ct.get_action_cooldown() == 0 and ct.can_build_harvester(player.target):
                ct.build_harvester(player.target)
                print(f"Econ E{ct.get_id()}: built harvester at {player.target}")
                player.claimed_ore.add(player.target)
                ore_pos = player.target
                # Enter bridge mode: connect harvester to core
                _start_bridge_chain(player, ct, pos, ore_pos)
                return
            return  # wait until we can build or ore is claimed

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

    # Pathfind to ore, or wander if no ore known
    if player.target is not None:
        if player.pf_agent.goal != player.target:
            player.pf_agent.retarget(pos, player.target)
        _pf_step(player, ct, pos)
    else:
        _wander(player, ct, pos)


# ── Scout states ─────────────────────────────────────────────────────


def _pick_target(player: Player, pos: Position) -> None:
    """Set target based on assigned candidate."""
    if player.enemy_core and player.sym_resolved == player.candidate_sym:
        player.target = player.enemy_core
        return
    if not player.sym_candidates:
        return
    if player.candidate_sym and player.candidate_sym not in player.sym_eliminated:
        player.target = player.sym_candidates[player.candidate_sym]


def _scout_out(player: Player, ct: Controller, pos: Position) -> None:
    if player.target is None:
        return

    rnd = ct.get_current_round()
    tracing = player.pf_agent.is_tracing
    if rnd <= 20 or rnd % 20 == 0:
        print(
            f"Scout {player.scout_idx}: R{rnd} ({pos.x},{pos.y})->{player.target} "
            f"tracing={tracing}",
        )

    player.visited.add(pos)
    if not player.path or player.path[-1] != pos:
        player.path.append(pos)

    # Check if we've found the enemy core (detected by _detect_symmetry)
    if player.enemy_core and player.sym_resolved == player.candidate_sym:
        player.target = player.enemy_core
        if ct.is_in_vision(player.enemy_core):
            print(
                f"Scout {player.scout_idx}: enemy core in sight, entering report phase",
            )
            player.state = "scout_report"
            player.pf_agent.retarget(pos, player.core_pos)
            return

    if ct.get_move_cooldown() > 0:
        return

    # Re-target Bug2 if goal changed
    if player.pf_agent.goal != player.target:
        player.pf_agent.retarget(pos, player.target)

    _pf_step(player, ct, pos)


def _try_build_launcher(player: Player, ct: Controller, pos: Position) -> bool:
    """Try to build a launcher + waypoint marker to speed return to core.
    Returns True if a launcher was built (builder should wait to be thrown)."""
    if player.core_pos is None or player.enemy_core is None:
        return False
    if ct.get_action_cooldown() > 0:
        return False

    # Don't build if we're already close to core
    if pos.distance_squared(player.core_pos) <= 20:
        return False

    # Don't build if we haven't moved far enough from the last launcher
    if (
        player.last_launcher_pos is not None
        and pos.distance_squared(player.last_launcher_pos) <= 20
    ):
        return False

    # Prefer launcher toward enemy core, marker away from it
    enemy_dir = pos.direction_to(player.enemy_core)
    if enemy_dir == Direction.CENTRE:
        enemy_dir = Direction.NORTH
    enemy_idx = _DIR_IDX[enemy_dir]

    # Try launcher tiles: closest to enemy direction first
    launcher_tile = None
    for offset in [0, 1, -1, 2, -2, 3, -3, 4]:
        d = _ALL_DIRS[(enemy_idx + offset) % 8]
        tile = pos.add(d)
        if in_bounds(ct, tile) and ct.can_build_launcher(tile):
            launcher_tile = tile
            break

    if launcher_tile is None:
        return False

    ct.build_launcher(launcher_tile)
    player.last_launcher_pos = launcher_tile

    # Place waypoint marker: prefer opposite direction from enemy (toward core)
    wp_value = encode_waypoint(
        player.core_pos.x,
        player.core_pos.y,
        player.enemy_core.x,
        player.enemy_core.y,
    )
    core_idx = (enemy_idx + 4) % 8  # opposite direction
    for offset in [0, 1, -1, 2, -2, 3, -3, 4]:
        d = _ALL_DIRS[(core_idx + offset) % 8]
        wp_tile = pos.add(d)
        if in_bounds(ct, wp_tile) and ct.can_place_marker(wp_tile):
            ct.place_marker(wp_tile, wp_value)
            break

    player.built_launcher = True
    print(f"Scout {player.scout_idx}: built launcher at {launcher_tile}")

    return True


def _scout_report(player: Player, ct: Controller, pos: Position) -> None:
    """Walk back toward own core using Bug2, building launchers to speed the trip."""
    if player.core_pos is None:
        return

    # Write comms if we can (in case we haven't yet)
    if player.sym_resolved and player.enemy_core:
        _write_comms(player, ct, player.sym_resolved, player.enemy_core)

    # Check if we're back at core
    if pos.distance_squared(player.core_pos) <= 2:
        print(f"Scout {player.scout_idx}: returned to core, entering economy")
        player.state = "economy"
        player.target = None
        return

    if player.built_launcher:
        player.built_launcher = False
        return

    if ct.get_move_cooldown() > 0:
        return

    # Try to build a launcher for a speed boost
    if _try_build_launcher(player, ct, pos):
        return  # wait for throw next turn

    if player.pf_agent.goal != player.core_pos:
        player.pf_agent.retarget(pos, player.core_pos)

    _pf_step(player, ct, pos)


# ── Main entry point ─────────────────────────────────────────────────


def run_builder(player: Player, ct: Controller) -> None:
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

    # Scan for ore every turn
    _scan_ore(player, ct)

    # Check comms markers for enemy core info from other scouts
    _check_comms(player, ct)

    # Symmetry elimination from vision
    _detect_symmetry(player, ct, pos)

    # Init state on first run — scout_idx was set by _check_comms above
    if player.state is None:
        player.state = "scout_out"
        if player.scout_idx < 0 or player.scout_idx >= 3:
            player.scout_idx = player.scout_idx % 3
        player.candidate_sym = SYM_TYPES[player.scout_idx]
        _pick_target(player, pos)
        print(
            f"Scout {player.scout_idx} (E{ct.get_id()}): assigned [{player.candidate_sym}] "
            f"target={player.target} elim={player.sym_eliminated}",
        )

    # Handle scout target changes
    if player.state == "scout_out":
        if player.sym_resolved:
            if player.sym_resolved == player.candidate_sym:
                player.target = player.enemy_core
            else:
                print(
                    f"Scout {player.scout_idx}: candidate "
                    f"[{player.candidate_sym}] not needed "
                    f"(resolved={player.sym_resolved}), going economy",
                )
                player.state = "economy"
                player.target = None
        elif player.candidate_sym in player.sym_eliminated:
            print(
                f"Scout {player.scout_idx}: [{player.candidate_sym}] "
                f"eliminated, going economy",
            )
            player.state = "economy"
            player.target = None

    # Idle -> economy transition
    if player.state == "idle":
        pass

    # Run state
    if player.state == "scout_out":
        _scout_out(player, ct, pos)
    elif player.state == "scout_report":
        _scout_report(player, ct, pos)
    elif player.state == "bridge":
        _bridge(player, ct, pos)
    elif player.state == "economy":
        _economy(player, ct, pos)
