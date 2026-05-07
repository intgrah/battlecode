"""
Chain-laying for Ti and Ax harvester outputs.

Two public entry points share a single one-step worker `extend_step`:

- `extend_chain` — auto-pick target by resource (Ti -> `ti_sink`, Ax ->
  `ax_sink`). Used by ECON's chain-extension tasks.
- `extend_step` — picks an explicit target. Used by OFFENSE
  (`push_extend`) to point at the enemy core.

Failures return `Err(TaskRejected)` so callers don't need their own
wrapper types.
"""

from __future__ import annotations

from typing import Final

from cambc import Direction, EntityType, Position, ResourceType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import (
    make_move,
    on_enemy_side,
    trace_upstream,
    try_move_with_road,
    try_place,
)
from builder.tasks.rejected import TaskRejected
from util.constants import MAX_WIDTH
from util.debug import Scope, debug, line
from util.directions import DIR4, DIR8, delta_to_dir, get_direction_object, is_cardinal
from util.metrics import chebyshev, reachable_path_end
from util.visualiser import auto_wrap_position

_UPSTREAM_MAX_NODES_RES: Final[int] = 80
"""Cap on upstream BFS size in `resource_at`."""


def resource_at(builder, pos):
    """
    Infer which resource a chain starting at `pos` carries. Returns None
    if it can't be determined — caller must NOT silently default to Ti,
    because routing Ax as Ti sends raw Ax to the core where it's destroyed.
    """
    ax_adj = pos in builder.ax_harvester_adjacent
    ti_adj = pos in builder.ti_harvester_adjacent
    if ax_adj and not ti_adj:
        return ResourceType.RAW_AXIONITE
    if ti_adj and not ax_adj:
        return ResourceType.TITANIUM
    seen_ti = False
    seen_ax = False
    visited: set[Position] = set()
    visited.add(pos)
    stack: list[Position] = [pos]
    while (p := (stack.pop() if stack else None)) is not None:
        if len(visited) > 80:
            break
        if p in builder.ti_harvester_adjacent:
            seen_ti = True
        if p in builder.ax_harvester_adjacent:
            seen_ax = True
        pi = int(p.y) * 50 + int(p.x)
        for r, _rid in builder.flow_history[pi]:
            match r:
                case ResourceType.TITANIUM:
                    seen_ti = True
                case ResourceType.RAW_AXIONITE | ResourceType.REFINED_AXIONITE:
                    seen_ax = True
                case _:
                    pass
        if seen_ti and seen_ax:
            return None
        for u in builder.in_edges[pi]:
            if u in visited:
                continue
            visited.add(u)
            stack.append(u)
    if seen_ax and not seen_ti:
        return ResourceType.RAW_AXIONITE
    if seen_ti and not seen_ax:
        return ResourceType.TITANIUM
    return None


def _retarget_foundry_to_junction(builder, landing):
    """
    If an Ax chain segment we just placed lands on a pre-existing friendly
    Ti conveyor with pure-Ti flow history, retarget `foundry_target` to that
    tile — it's the natural junction.
    """
    if builder.foundry_target == landing:
        return
    kind = builder.building_kind[builder.idx(landing)]
    team = builder.building_team[builder.idx(landing)]
    if not (
        (kind is not None)
        and (kind == EntityType.CONVEYOR or kind == EntityType.ARMOURED_CONVEYOR)
    ):
        return
    if team != builder.state.my_team:
        return
    hist = builder.flow_history[int(landing.y) * 50 + int(landing.x)]
    saw_ti = False
    has_ax = False
    for r, _rid in hist:
        match r:
            case ResourceType.TITANIUM:
                saw_ti = True
            case ResourceType.RAW_AXIONITE | ResourceType.REFINED_AXIONITE:
                has_ax = True
            case _:
                pass
    if not saw_ti or has_ax:
        return
    args = {}
    args[str("landing")] = auto_wrap_position(landing)
    debug("retarget foundry to junction at {landing}", args)
    builder.foundry_target = landing


def _clear_with_turret(builder, ct, build_pos, target_pos):
    """
    Step off `build_pos` if needed, then place a sentinel facing
    `target_pos`.
    """
    if build_pos == builder.state.my_pos:
        for d in DIR8:
            if ct.can_move(d):
                ct.move(d)
                break
    if build_pos == ct.get_position(None):
        for d in DIR8:
            pos = ct.get_position(None).add(d)
            if try_move_with_road(builder, ct, pos):
                break
    dx = target_pos.x - build_pos.x
    dy = target_pos.y - build_pos.y
    direction = delta_to_dir(dx, dy)
    if direction is None:
        return False
    return try_place(builder, ct, EntityType.SENTINEL, build_pos, direction, True)


def _lay_segment(builder, ct, start_pos, path):
    """
    Place one conveyor / bridge at `start_pos` that advances along `path`.
    Returns True iff an action was taken.
    """
    if not path:
        return False
    bid = ct.get_tile_building_id(start_pos)
    entity_type: EntityType | None = (
        (lambda b: ct.get_entity_type(b))(bid) if bid is not None else None
    )
    b = bid
    if (
        (entity_type == EntityType.ROAD)
        and b is not None
        and (ct.get_team(b) != builder.state.my_team)
        and (ct.can_fire(start_pos))
    ):
        args = {}
        args[str("pos")] = auto_wrap_position(start_pos)
        debug("chain: fire on enemy road at {pos}", args)
        ct.fire(start_pos)
        return True
    direction: Direction | None = None
    if (
        start_pos.distance_squared(builder.my_core) <= 5
        and path[len(path) - 1] == builder.my_core
    ):
        for d in DIR4:
            if start_pos.add(d).distance_squared(builder.my_core) <= 2:
                direction = d
                break
    else:
        direction = get_direction_object(start_pos, path[1])
    if entity_type == EntityType.CONVEYOR and ct.get_direction(bid) == (
        direction if direction is not None else Direction.CENTRE
    ):
        return True
    b = bid
    if (entity_type == EntityType.BRIDGE) and b is not None:
        bridge_output = ct.get_bridge_target(b)
        if not ct.is_in_vision(bridge_output) or builder.is_buildable(bridge_output):
            return True
    next_pos = path[1]
    if not ct.is_in_vision(next_pos):
        target = reachable_path_end(path, start_pos, 3)
        return try_place(builder, ct, EntityType.BRIDGE, start_pos, target, True)
    destination_building = ct.get_tile_building_id(next_pos)
    destination_team: object | None = (
        (lambda b: ct.get_team(b))(destination_building)
        if destination_building is not None
        else None
    )
    destination_is_marker = (
        ct.get_entity_type(b) == EntityType.MARKER
        if ((b := destination_building) is not None)
        else False
    )
    d = direction
    if (
        d is not None
        and (is_cardinal(d))
        and (
            (destination_building is None)
            or destination_team == builder.state.my_team
            or destination_is_marker
        )
    ):
        ok = try_place(builder, ct, EntityType.CONVEYOR, start_pos, d, True)
        if ok:
            line(ct, start_pos, next_pos, 255, 255, 0)
            _retarget_foundry_to_junction(builder, next_pos)
        return ok
    pending_bridge = reachable_path_end(path, start_pos, 3)
    if builder.is_enemy_building(pending_bridge):
        _clear_with_turret(builder, ct, start_pos, pending_bridge)
        return False
    if try_place(builder, ct, EntityType.BRIDGE, start_pos, pending_bridge, True):
        _retarget_foundry_to_junction(builder, pending_bridge)
        return True
    return False


def extend_step(builder, ct, start, target, resource):
    """Lay one segment toward `target` and/or take one step toward it."""
    if start == target:
        return TaskRejected.from_string(f"start == target ({start!r})")
    if chebyshev(start, target) <= 1 and target == builder.my_core:
        return TaskRejected.from_string(
            f"{start!r} is already adjacent to core; nothing to lay"
        )
    current_pos = builder.state.my_pos
    existing_path = trace_upstream(builder, start)
    if not existing_path:
        return TaskRejected.from_string(f"no upstream chain reaches {start!r}")
    if not builder.cost_grid[builder.idx(start)] != 1000000:
        if len(existing_path) > 1:
            start = existing_path[len(existing_path) - 2]
        else:
            return TaskRejected.from_string(
                f"{start!r} is unpassable and no upstream fallback"
            )
    is_ax = (
        resource == ResourceType.RAW_AXIONITE
        or resource == ResourceType.REFINED_AXIONITE
    )
    with Scope.new_timed("conv_astar") as _g:
        __block_value = (
            builder.ax_conv_astar(start, target, resource)
            if is_ax
            else builder.ti_conv_astar(start, target, resource)
        )
    path = __block_value
    path = path
    if path is None:
        fail = (
            list(builder.ax_conv_search.last_fail_reason)
            if is_ax
            else list(builder.conv_search.last_fail_reason)
        )
        return TaskRejected.from_string(f"A* {resource} {start!r}->{target!r}: {fail}")
    colour: tuple[int, int, int] = (200, 0, 255) if is_ax else (80, 160, 255)
    for i in range(0, len(path) - 1):
        line(ct, path[i], path[i + 1], colour[0], colour[1], colour[2])
    existing_set: set[Position] = list(existing_path)
    path_start_index: int = 0
    for i, pos in enumerate(path):
        if pos in existing_set:
            start = pos
            path_start_index = i
    path = list(path[path_start_index:])
    did_something = False
    if chebyshev(current_pos, start) <= 1:
        if len(path) < 2:
            return TaskRejected.from_string(
                f"in range of {start!r} but A* path is empty"
            )
        if _lay_segment(builder, ct, start, path):
            did_something = True
    if make_move(builder, ct, start):
        did_something = True
    if not did_something:
        return TaskRejected.from_string(
            f"could neither lay at {start!r} nor move toward {target!r}"
        )
    return None


def extend_chain(builder, ct, start):
    """
    Auto-target wrapper around `extend_step`: classifies the chain's
    resource and picks the right sink. Ti -> `ti_sink`, Ax -> `ax_sink`.
    """
    if on_enemy_side(builder, start):
        return TaskRejected.from_string(
            f"{start!r} is enemy-side; deferring to OFFENSE"
        )
    resource = resource_at(builder, start)
    resource = resource
    if resource is None:
        return TaskRejected.from_string(f"cannot classify resource at {start!r}")
    if resource == ResourceType.RAW_AXIONITE:
        target = builder.ax_sink
        target = target
        if target is None:
            return TaskRejected.from_string(
                f"chain at {start!r} is Ax but ax_sink is None"
            )
        return extend_step(builder, ct, start, target, resource)
    target = builder.ti_sink if builder.ti_sink is not None else builder.my_core
    return extend_step(builder, ct, start, target, resource)
