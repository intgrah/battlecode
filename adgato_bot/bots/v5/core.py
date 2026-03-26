"""Core unit logic for v5."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, Direction, EntityType, Position
from pathfinding import _ALL_DIRS, _DIR_IDX
from utils import (
    PHASE_FOUND,
    SYM_TYPES,
    comms_tiles,
    encode_comms,
    get_symmetry_candidates,
    is_waypoint_marker,
    mirror_pos,
    place_comms,
    read_comms,
)


def run_core(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    w, h = ct.get_map_width(), ct.get_map_height()
    rnd = ct.get_current_round()

    if player.core_pos is None:
        player.core_pos = pos

    # Init symmetry candidates
    if player.sym_candidates is None:
        player.sym_candidates = get_symmetry_candidates(pos, w, h)
        seen: dict[Position, str] = {}
        for s, epos in player.sym_candidates.items():
            if epos == pos or epos in seen:
                player.sym_eliminated.add(s)
            else:
                seen[epos] = s

    # Read comms markers from scouts
    if player.sym_resolved is None:
        sym, phase, epos, _ = read_comms(ct, pos)
        if sym is not None:
            player.sym_resolved = sym
            player.enemy_core = epos
            player.core_phase = max(player.core_phase, phase)
            print(f"Core: enemy at {epos} [{sym}] phase={phase}")

    # Core's own symmetry elimination via vision (r²=36)
    if player.sym_resolved is None:
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
        if player.try_resolve(w, h, "Core"):
            player.core_phase = PHASE_FOUND

    # Write/refresh all comms markers — overwrite any with stale phase
    sym_name = player.sym_resolved or "unknown"
    ex = player.enemy_core.x if player.enemy_core else 0
    ey = player.enemy_core.y if player.enemy_core else 0
    value = encode_comms(sym_name, player.core_phase, ex, ey, player.spawned)
    has_current = False
    for tile in comms_tiles(ct, pos):
        bid = ct.get_tile_building_id(tile)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.MARKER
            and ct.get_team(bid) == ct.get_team()
        ):
            old_val = ct.get_marker_value(bid)
            if not is_waypoint_marker(old_val):
                if old_val == value:
                    has_current = True
                elif ct.can_place_marker(tile):
                    ct.place_marker(tile, value)
                    has_current = True
    if not has_current:
        place_comms(ct, pos, value)

    # Debug output
    if rnd % 100 == 1:
        ti, ax = ct.get_global_resources()
        sym_str = player.sym_resolved or "?"
        ec_str = (
            f"({player.enemy_core.x},{player.enemy_core.y})"
            if player.enemy_core
            else "?"
        )
        print(
            f"R{rnd} Ti:{ti} Ax:{ax} spawned:{player.spawned} "
            f"sym:{sym_str} enemy:{ec_str} phase:{player.core_phase}",
        )

    # Spawning
    if ct.get_action_cooldown() > 0:
        return

    # Spawn scout biased toward its candidate direction
    candidates_list = (
        list(player.sym_candidates.items()) if player.sym_candidates else []
    )
    if player.spawned < len(candidates_list):
        _, target_pos = candidates_list[player.spawned]
    else:
        return

    # Try spawn tiles in order of direction similarity to target
    target_dir = pos.direction_to(target_pos)
    if target_dir == Direction.CENTRE:
        target_dir = Direction.NORTH
    target_idx = _DIR_IDX[target_dir]
    best_spawn = None
    for offset in [0, 1, -1, 2, -2, 3, -3, 4]:
        d = _ALL_DIRS[(target_idx + offset) % 8]
        p = pos.add(d)
        if ct.can_spawn(p):
            best_spawn = p
            break
    if best_spawn is None and ct.can_spawn(pos):
        best_spawn = pos

    if best_spawn:
        ct.spawn_builder(best_spawn)
        player.spawned += 1
