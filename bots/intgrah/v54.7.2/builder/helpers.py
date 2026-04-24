from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Environment, Position, ResourceType
from util.constants import BASE_COST, INF, MAX_WIDTH
from util.debug import debug as log
from util.directions import DIR4, DIR8
from util.symmetry import Symmetry

from builder.algorithms.bugnav import bugnav

if TYPE_CHECKING:
    from builder import Builder


def make_move(self: Builder, ct: Controller, target: Position) -> bool:
    """Return True iff this call actually issued a move. 'Already at target'
    and 'path not found' both return False — neither advances the builder,
    so the caller shouldn't treat the turn as productive."""
    if self.my_pos == target:
        log(f"make_move: already on target tile {target}, no movement needed")
        return False

    path = self.move_search.search_blocked(ct, self.my_pos, target)
    if path is not None and len(path) > 1:
        next_step = path[1]
        log(
            f"make_move: walking from {self.my_pos} toward {target} via A* move "
            f"search; path has {len(path)} hops, stepping to {next_step} this turn",
        )
        return try_move_with_road(self, ct, next_step)
    next_move = bugnav(self, ct, target)
    if next_move:
        log(
            f"make_move: A* found no path from {self.my_pos} to {target}; falling "
            f"back to bugnav, stepping to {next_move} this turn",
        )
        return try_move_with_road(self, ct, next_move)
    log(
        f"make_move: FAILED to reach {target} from {self.my_pos}: A* returned no "
        "path and bugnav also failed; builder stays put this turn",
    )
    return False


def try_move_dir(ct: Controller, d: Direction) -> bool:
    if ct.can_move(d):
        log(f"try_move_dir: moving in direction {d}")
        ct.move(d)
        return True
    return False


def try_move_to(self: Builder, ct: Controller, target_pos: Position) -> bool:
    d = self.my_pos.direction_to(target_pos)
    if ct.can_move(d):
        log(
            f"try_move_to: stepping from {self.my_pos} toward {target_pos} in "
            f"direction {d}",
        )
        ct.move(d)
        return True
    return False


def try_move_with_road(self: Builder, ct: Controller, target_pos: Position) -> bool:
    if self.get_cost(target_pos) > 1 and ct.can_build_road(target_pos):
        log(
            f"try_move_with_road: paving road at {target_pos} before stepping onto "
            f"it (cost={self.get_cost(target_pos)} > 1, so road speeds up movement)",
        )
        ct.build_road(target_pos)
    return try_move_to(self, ct, target_pos)


def try_attack(ct: Controller, pos: Position) -> bool:
    if ct.can_fire(pos):
        log(f"try_attack: firing on tile {pos}")
        ct.fire(pos)
        return True
    return False


_IS_UNIT = frozenset(
    {EntityType.HARVESTER, EntityType.SENTINEL, EntityType.GUNNER, EntityType.LAUNCHER},
)
_EARLY_GAME_ROUND = 35
_HARVESTER_RESERVE_EARLY = 10
_HARVESTER_RESERVE_LATE = 20
_LAUNCHER_RESERVE = 15


def _foundry_reserve(self: Builder) -> int:
    """Ti reserved for a pending foundry placement. Kicks in once we've
    placed at least one Ax harvester (we're committing to the Ax economy
    and a foundry is expected to follow). Prevents other builders from
    spending the colony's last Ti on conveyors while a foundry is queued."""
    if self.round < 500:
        return 0
    if not self.ax_harvester_adjacent:
        return 0
    foundry_ti, _ = BASE_COST[EntityType.FOUNDRY]
    return int(foundry_ti * self.scale)


def _unit_reserve(self: Builder, etype: EntityType) -> int:
    """Ti a unit placement should leave on top of its own cost, to avoid
    spending the last Ti on a unit that then has no buffer to act."""
    if etype == EntityType.HARVESTER:
        return (
            _HARVESTER_RESERVE_EARLY
            if self.round < _EARLY_GAME_ROUND
            else _HARVESTER_RESERVE_LATE
        )
    if etype == EntityType.LAUNCHER:
        return _LAUNCHER_RESERVE
    return 0


def ti_needed(self: Builder, etype: EntityType) -> int:
    """Total Ti required to place `etype` on this tile, accounting for both
    the scaled build cost and all reserves. Single source of truth for
    `can_afford` and for user-facing "insufficient titanium" messages."""
    ti_cost, _ax_cost = BASE_COST[etype]
    if etype == EntityType.FOUNDRY:
        # Foundry placement itself doesn't need to preserve the reserve (it
        # IS the reserve target).
        return int(ti_cost * self.scale)
    if etype in _IS_UNIT:
        unit_reserve = _unit_reserve(self, etype)
        return int(
            (ti_cost + unit_reserve) * (1 + self.scale) + _foundry_reserve(self),
        )
    return int(ti_cost * self.scale + _foundry_reserve(self))


def can_afford(self: Builder, etype: EntityType) -> bool:
    return self.ti >= ti_needed(self, etype)


def try_place(
    self: Builder,
    ct: Controller,
    etype: EntityType,
    pos: Position,
    extra: Direction | Position | None = None,
    *,
    destroy: bool = True,
) -> bool:
    if not can_afford(self, etype):
        ti_base, _ax = BASE_COST[etype]
        need = ti_needed(self, etype)
        log(
            f"try_place: cannot build {etype.name} at {pos}: insufficient "
            f"titanium (have ti={self.ti}, need {need}; base cost {ti_base}, "
            f"scale {self.scale:.2f}, foundry_reserve={_foundry_reserve(self)}, "
            f"unit_reserve={_unit_reserve(self, etype)})",
        )
        return False
    if destroy and ct.can_destroy(pos):
        log(
            f"try_place: destroying existing building at {pos} to make room for "
            f"new {etype.name}",
        )
        ct.destroy(pos)
    if ct.can_build(etype, pos, extra):
        log(
            f"try_place: built {etype.name} at {pos} with extra={extra}; "
            f"ti before this action was {self.ti}, scale {self.scale:.2f}",
        )
        ct.build(etype, pos, extra)
        return True
    log(
        f"try_place: controller rejected build of {etype.name} at {pos} with "
        f"extra={extra} (can_build returned False; likely action cooldown, "
        "out of range, or invalid tile)",
    )
    return False


def trace_downstream(
    self: Builder,
    start_pos: Position,
    target_head: Position | None,
    path: list[Position] | None = None,
) -> list[Position]:
    if path is None:
        path = []
    current_pos = start_pos
    while True:
        path.append(current_pos)
        bld = self.get_building(current_pos)
        match bld:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                current_pos = current_pos.add(d)
            case BuildingSplitter(direction=d):
                for sd in DIR4:
                    if sd == d.opposite():
                        continue
                    new_pos = current_pos.add(sd)
                    if target_head:
                        new_path = trace_downstream(
                            self,
                            new_pos,
                            target_head,
                            path=path.copy(),
                        )
                        if new_path and target_head in new_path:
                            return new_path
                    elif self.get_building(new_pos) is None:
                        path.append(new_pos)
                        return path
                current_pos = current_pos.add(d)
            case BuildingBridge(target=t):
                current_pos = t
            case _:
                break
        if current_pos in path:
            break
    return path


def try_heal(
    self: Builder,
    ct: Controller,
    position: Position,
    *,
    conserve_ti: bool = True,
) -> bool:
    if conserve_ti and self.repair_pos is not None:
        i = self.idx(self.repair_pos)
        if not self.buildings[i] or self.hp[i] > self.max_hp[i] - 4:
            return False
    if ct.can_heal(position):
        ct.heal(position)
        return True
    return False


def get_enemy_core_pos(self: Builder) -> Position:
    for sym in (Symmetry.ROT, Symmetry.VER, Symmetry.HOR):
        if sym in self.symmetry_candidates:
            return sym.action(self.my_core, self.w, self.h)
    return Symmetry.ROT.action(self.my_core, self.w, self.h)


def move_random(self: Builder, ct: Controller) -> bool:
    dir8 = DIR8.copy()
    self.rng.shuffle(dir8)
    for direction in dir8:
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False


def trace_upstream(self: Builder, position: Position) -> list[Position]:
    path: list[Position] = []
    feeders = [position]
    while feeders:
        position = feeders[0]
        feeders = self.get_in_edges(position)
        if position in path:
            break
        path.append(position)
    return path


def ore_available(self: Builder, pos: Position) -> bool:
    b = self.get_building(pos)
    if b is not None and not isinstance(b, BuildingRoad | BuildingMarker):
        return False
    return not (pos in self.all_bots and self.all_bots[pos] != self.my_id)


def pick_ore_target(self: Builder) -> Position | None:
    return _pick_ore(self, Environment.ORE_TITANIUM)


def pick_ax_ore_target(self: Builder) -> Position | None:
    return _pick_ore(self, Environment.ORE_AXIONITE)


def pick_offensive_ti_ore_target(self: Builder) -> Position | None:
    """Pick an enemy-side Ti ore tile (more than r²=20 closer to enemy
    core than to ours) for an offensive harvester. Requires symmetry to
    be resolved; returns None otherwise."""
    if self.symmetry is None:
        return None
    enemy_core = get_enemy_core_pos(self)
    best_target = None
    min_dist = INF
    for pos in self.nearby_tiles:
        if self.get_env(pos) != Environment.ORE_TITANIUM:
            continue
        match self.get_building(pos):
            case BuildingHarvester():
                continue
            case None | BuildingRoad() | BuildingMarker():
                pass
            case _:
                continue
        d = self.bfs_dist[pos.y * MAX_WIDTH + pos.x]
        if d is INF:
            continue
        if not ore_available(self, pos):
            continue
        if (
            pos.distance_squared(enemy_core)
            >= pos.distance_squared(self.my_core) - _BISECTOR_MARGIN_R2
        ):
            continue
        if harvester_would_contaminate(self, pos):
            continue
        my_d = self.my_pos.distance_squared(pos)
        if any(fb.distance_squared(pos) < my_d for fb in self.friendly_bots):
            continue
        if d < min_dist:
            min_dist = d
            best_target = pos
    return best_target


def harvester_would_contaminate(self: Builder, pos: Position) -> bool:
    """True if placing a harvester on `pos` would leak the ore into an
    opposite-resource transport chain adjacent to it. A Ti harvester dumps
    titanium into every cardinal neighbour, which is bad if any neighbour
    is a friendly conveyor/bridge/splitter/armoured-conveyor that carries
    (or will carry) raw/refined axionite — and vice versa for Ax.

    Combines two checks so a vision-limited builder doesn't miss a known
    contamination:
    - Structural: the neighbour's upstream tree reaches a harvester on a
      bad-resource ore tile.
    - Empirical: the neighbour's flow_history shows a bad resource stack
      any time in the last 8 observed ticks.

    Exception for Ax ore: if exactly one cardinal neighbour is a pure
    friendly `BuildingConveyor` carrying Ti and there are NO heavy hostile
    neighbours (armoured / bridge / splitter), allow placement. That Ti
    conveyor is the designated foundry spot — the `build_foundry` task
    will replace it with a foundry once the zero-length Ax chain
    connects."""
    ore_env = self.get_env(pos)
    if ore_env == Environment.ORE_TITANIUM:
        bad_upstream = self.ax_upstream
        bad_flows = {ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE}
    elif ore_env == Environment.ORE_AXIONITE:
        bad_upstream = self.ti_upstream
        bad_flows = {ResourceType.TITANIUM}
    else:
        return False
    pure_ti_conveyor_count = 0
    heavy_hostile_count = 0
    hostile_found = False
    for d in DIR4:
        n = pos.add(d)
        if not self.in_bounds(n):
            continue
        b = self.get_building(n)
        if not isinstance(
            b,
            BuildingConveyor
            | BuildingArmouredConveyor
            | BuildingSplitter
            | BuildingBridge,
        ):
            continue
        if b.team != self.my_team:
            continue
        ni = n.y * MAX_WIDTH + n.x
        is_bad = n in bad_upstream or any(
            r in bad_flows for r, _rid in self.flow_history[ni]
        )
        if not is_bad:
            continue
        hostile_found = True
        if ore_env == Environment.ORE_AXIONITE:
            if isinstance(b, BuildingConveyor):
                pure_ti_conveyor_count += 1
            else:
                heavy_hostile_count += 1
    if not hostile_found:
        return False
    if (
        ore_env == Environment.ORE_AXIONITE
        and heavy_hostile_count == 0
        and pure_ti_conveyor_count == 1
    ):
        return False
    return True


_BISECTOR_MARGIN_R2 = 20


def _pick_ore(self: Builder, wanted: Environment) -> Position | None:
    enemy_core = get_enemy_core_pos(self)
    best_target = None
    min_dist = INF
    for pos in self.nearby_tiles:
        if self.get_env(pos) != wanted:
            continue
        match self.get_building(pos):
            case BuildingHarvester():
                continue
            case None | BuildingRoad() | BuildingMarker():
                pass
            case _:
                continue
        d = self.bfs_dist[pos.y * MAX_WIDTH + pos.x]
        if d is INF:
            continue
        if not ore_available(self, pos):
            continue
        # Bisector gate: skip ore that is more than r²=20 closer to enemy
        # core than to ours. Routing such ore home is expensive, and if we
        # could afford it we'd already have economic dominance.
        if (
            pos.distance_squared(self.my_core)
            > pos.distance_squared(enemy_core) + _BISECTOR_MARGIN_R2
        ):
            continue
        # Contamination gate: skip an ore if placing a harvester there would
        # leak Ti into an Ax chain (or Ax into a Ti chain) via an adjacent
        # transport tile.
        if harvester_would_contaminate(self, pos):
            continue
        # Coordination: skip an ore tile if any visible friendly builder is
        # strictly closer. Each builder ends up claiming the ores it is
        # nearest to, so several builders don't converge on the same tile
        # and deadlock while one places the harvester.
        my_d = self.my_pos.distance_squared(pos)
        if any(fb.distance_squared(pos) < my_d for fb in self.friendly_bots):
            continue
        if d < min_dist:
            min_dist = d
            best_target = pos
    return best_target


_UPSTREAM_MAX_NODES = 80
_DOWNSTREAM_MAX_NODES = 80


def upstream_tree(self: Builder, start: Position) -> set[Position]:
    """BFS backwards via `in_edges` — all friendly transport tiles whose
    output structurally reaches `start`."""
    visited: set[Position] = {start}
    queue: list[Position] = [start]
    while queue and len(visited) < _UPSTREAM_MAX_NODES:
        pos = queue.pop()
        for u in self.in_edges[pos.y * MAX_WIDTH + pos.x]:
            if u in visited:
                continue
            visited.add(u)
            queue.append(u)
    return visited


def downstream_tree(self: Builder, start: Position) -> set[Position]:
    """BFS forwards via `out_edges`."""
    visited: set[Position] = {start}
    queue: list[Position] = [start]
    while queue and len(visited) < _DOWNSTREAM_MAX_NODES:
        pos = queue.pop()
        for out in self.out_edges[pos.y * MAX_WIDTH + pos.x]:
            if out in visited:
                continue
            visited.add(out)
            queue.append(out)
    return visited


def chain_has_foundry(self: Builder, start: Position) -> bool:
    """Any friendly foundry in the up-or-downstream tree of `start`?"""
    for pos in upstream_tree(self, start):
        b = self.get_building(pos)
        if isinstance(b, BuildingFoundry) and b.team == self.my_team:
            return True
    for pos in downstream_tree(self, start):
        b = self.get_building(pos)
        if isinstance(b, BuildingFoundry) and b.team == self.my_team:
            return True
    return False


def ax_feeds_target(self: Builder, target: Position) -> bool:
    """Ax is (or will be) delivered to `target`. True iff any cardinal
    feeder is structurally downstream of an Ax harvester OR an Ax harvester
    is directly cardinal (the zero-length-chain case — harvesters aren't in
    `in_edges`, so the structural check alone misses them)."""
    for feeder in self.in_edges[target.y * MAX_WIDTH + target.x]:
        if feeder in self.ax_upstream:
            return True
    for d in DIR4:
        n = target.add(d)
        if not self.in_bounds(n):
            continue
        ni = n.y * MAX_WIDTH + n.x
        nb = self.buildings[ni]
        if (
            isinstance(nb, BuildingHarvester)
            and nb.team == self.my_team
            and self.env[ni] == Environment.ORE_AXIONITE
        ):
            return True
    return False


def tile_has_ax_flow(self: Builder, pos: Position) -> bool:
    """True if flow_history on `pos` shows raw or refined Ax in the last 8
    observed ticks."""
    for r, _rid in self.flow_history[pos.y * MAX_WIDTH + pos.x]:
        if r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
            return True
    return False
