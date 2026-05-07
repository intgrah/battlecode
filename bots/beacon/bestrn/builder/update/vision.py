from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import EntityType, Environment, GameConstants

if TYPE_CHECKING:
    from cambc import Position
from building import edge_targets, make_building
from util.directions import DIR8

if TYPE_CHECKING:
    from util.symmetry import Symmetry


def _remove_topology(builder, pos, i) -> None:
    old_kind = builder.building_kind[i]
    old_team = builder.building_team[i]
    my_team = builder.state.my_team
    if old_team == my_team and builder.out_edges[i]:
        outs: list[Position] = list(builder.out_edges[i])
        for t in outs:
            if not builder.in_bounds(t):
                continue
            ti = builder.idx(t)
            if pos in builder.in_edges[ti]:
                builder.in_edges[ti].__setitem__(
                    slice(None), [p for p in builder.in_edges[ti] if p != pos]
                )
                builder._on_in_edge_removed(t, pos)
                builder._check_multi_input(t)
                builder._check_dangling(t, f"edge_removed src={pos!r}")
        builder.out_edges[i] = []
        builder._on_out_edges_changed(pos)
    match old_kind:
        case EntityType.FOUNDRY if old_team == my_team:
            builder.my_foundries.discard(pos)
            builder._bump_foundry(pos, -1)
        case EntityType.HARVESTER:
            if old_team == my_team:
                builder.my_harvesters.discard(pos)
            env = builder.env[i]
            if env == Environment.ORE_AXIONITE:
                builder._bump_ax_harv(pos, -1)
            elif env == Environment.ORE_TITANIUM:
                builder._bump_ti_harv(pos, -1)
        case _:
            pass


def _add_topology(builder, ct, pos, bid, kind, team) -> None:
    i = int(pos.y) * 50 + int(pos.x)
    if builder.reach_parent[i] == -1:
        builder.reach_parent[i] = int(i)
        builder.reach_frontier.append(int(i))
    if team == builder.state.my_team:
        targets = edge_targets(ct, pos, bid, kind)
        if targets:
            outs: list[Position] = []
            for t in targets:
                if builder.in_bounds(t):
                    ti = builder.idx(t)
                    builder.in_edges[ti].append(pos)
                    outs.append(t)
                    builder._check_multi_input(t)
            was_ti_in = pos in builder.ti_upstream
            was_ax_in = pos in builder.ax_upstream
            pi = int(pos.y) * 50 + int(pos.x)
            builder.out_edges[pi] = list(outs)
            builder._on_out_edges_changed(pos)
            for t in outs:
                ti = builder.idx(t)
                if was_ti_in and (pos in builder.ti_upstream):
                    builder._ti_in_count[ti] += 1
                    builder._reeval_ti_upstream(t)
                if was_ax_in and (pos in builder.ax_upstream):
                    builder._ax_in_count[ti] += 1
                    builder._reeval_ax_upstream(t)
                builder._check_dangling(t, f"edge_added src={pos!r}")
            return
    match kind:
        case EntityType.FOUNDRY if team == builder.state.my_team:
            builder.my_foundries.add(pos)
            builder._bump_foundry(pos, 1)
        case EntityType.HARVESTER:
            if team == builder.state.my_team:
                builder.my_harvesters.add(pos)
            idx = builder.idx(pos)
            match builder.env[idx]:
                case Environment.ORE_AXIONITE:
                    builder._bump_ax_harv(pos, 1)
                case Environment.ORE_TITANIUM:
                    builder._bump_ti_harv(pos, 1)
                case _:
                    pass
        case _:
            pass


def _apply_post_transition(builder, pos, i, env, trigger) -> None:
    """
    Shared post-transition fix-up after a tile's building changes
    (added, removed, or replaced). Refreshes cost grid, precomputed
    neighbours, and dangling status for the tile and any splitter
    feeders whose satisfaction count may have flipped.
    """
    kind = builder.building_kind[i]
    team = builder.building_team[i]
    _update_cost(builder, i, env, kind, team)
    builder.update_pnb(i)
    builder._check_dangling(pos, trigger)
    feeders: list[Position] = list(builder.in_edges[i])
    for feeder in feeders:
        fi = int(feeder.y) * 50 + int(feeder.x)
        if builder.building_kind[fi] == EntityType.SPLITTER:
            siblings: list[Position] = list(builder.out_edges[fi])
            for sib in siblings:
                if sib != pos:
                    builder._check_dangling(sib, "splitter_sibling")


def apply_local_destroy(builder, pos) -> None:
    """Mid-turn invariant fix-up after `ct.destroy(pos)`."""
    i = builder.idx(pos)
    _remove_topology(builder, pos, i)
    builder.building_kind[i] = None
    builder.building_team[i] = None
    builder.hp[i] = 0
    builder.max_hp[i] = 0
    env = builder.env[i]
    _apply_post_transition(builder, pos, i, env, "local_destroy")
    _refresh_ore_set(builder, pos, env)


def _refresh_ore_set(builder, pos, env) -> None:
    """
    Maintain the incremental `visible_{ti,ax}_ores` sets: a tile is in
    the matching set iff its env is the corresponding ore type AND it
    has no harvester on it. Called wherever the env or building on
    `pos` may have changed (vision update, mid-turn local destroy).
    """
    i = builder.idx(pos)
    has_harvester = builder.building_kind[i] == EntityType.HARVESTER
    if env == Environment.ORE_TITANIUM:
        if has_harvester:
            builder.visible_ti_ores.discard(pos)
        else:
            builder.visible_ti_ores.add(pos)
        builder.visible_ax_ores.discard(pos)
    elif env == Environment.ORE_AXIONITE:
        if has_harvester:
            builder.visible_ax_ores.discard(pos)
        else:
            builder.visible_ax_ores.add(pos)
        builder.visible_ti_ores.discard(pos)
    else:
        builder.visible_ti_ores.discard(pos)
        builder.visible_ax_ores.discard(pos)


def _update_cost(builder, i, terrain, kind, team) -> None:
    routing_extra: int = 0
    if terrain == Environment.WALL:
        cost = 1000000
        buildable = False
    else:
        k = kind
        if k is not None:
            match k:
                case EntityType.ROAD if team == builder.state.my_team:
                    cost = 1
                    buildable = True
                case EntityType.ROAD:
                    cost = 1
                    buildable = True
                    routing_extra = 4
                case EntityType.MARKER:
                    cost = 3
                    buildable = True
                case (
                    EntityType.CONVEYOR
                    | EntityType.SPLITTER
                    | EntityType.ARMOURED_CONVEYOR
                    | EntityType.BRIDGE
                ):
                    cost = 1
                    buildable = False
                case EntityType.CORE if team == builder.state.my_team:
                    cost = 1
                    buildable = False
                case _:
                    cost = 1000000
                    buildable = False
        elif terrain == Environment.EMPTY:
            cost = 3
            buildable = True
        else:
            cost = 3
            buildable = False
    builder.cost_grid[i] = cost
    builder.routing_extra[i] = int(routing_extra)
    if builder.buildable[i] != buildable:
        builder.buildable[i] = buildable
        builder.ti_routable[i] = buildable and not builder.ti_leakage[i]
        builder.ax_routable[i] = buildable and not builder.ax_leakage[i]


def _update_turret_rays(builder, ct, pos, bid, kind, team) -> None:
    my_team = builder.state.my_team
    enemy = team != my_team
    match kind:
        case EntityType.LAUNCHER if enemy:
            for d in DIR8:
                n = pos.add(d)
                if builder.in_bounds(n):
                    builder.adjacent_to_enemy_launcher.add(n)
        case EntityType.GUNNER if enemy:
            d = ct.get_direction(bid)
            ray = pos
            for _ in range(3):
                ray = ray.add(d)
                if pos.distance_squared(ray) > GameConstants.GUNNER_VISION_RADIUS_SQ:
                    break
                if builder.in_bounds(ray):
                    builder.enemy_turret_ray_tiles.add(ray)
        case EntityType.SENTINEL if enemy:
            d = ct.get_direction(bid)
            for tile in ct.get_attackable_tiles_from(pos, d, EntityType.SENTINEL):
                builder.enemy_turret_ray_tiles.add(tile)
        case EntityType.GUNNER:
            d = ct.get_direction(bid)
            ray = pos
            for _ in range(3):
                ray = ray.add(d)
                if pos.distance_squared(ray) > GameConstants.GUNNER_VISION_RADIUS_SQ:
                    break
                if not builder.in_bounds(ray):
                    break
                if builder.env[builder.idx(ray)] == Environment.WALL:
                    break
                builder.friendly_turret_ray_tiles.add(ray)
                if builder.get_building(ray) is not None:
                    break
        case EntityType.SENTINEL:
            d = ct.get_direction(bid)
            ray = pos
            for _ in range(6):
                ray = ray.add(d)
                if pos.distance_squared(ray) > 32:
                    break
                if not builder.in_bounds(ray):
                    break
                if builder.env[builder.idx(ray)] == Environment.WALL:
                    break
                builder.friendly_turret_ray_tiles.add(ray)
                for hd in DIR8:
                    h = ray.add(hd)
                    if builder.in_bounds(h):
                        builder.friendly_turret_ray_tiles.add(h)
                if builder.get_building(ray) is not None:
                    break
        case _:
            pass


def update_vision(builder, ct) -> None:
    new_observations: list[tuple[Position, Environment, bool]] = []
    nearby = list(builder.state.nearby_tiles)
    for pos in nearby:
        pos = pos
        i = builder.idx(pos)
        env = ct.get_tile_env(pos)
        bid = ct.get_tile_building_id(pos)
        env_changed = builder.env[i] != env
        bld_changed = builder.building_ids[i] != bid
        if builder.env[i] is None:
            builder.reflect_queue.append(i)
            is_core = bid is not None and (
                lambda b: ct.get_entity_type(b) == EntityType.CORE
            )(bid)
            new_observations.append((pos, env, is_core))
            if env != Environment.WALL:
                py = pos.y
                px = pos.x
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dx == 0 and dy == 0:
                            continue
                        nx = px + dx
                        ny = py + dy
                        if nx not in range(builder.state.width) or ny not in range(
                            builder.state.height
                        ):
                            continue
                        ni = int(ny) * 50 + int(nx)
                        if builder.reach_parent[ni] != -1:
                            builder.reach_frontier.append(int(ni))
        builder.env[i] = env
        builder.building_ids[i] = bid
        if bld_changed or env_changed:
            if bid is None:
                apply_local_destroy(builder, pos)
            else:
                _remove_topology(builder, pos, i)
                bid_v = bid
                kind, team = make_building(ct, bid_v)
                builder.building_kind[i] = kind
                builder.building_team[i] = team
                builder.hp[i] = ct.get_hp(bid)
                builder.max_hp[i] = ct.get_max_hp(bid)
                _add_topology(builder, ct, pos, bid_v, kind, team)
                _apply_post_transition(builder, pos, i, env, "building_changed")
            bid_v = bid
            kind = builder.building_kind[i]
            team = builder.building_team[i]
            if bid_v is not None and kind is not None and team is not None:
                _update_turret_rays(builder, ct, pos, bid_v, kind, team)
        elif bid is not None:
            builder.hp[i] = ct.get_hp(bid)
            builder.max_hp[i] = ct.get_max_hp(bid)
        _refresh_ore_set(builder, pos, env)
        if bid is not None:
            kind = builder.building_kind[i]
            team = builder.building_team[i]
            builder.nearby_buildings.append(pos)
            if builder.hp[i] < builder.max_hp[i] and team == builder.state.my_team:
                builder.healable_buildings.append(pos)
            if (kind is not None) and (
                kind
                in (
                    EntityType.CONVEYOR,
                    EntityType.ARMOURED_CONVEYOR,
                    EntityType.BRIDGE,
                    EntityType.SPLITTER,
                )
            ):
                bid_v = bid
                r = ct.get_stored_resource(bid_v)
                rid = ct.get_stored_resource_id(bid_v)
                builder.flow_history[i].append((r, rid))
                while len(builder.flow_history[i]) > 8:
                    (
                        builder.flow_history[i].pop(0)
                        if builder.flow_history[i]
                        else None
                    )
    if builder.symmetry is None:
        _narrow_symmetry(builder, new_observations)


def _narrow_symmetry(builder, new_observations) -> None:
    invalid: set[Symmetry] = set()
    candidates: list[Symmetry] = list(builder.state.symmetry_candidates)
    w = builder.state.width
    h = builder.state.height
    for sym in candidates:
        for pos, env, is_core in new_observations:
            m = sym.action(pos, w, h)
            mi = int(m.y) * 50 + int(m.x)
            mirror_env = builder.env[mi]
            mirror_env = mirror_env
            if mirror_env is None:
                continue
            mirror_is_core = builder.building_kind[mi] == EntityType.CORE
            if mirror_env != env or mirror_is_core != is_core:
                invalid.add(sym)
                break
    for sym in invalid:
        builder.state.symmetry_candidates.discard(sym)
