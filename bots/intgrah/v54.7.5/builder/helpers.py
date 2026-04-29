from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBridge,
    BuildingConveyor,
    BuildingCore,
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
from util.metrics import claims_by_proximity

if TYPE_CHECKING:
    from builder import Builder


def make_move(self: Builder, ct: Controller, target: Position) -> bool:
    """Return True iff this call actually issued a move. 'Already at target'
    and 'no plan' both return False — neither advances the builder, so the
    caller shouldn't treat the turn as productive.

    Uses bug2-bounded planner with dp_step path-follower. Plan state lives
    on `self.bugnav` and persists across turns for the same goal.
    """
    if self.my_pos == target:
        log("make_move: already on target {target}", target=target)
        return False
    next_move = self.bugnav.step(self, target)
    if next_move is None:
        # Bugnav can't find a plan that progresses (typically two builders
        # head-butting in a corridor — both planners route through each
        # other's tile). Take a random unblocked step to break the
        # deadlock; one builder yielding lets the other progress.
        if move_random(self, ct):
            log(
                "make_move: bugnav stuck, took random step {start}->{target}",
                start=self.my_pos,
                target=target,
            )
            return True
        log(
            "make_move: FAILED {start}->{target} (bugnav: no plan, random step also blocked)",
            start=self.my_pos,
            target=target,
        )
        return False
    log(
        "make_move: bugnav {start}->{target} step {next}",
        start=self.my_pos,
        target=target,
        next=next_move,
    )
    return try_move_with_road(self, ct, next_move)


def try_move_dir(ct: Controller, d: Direction) -> bool:
    if ct.can_move(d):
        log("try_move_dir: moving {dir}", dir=d)
        ct.move(d)
        return True
    return False


def try_move_to(self: Builder, ct: Controller, target_pos: Position) -> bool:
    d = self.my_pos.direction_to(target_pos)
    if ct.can_move(d):
        log(
            "try_move_to: {start}->{target} dir {dir}",
            start=self.my_pos,
            target=target_pos,
            dir=d,
        )
        dx = target_pos.x - self.my_pos.x
        dy = target_pos.y - self.my_pos.y
        self.explore_heading = (
            (dx > 0) - (dx < 0),
            (dy > 0) - (dy < 0),
        )
        ct.move(d)
        return True
    return False


def try_move_with_road(self: Builder, ct: Controller, target_pos: Position) -> bool:
    if self.get_cost(target_pos) > 1 and ct.can_build_road(target_pos):
        log(
            "try_move_with_road: paving road at {target} (cost={cost} > 1)",
            target=target_pos,
            cost=self.get_cost(target_pos),
        )
        ct.build_road(target_pos)
    return try_move_to(self, ct, target_pos)


def try_attack(ct: Controller, pos: Position) -> bool:
    if ct.can_fire(pos):
        log("try_attack: firing on {pos}", pos=pos)
        ct.fire(pos)
        return True
    return False


def ti_needed(self: Builder, etype: EntityType) -> int:
    base = BASE_COST[etype][0]
    scale = self.scale
    foundry = (
        int(BASE_COST[EntityType.FOUNDRY][0] * scale)
        if self.round >= 500 and self.ax_harvester_adjacent
        else 0
    )
    """Once we've committed to an Ax economy (round >= 500 with at least
    one Ax harvester visible), keep enough Ti banked for a foundry so
    other builders can't drain the colony before it's placed.
    """
    match etype:
        case EntityType.FOUNDRY:
            return int(base * scale)
        case EntityType.HARVESTER:
            reserve = 10 if self.round < 35 else 20
            return int((base + reserve) * (1 + scale)) + foundry
        case EntityType.LAUNCHER:
            return int((base + 15) * (1 + scale)) + foundry
        case EntityType.SENTINEL | EntityType.GUNNER:
            return int(base * (1 + scale)) + foundry
        case _:
            return int(base * scale) + foundry


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
        log(
            "try_place: cannot afford {etype} at {pos} "
            "(have {have}, need {need}; base {base}, scale {scale:.2f})",
            etype=etype,
            pos=pos,
            have=self.ti,
            need=ti_needed(self, etype),
            base=BASE_COST[etype][0],
            scale=self.scale,
        )
        return False
    if destroy and ct.can_destroy(pos):
        log(
            "try_place: destroying existing building at {pos} for {etype}",
            pos=pos,
            etype=etype,
        )
        ct.destroy(pos)
    if ct.can_build(etype, pos, extra):
        log(
            "try_place: built {etype} at {pos} extra={extra} (ti={ti}, scale={scale:.2f})",
            etype=etype,
            pos=pos,
            extra=extra,
            ti=self.ti,
            scale=self.scale,
        )
        ct.build(etype, pos, extra)
        return True
    log(
        "try_place: controller rejected {etype} at {pos} extra={extra} (can_build False)",
        etype=etype,
        pos=pos,
        extra=extra,
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
        log("try_heal: healing {pos}", pos=position)
        ct.heal(position)
        return True
    return False


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
    if b is not None:
        if isinstance(b, BuildingRoad | BuildingMarker | BuildingBarrier):
            pass
        elif isinstance(
            b, BuildingConveyor | BuildingArmouredConveyor,
        ) and _is_inward_guard_on_ore(self, pos):
            pass
        else:
            return False
    return not (pos in self.all_bots and self.all_bots[pos] != self.my_id)


def harvester_feed_cardinal(self: Builder, ore_pos: Position) -> Position | None:
    """The cardinal of `ore_pos` chosen as the future flow-feed slot —
    the empty cardinal closest to the relevant sink. Reserved per
    harvester so the harvester always has at least one consumer side.

    Sink direction is bisector-aware: harvesters on our side feed back
    toward `ti_sink` / `my_core`. Harvesters on the enemy side
    (offensive) feed FORWARD toward `enemy_core`, so the gap left in
    the surrounding barrier ring opens toward the push, not back home.

    Returns None if every cardinal already hosts a flow consumer or the
    builder, or if no sink is known. Excludes the builder's own tile
    (transient: the builder will step off; that tile may become the
    feed too, but it's already an I/O slot regardless of sink choice).
    """
    if on_enemy_side(self, ore_pos):
        sink = self.en_core_guess if self.symmetry is not None else None
    else:
        sink = self.ti_sink if self.ti_sink is not None else self.my_core
    if sink is None:
        return None
    free: list[Position] = []
    for d in DIR4:
        c = ore_pos.add(d)
        if not self.in_bounds(c):
            continue
        if c == self.my_pos:
            continue
        b = self.get_building(c)
        if isinstance(
            b,
            BuildingConveyor
            | BuildingArmouredConveyor
            | BuildingSplitter
            | BuildingBridge
            | BuildingFoundry
            | BuildingCore
            | BuildingHarvester,
        ):
            continue
        # The feed cardinal must have at least one passable neighbour
        # other than the ore itself. Otherwise the harvester's output
        # has nowhere to flow — feed becomes a dead-end pocket.
        has_outlet = False
        for d2 in DIR4:
            n = c.add(d2)
            if n == ore_pos:
                continue
            if not self.in_bounds(n):
                continue
            if not self.is_passable(n):
                continue
            has_outlet = True
            break
        if not has_outlet:
            continue
        free.append(c)
    if not free:
        return None
    return min(free, key=lambda c: c.distance_squared(sink))


def harvester_io_cardinals(self: Builder, ore_pos: Position) -> set[Position]:
    """Cardinals of `ore_pos` that must NOT be barriered: they are (or
    will become) the harvester's flow input/output side.

    Excluded:
    - The cardinal already hosts a friendly transport (conveyor / armoured
      conveyor / splitter / bridge), foundry, core, or another harvester
      — already a flow path or blocked by a sibling harvester.
    - The builder's own current tile (will become the chain feed when
      the builder steps off the ore).
    - The cardinal returned by `harvester_feed_cardinal` (chosen feed
      direction toward the sink).
    """
    cardinals = [ore_pos.add(d) for d in DIR4 if self.in_bounds(ore_pos.add(d))]
    reserved: set[Position] = set()
    for c in cardinals:
        if c == self.my_pos:
            reserved.add(c)
            continue
        b = self.get_building(c)
        if isinstance(
            b,
            BuildingConveyor
            | BuildingArmouredConveyor
            | BuildingSplitter
            | BuildingBridge
            | BuildingFoundry
            | BuildingCore
            | BuildingHarvester,
        ):
            reserved.add(c)

    feed = harvester_feed_cardinal(self, ore_pos)
    if feed is not None:
        reserved.add(feed)
    return reserved


def harvester_barrier_saturated(self: Builder, ore_pos: Position) -> bool:
    """True iff at least 3 of `ore_pos`'s 4 in-bounds cardinals already
    host a barrier. Used to prevent placing a 4th barrier and sealing
    the harvester off — different builders may compute different feed
    cardinals and disagree on which side to leave open, so each
    barrier-placement site must independently refuse to fill the last
    open cardinal.
    """
    barriers = 0
    for d in DIR4:
        c = ore_pos.add(d)
        if not self.in_bounds(c):
            continue
        if isinstance(self.get_building(c), BuildingBarrier):
            barriers += 1
    return barriers >= 3


def pick_ore_target(self: Builder) -> Position | None:
    return _pick_ore(self, Environment.ORE_TITANIUM)


def pick_ax_ore_target(self: Builder) -> Position | None:
    return _pick_ore(self, Environment.ORE_AXIONITE)


def pick_offensive_ti_ore_target(self: Builder) -> Position | None:
    """Pick an enemy-side Ti ore tile (more than r²=20 closer to enemy
    core than to ours) for an offensive harvester. Requires symmetry to
    be resolved; returns None otherwise.
    """
    if self.symmetry is None:
        return None
    enemy_core = self.en_core_guess
    best_target = None
    min_dist = INF
    for pos in self.nearby_tiles:
        if self.get_env(pos) != Environment.ORE_TITANIUM:
            continue
        match self.get_building(pos):
            case BuildingHarvester():
                continue
            case None | BuildingRoad() | BuildingMarker() | BuildingBarrier():
                pass
            case BuildingConveyor() | BuildingArmouredConveyor():
                if not _is_inward_guard_on_ore(self, pos):
                    continue
            case _:
                continue
        if not self.is_reachable(pos):
            continue
        d = self.my_pos.distance_squared(pos)
        if not ore_available(self, pos):
            continue
        if (
            pos.distance_squared(enemy_core)
            >= pos.distance_squared(self.my_core) - _BISECTOR_MARGIN_R2
        ):
            continue
        if harvester_would_contaminate(self, pos):
            continue
        if not claims_by_proximity(
            self.my_pos,
            self.my_id,
            pos,
            (
                (fb_pos, fb_id)
                for fb_pos, fb_id in self.all_bots.items()
                if fb_id != self.my_id and fb_pos in self.friendly_bots
            ),
        ):
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
    connects.
    """
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
    return not (
        ore_env == Environment.ORE_AXIONITE
        and heavy_hostile_count == 0
        and pure_ti_conveyor_count == 1
    )


_BISECTOR_MARGIN_R2 = 20


def on_enemy_side(self: Builder, pos: Position) -> bool:
    """True if `pos` is more than r²=20 closer to enemy_core than to ours.
    Mirrors the rule used by `_pick_ore` for harvester placement, so econ
    routing of harvester outputs uses the same split: ours-side tiles are
    routed home, enemy-side tiles are left for OFFENSE's `push_extend`.
    Requires symmetry to be resolved; returns False otherwise.
    """
    if self.symmetry is None:
        return False
    enemy_core = self.en_core_guess
    return (
        pos.distance_squared(self.my_core)
        > pos.distance_squared(enemy_core) + _BISECTOR_MARGIN_R2
    )


def _is_inward_guard_on_ore(self: Builder, pos: Position) -> bool:
    """True if `pos` hosts a friendly conveyor whose flow direction
    points at an adjacent friendly harvester. Such conveyors are
    harvester guards (placed by the proactive ring of an adjacent
    harvester); we're allowed to destroy them when claiming the ore
    underneath as a new harvester site."""
    b = self.get_building(pos)
    if not isinstance(b, BuildingConveyor | BuildingArmouredConveyor):
        return False
    if b.team != self.my_team:
        return False
    target = pos.add(b.direction)
    if not self.in_bounds(target):
        return False
    target_b = self.get_building(target)
    return isinstance(target_b, BuildingHarvester) and target_b.team == self.my_team


def _pick_ore(self: Builder, wanted: Environment) -> Position | None:
    enemy_core = self.en_core_guess
    best_target = None
    min_dist = INF
    for pos in self.nearby_tiles:
        if self.get_env(pos) != wanted:
            continue
        match self.get_building(pos):
            case BuildingHarvester():
                continue
            case None | BuildingRoad() | BuildingMarker() | BuildingBarrier():
                pass
            case BuildingConveyor() | BuildingArmouredConveyor():
                # Allow only if it's our own inward guard pointing at
                # an adjacent friendly harvester — we'll destroy it
                # before claiming. Outward / sideways / enemy conveyors
                # still block.
                if not _is_inward_guard_on_ore(self, pos):
                    continue
            case _:
                continue
        if not self.is_reachable(pos):
            continue
        d = self.my_pos.distance_squared(pos)
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
        if not claims_by_proximity(
            self.my_pos,
            self.my_id,
            pos,
            (
                (fb_pos, fb_id)
                for fb_pos, fb_id in self.all_bots.items()
                if fb_id != self.my_id and fb_pos in self.friendly_bots
            ),
        ):
            continue
        if d < min_dist:
            min_dist = d
            best_target = pos
    return best_target


_UPSTREAM_MAX_NODES = 80
_DOWNSTREAM_MAX_NODES = 80


def upstream_tree(self: Builder, start: Position) -> set[Position]:
    """BFS backwards via `in_edges` — all friendly transport tiles whose
    output structurally reaches `start`.
    """
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
    `in_edges`, so the structural check alone misses them).
    """
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
    observed ticks.
    """
    for r, _rid in self.flow_history[pos.y * MAX_WIDTH + pos.x]:
        if r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
            return True
    return False
