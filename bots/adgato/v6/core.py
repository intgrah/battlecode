"""Core unit logic for v6."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import Player

from cambc import Controller, Direction, EntityType, Position, ResourceType
from pathfinding import _ALL_DIRS, _DIR_IDX
from utils import (
    PHASE_FOUND,
    SYM_TYPES,
    Symmetry,
    comms_tiles,
    encode_comms,
    get_symmetry_candidates,
    is_waypoint_marker,
    king_dist,
    mirror_pos,
    place_comms,
    read_comms,
)


def _init_symmetry(
    player: Player,
    ct: Controller,
    pos: Position,
    w: int,
    h: int,
) -> None:
    if player.sym_candidates is not None:
        return
    player.sym_candidates = get_symmetry_candidates(pos, w, h)
    seen: dict[Position, Symmetry] = {}
    for s, epos in player.sym_candidates.items():
        if epos == pos or epos in seen:
            player.sym_eliminated.add(s)
        else:
            seen[epos] = s


def _read_comms(player: Player, ct: Controller, pos: Position) -> None:
    if player.sym_resolved is not None:
        return
    sym, phase, epos, _ = read_comms(ct, pos)
    if sym is not None:
        player.sym_resolved = sym
        player.enemy_core = epos
        player.core_phase = max(player.core_phase, phase)
        print(f"Core: enemy at {epos} [{sym.value}] phase={phase}")


def _eliminate_symmetry(
    player: Player,
    ct: Controller,
    pos: Position,
    w: int,
    h: int,
) -> None:
    if player.sym_resolved is not None:
        return
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
    if player.try_resolve("Core"):
        player.core_phase = PHASE_FOUND


def _write_comms(player: Player, ct: Controller, pos: Position) -> None:
    sym_name: Symmetry | str = player.sym_resolved or "unknown"
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


def _debug_output(player: Player, ct: Controller, rnd: int) -> None:
    for bid, counts in player.splitter_resource_counts.items():
        sp = player.known_splitters.get(bid) if player.known_splitters else None
        d = ct.get_position().direction_to(sp) if sp else "?"
        ti_count = counts.get(ResourceType.TITANIUM, 0)
        ax_count = counts.get(ResourceType.RAW_AXIONITE, 0)
        print(f"{d}, TI {ti_count} AX {ax_count}")


def _spawn_initial(player: Player, ct: Controller, pos: Position) -> None:
    """Spawn first builders. First 3 toward enemy core, rest at cardinal offsets."""
    enemy_pos = player.enemy_core or (
        player.sym_candidates[Symmetry.ROTATIONAL] if player.sym_candidates else None
    )
    if enemy_pos is None:
        return
    enemy_dir = pos.direction_to(enemy_pos)
    if enemy_dir == Direction.CENTRE:
        enemy_dir = Direction.NORTH
    enemy_idx = _DIR_IDX[enemy_dir]

    if player.spawned < 1:
        # First 3: spawn toward enemy, trying nearby offsets
        for offset in [0, -1, 1, -2, 2]:
            d = _ALL_DIRS[(enemy_idx + offset) % 8]
            spawn_pos = pos.add(d)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                player.spawned += 1
                print(f"Spawning advance builder in dir {d}")
                return
    else:
        # Remaining: rotate through cardinals away from enemy
        first = (enemy_idx + 7 * (enemy_idx % 2)) % 8
        d = _ALL_DIRS[(first + player.spawned * 2) % 8]
        print(f"Spawning in dir {d}")
        spawn_pos = pos.add(d)
        if ct.can_spawn(spawn_pos):
            ct.spawn_builder(spawn_pos)
            player.spawned += 1


def _spawn_economy(player: Player, ct: Controller, pos: Position, rnd: int) -> None:
    """After turn 23, spawn alternating advance/economy builders on matching round parity."""
    if rnd <= 23:
        return

    # Advance builders on even rounds, economy on odd
    spawn_advance = not player.next_spawn_economy
    if spawn_advance and rnd % 2 != 0:
        return
    if not spawn_advance and rnd % 2 != 1:
        return

    ti, _ = ct.get_global_resources()
    builder_cost, _ = ct.get_builder_bot_cost()
    harvester_cost, _ = ct.get_harvester_cost()

    if spawn_advance and ti - builder_cost < 400 + rnd // 2:
        return
    if not spawn_advance and ti - builder_cost - harvester_cost < 400 + rnd // 2:
        return

    best_pos = None
    best_dist = 999999
    my_team = ct.get_team()
    for bid in ct.get_nearby_buildings():
        if (
            ct.get_entity_type(bid) != EntityType.LAUNCHER
            or ct.get_team(bid) != my_team
        ):
            continue
        lp = ct.get_position(bid)
        d = lp.distance_squared(pos)
        if d < best_dist:
            best_dist = d
            best_pos = lp

    spawn_dir = Direction.CENTRE if best_pos is None else pos.direction_to(best_pos)

    spawn_pos = pos.add(spawn_dir)
    if ct.can_spawn(spawn_pos):
        ct.spawn_builder(spawn_pos)
        player.spawned += 1
        player.next_spawn_economy = not player.next_spawn_economy
        player.spawned_economy += 0 if spawn_advance else 1
        player.spawned_advance += 1 if spawn_advance else 0
        print(f"Spawned {'advance' if spawn_advance else 'economy'} builder")


def run_core(player: Player, ct: Controller) -> None:
    pos = ct.get_position()
    w, h = ct.get_map_width(), ct.get_map_height()
    rnd = ct.get_current_round()

    if player.core_pos is None:
        player.core_pos = pos

    print(f"spawn economy {player.spawned_economy}")
    print(f"spawn advance {player.spawned_advance}")

    _init_symmetry(player, ct, pos, w, h)
    _read_comms(player, ct, pos)
    _eliminate_symmetry(player, ct, pos, w, h)
    _write_comms(player, ct, pos)
    _debug_output(player, ct, rnd)

    # Detect damage — queue emergency spawns based on damage taken
    cur_hp = ct.get_hp()
    if (
        cur_hp < ct.get_max_hp() * 0.6
        and player.last_hp is not None
        and cur_hp < player.last_hp
    ):
        damage = player.last_hp - cur_hp
        spawns = (damage + 9) // 10  # ceil(damage / 10)
        player.damage_spawns_remaining += spawns
        print(
            f"Core: taking damage! HP {player.last_hp} -> {cur_hp}, queuing {spawns} spawns",
        )
    player.last_hp = cur_hp
    if cur_hp == ct.get_max_hp():
        player.max_hp_turns += 1
    else:
        player.max_hp_turns = 0

    if player.damage_spawns_remaining > 0:
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            spawn_pos = pos.add(d)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                player.spawned += 1
                player.damage_spawns_remaining -= 1
                print(
                    f"Core: emergency spawn {d} ({player.damage_spawns_remaining} remaining)",
                )
                break

    # Track splitters near core and spawn replacements for destroyed ones
    my_team = ct.get_team()
    current_splitters = {}
    for bid in ct.get_nearby_buildings():
        if (
            ct.get_entity_type(bid) == EntityType.SPLITTER
            and ct.get_team(bid) == my_team
        ):
            sp = ct.get_position(bid)
            if king_dist(sp, pos) <= 2:
                current_splitters[bid] = sp

    if player.known_splitters is not None:
        for old_bid, old_pos in player.known_splitters.items():
            if old_bid not in current_splitters:
                # Splitter was destroyed — queue a spawn in its direction
                d = pos.direction_to(old_pos)
                if d != Direction.CENTRE:
                    player.splitter_respawn_queue.append(d)
                    print(
                        f"Core: splitter {old_bid} destroyed at {old_pos}, queuing spawn {d}",
                    )
    player.known_splitters = current_splitters

    # Track resource contents of each splitter every turn
    # Clean up destroyed splitters from counts
    for old_bid in list(player.splitter_resource_counts):
        if old_bid not in current_splitters:
            del player.splitter_resource_counts[old_bid]
    for bid in current_splitters:
        if bid not in player.splitter_resource_counts:
            player.splitter_resource_counts[bid] = {}
        counts = player.splitter_resource_counts[bid]
        res = ct.get_stored_resource(bid)
        for rt in (ResourceType.TITANIUM, ResourceType.RAW_AXIONITE):
            if res == rt:
                counts[rt] = counts.get(rt, 0) + 10
            else:
                counts[rt] = max(0, counts.get(rt, 0) - 1)

    if ct.get_action_cooldown() > 0:
        return

    # Spawn replacements for destroyed splitters first
    if player.splitter_respawn_queue:
        d = player.splitter_respawn_queue[0]
        spawn_pos = pos.add(d)
        if ct.can_spawn(spawn_pos):
            ct.spawn_builder(spawn_pos)
            player.spawned += 1
            player.splitter_respawn_queue.pop(0)
            print(f"Core: spawned replacement builder toward {d}")
            return

    # If flush with titanium, spawn toward the best splitter
    # Priority: splitters that have seen both Ti and raw Ax > most total ore observed
    ti, _ = ct.get_global_resources()
    builder_cost, _ = ct.get_builder_bot_cost()
    foundary_cost, _ = ct.get_foundry_cost()
    should_spawn = (
        ti - builder_cost - foundary_cost > max(0, 250 - rnd)
    ) and player.max_hp_turns >= 1000
    if should_spawn:
        print("wants to spawn foundry")
    if should_spawn and current_splitters:
        has_both = [
            bid
            for bid, sp in current_splitters.items()
            if bid in player.splitter_resource_counts
            and player.splitter_resource_counts[bid].get(ResourceType.TITANIUM, 0) > 0
            and player.splitter_resource_counts[bid].get(ResourceType.RAW_AXIONITE, 0)
            > 0
        ]
        if has_both:
            ranked = sorted(
                has_both,
                key=lambda b: min(player.splitter_resource_counts[b].values()),
                reverse=True,
            )
            for bid in ranked:
                sp = current_splitters[bid]
                d = pos.direction_to(sp)
                if d == Direction.CENTRE or player.busiest_spawned_dirs.get(d, 0) >= 2:
                    continue
                spawn_pos = pos.add(d)
                if ct.can_spawn(spawn_pos):
                    ct.spawn_builder(spawn_pos)
                    player.spawned += 1
                    player.busiest_spawned_dirs[d] = (
                        player.busiest_spawned_dirs.get(d, 0) + 1
                    )
                    print(f"Core: spawned economy builder toward splitter at {sp}")
                    return

    if player.spawned < 5:
        _spawn_initial(player, ct, pos)
    else:
        _spawn_economy(player, ct, pos, rnd)

    if ct.can_heal(pos):
        ct.heal(pos)
        print("healed")
