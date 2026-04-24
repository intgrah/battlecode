"""Chain-laying for Ti and Ax harvester outputs.

Public entry: `route_chain(self, ct, start)`. Internals handle resource
classification, upstream-tree reuse, conveyor/bridge placement, and the
foundry-retarget side effect when an Ax chain lands on a Ti conveyor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingConveyor,
    BuildingHarvester,
)
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    Position,
    ResourceType,
)
from util.constants import MAX_WIDTH
from util.debug import debug, line
from util.directions import DIR4, DIR8, get_direction_object
from util.metrics import chebyshev, reachable_path_end

from builder.helpers import (
    make_move,
    trace_upstream,
    try_move_with_road,
    try_place,
)

if TYPE_CHECKING:
    from builder import Builder


_UPSTREAM_MAX_NODES_RES = 80
"""Cap on upstream BFS size in `resource_at`."""


def resource_at(self: Builder, pos: Position) -> ResourceType | None:
    """Infer which resource a chain starting at `pos` carries. Returns None
    if it can't be determined — caller must NOT silently default to Ti,
    because routing Ax as Ti sends raw Ax to the core where it's destroyed.
    """
    ax_adj = pos in self.ax_harvester_adjacent
    ti_adj = pos in self.ti_harvester_adjacent
    if ax_adj and not ti_adj:
        return ResourceType.RAW_AXIONITE
    if ti_adj and not ax_adj:
        return ResourceType.TITANIUM

    seen_ti = False
    seen_ax = False
    visited: set[Position] = {pos}
    stack: list[Position] = [pos]
    while stack and len(visited) < _UPSTREAM_MAX_NODES_RES:
        p = stack.pop()
        if p in self.ti_harvester_adjacent:
            seen_ti = True
        if p in self.ax_harvester_adjacent:
            seen_ax = True
        pi = p.y * MAX_WIDTH + p.x
        for r, _rid in self.flow_history[pi]:
            if r is None:
                continue
            if r == ResourceType.TITANIUM:
                seen_ti = True
            elif r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
                seen_ax = True
        if seen_ti and seen_ax:
            return None
        for u in self.in_edges[pi]:
            if u in visited:
                continue
            visited.add(u)
            stack.append(u)

    if seen_ax and not seen_ti:
        return ResourceType.RAW_AXIONITE
    if seen_ti and not seen_ax:
        return ResourceType.TITANIUM
    return None


def best_harvester_neighbour(
    self: Builder,
    dangling: Position,
    target: Position,
) -> Position:
    """If `dangling` is a cardinal neighbour of an unconnected harvester,
    pick whichever side of the harvester is closest to `target` — otherwise
    A* lays a much longer chain than necessary."""
    for d in DIR4:
        h = dangling.add(d)
        if not self.in_bounds(h):
            continue
        hb = self.get_building(h)
        if not isinstance(hb, BuildingHarvester):
            continue
        if hb.team != self.my_team:
            continue
        best = dangling
        best_d = dangling.distance_squared(target)
        for d2 in DIR4:
            n = h.add(d2)
            if not self.in_bounds(n):
                continue
            if n not in self.adjacent_to_unconnected_harvester:
                continue
            nd = n.distance_squared(target)
            if nd < best_d:
                best_d = nd
                best = n
        return best
    return dangling


def _retarget_foundry_to_junction(self: Builder, landing: Position) -> None:
    """If an Ax chain segment we just placed lands on a pre-existing friendly
    Ti conveyor with pure-Ti flow history, retarget `foundry_target` to that
    tile — it's the natural junction."""
    if self.foundry_target == landing:
        return
    bld = self.get_building(landing)
    if not isinstance(bld, BuildingConveyor | BuildingArmouredConveyor):
        return
    if bld.team != self.my_team:
        return
    hist = self.flow_history[landing.y * MAX_WIDTH + landing.x]
    saw_ti = False
    has_ax = False
    for r, _rid in hist:
        if r == ResourceType.TITANIUM:
            saw_ti = True
        elif r in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE):
            has_ax = True
    if not saw_ti or has_ax:
        return
    debug(f"retarget foundry to junction at {landing}")
    self.foundry_target = landing


def _clear_with_turret(
    self: Builder,
    ct: Controller,
    build_pos: Position,
    target_pos: Position,
) -> bool:
    """Step off `build_pos` if needed, then place a sentinel facing
    `target_pos`."""
    if build_pos == self.my_pos:
        for d in DIR8:
            if ct.can_move(d):
                ct.move(d)
                break
    if build_pos == ct.get_position():
        for d in DIR8:
            if try_move_with_road(self, ct, ct.get_position().add(d)):
                break
    direction = build_pos.direction_to(target_pos)
    return try_place(self, ct, EntityType.SENTINEL, build_pos, direction)


def _lay_segment(
    self: Builder,
    ct: Controller,
    start_pos: Position,
    path: list[Position] | None,
) -> bool:
    """Place one conveyor / bridge at `start_pos` that advances along
    `path`. Returns True iff an action was taken."""
    if not path:
        return False

    bid = ct.get_tile_building_id(start_pos)
    entity_type = ct.get_entity_type(bid) if bid else None
    direction: Direction | None = None
    if (
        self.my_core
        and start_pos.distance_squared(self.my_core) <= 5
        and path[-1] == self.my_core
    ):
        for d in DIR4:
            if start_pos.add(d).distance_squared(self.my_core) <= 2:
                direction = d
                break
    else:
        direction = get_direction_object(start_pos, path[1])

    if entity_type == EntityType.CONVEYOR:
        if ct.get_direction(bid) == direction:
            return True
    elif entity_type == EntityType.BRIDGE:
        bridge_output = ct.get_bridge_target(bid)
        if not ct.is_in_vision(bridge_output) or self.is_buildable(bridge_output):
            return True

    next_pos = path[1]
    if not ct.is_in_vision(next_pos):
        target = reachable_path_end(path, start_pos, 3)
        return try_place(self, ct, EntityType.BRIDGE, start_pos, target)

    destination_building = ct.get_tile_building_id(next_pos)
    destination_team = (
        ct.get_team(destination_building) if destination_building else None
    )
    destination_is_marker = (
        ct.get_entity_type(destination_building) == EntityType.MARKER
        if destination_building
        else False
    )

    if (
        direction in DIR4
        and (
            (not destination_building)
            or destination_team == self.my_team
            or destination_is_marker
        )
        and self.get_env(path[1]) == Environment.EMPTY
    ):
        ok = try_place(self, ct, EntityType.CONVEYOR, start_pos, direction)
        if ok:
            line(ct, start_pos, next_pos, 255, 255, 0)
            _retarget_foundry_to_junction(self, next_pos)
        return ok

    pending_bridge = reachable_path_end(path, start_pos, 3)
    if self.is_enemy_building(pending_bridge):
        _clear_with_turret(self, ct, start_pos, pending_bridge)
        return False
    if try_place(self, ct, EntityType.BRIDGE, start_pos, pending_bridge):
        _retarget_foundry_to_junction(self, pending_bridge)
        return True
    return False


def _route_to(
    self: Builder,
    ct: Controller,
    start: Position,
    target: Position,
    resource: ResourceType,
) -> bool:
    """Return True iff a useful action was taken this turn (a conveyor was
    placed, a bridge was placed, or the builder moved)."""
    if start == target:
        return False
    if chebyshev(start, target) <= 1 and target == self.my_core:
        return False

    current_pos = self.my_pos
    existing_path = trace_upstream(self, start)
    if not existing_path:
        return False

    if not self.is_passable(start):
        if len(existing_path) > 1:
            start = existing_path[-2]
        else:
            return False

    search = (
        self.ax_conv_search
        if resource in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE)
        else self.conv_search
    )
    path = search.search(ct, start, target, resource)
    if path is None:
        debug(f"A* {resource.name} {start}->{target}: {search.last_fail_reason}")
    else:
        is_ax = resource in (ResourceType.RAW_AXIONITE, ResourceType.REFINED_AXIONITE)
        colour = (200, 0, 255) if is_ax else (80, 160, 255)
        for i in range(len(path) - 1):
            line(ct, path[i], path[i + 1], *colour)

    if path:
        path_start_index = 0
        for i, pos in enumerate(path):
            if pos in existing_path:
                start = pos
                path_start_index = i
        path = path[path_start_index:]

    did_something = False
    if chebyshev(current_pos, start) <= 1:
        if not path or len(path) < 2:
            return False
        if _lay_segment(self, ct, start, path):
            did_something = True
    if make_move(self, ct, start):
        did_something = True
    return did_something


def route_chain(self: Builder, ct: Controller, start: Position) -> bool:
    """Route a chain from `start` toward the right sink. Ti -> ti_sink
    (nearest Ti conveyor reaching core, or core itself). Ax -> ax_sink. Ax
    chains are skipped when no ax_sink is set, to prevent raw Ax being
    shipped to the core where it would be destroyed."""
    resource = resource_at(self, start)
    if resource is None:
        debug(f"cannot classify resource at {start}")
        return False
    if resource == ResourceType.RAW_AXIONITE:
        target = self.ax_sink
        if target is None:
            debug(f"chain at {start} is Ax but ax_sink is None")
            return False
        start = best_harvester_neighbour(self, start, target)
        return _route_to(self, ct, start, target, resource)
    target = self.ti_sink if self.ti_sink is not None else self.my_core
    start = best_harvester_neighbour(self, start, target)
    return _route_to(self, ct, start, target, resource)


def route_chain_toward(
    self: Builder,
    ct: Controller,
    start: Position,
    target: Position,
) -> bool:
    """Route a chain from `start` toward `target`, regardless of which
    sink the resource would normally feed. Used by PUSH builders to
    extend dangling ends toward the enemy core."""
    start = best_harvester_neighbour(self, start, target)
    return _route_to(self, ct, start, target, ResourceType.TITANIUM)
