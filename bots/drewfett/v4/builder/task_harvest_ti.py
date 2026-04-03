"""Navigate to unharvested Ti ore, building conveyors on the way back.

Two phases:
1. Walk toward ore normally (no building)
2. Once adjacent to ore and harvester placed, build conveyors back
   toward network from current position using FlowAstar

If the builder sees ore within vision range and has a FlowAstar route
cached, it builds conveyors as it walks toward the ore.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, Direction, Environment, Position
from flow_astar import FlowAstar
from marker import MarkerChainPlan, MarkerTaskClaim, TaskKind
from util import DIR4_DELTA, INF

from .action import Action, PlaceHarvester
from .helpers import cardinal_adjacent, is_claimed, move_toward_with_road
from .task_connect_excess import (
    SearchKind,
    _already_connected,
    _build_action,
    _make_goals,
)

if TYPE_CHECKING:
    from .state import State


def harvest_ti(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    pos = state.pos
    w = state.w
    unharvested = state.ore_ti - state.my_harvesters - state.en_harvesters
    if not unharvested:
        return None

    # Phase 2: we have a route — build conveyors while walking toward ore
    if state.harvest_route is not None and state.harvest_target is not None:
        if state.harvest_target in unharvested:
            result = _walk_and_build(state, ct)
            if result is not None:
                rnd = ct.get_current_round()
                state.claim = MarkerTaskClaim(
                    TaskKind.NAV_ORE, state.harvest_target, rnd
                )
                return result
        # Target gone or route failed
        state.harvest_target = None
        state.harvest_route = None

    # Immediate: already adjacent to ore → place harvester + plan route back
    for ddx, ddy in DIR4_DELTA:
        ni = (pos.y + ddy) * w + (pos.x + ddx)
        if ni in unharvested:
            ore_pos = Position(pos.x + ddx, pos.y + ddy)
            bid = ct.get_tile_building_id(ore_pos)
            if bid is not None:
                if ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                else:
                    continue
            h_cost, _ = ct.get_harvester_cost()
            ti, _ = ct.get_global_resources()
            if ti >= h_cost and ct.can_build_harvester(ore_pos):
                # Plan route from here back to network
                _plan_route_back(state, ct, pos)
                return Direction.CENTRE, PlaceHarvester(ore_pos)

    # Phase 1: pick ore and walk toward it (no building yet)
    return _pick_and_walk(state, ct, unharvested)


def _plan_route_back(state: State, ct: Controller, from_pos: Position) -> None:
    """Compute FlowAstar from current position back to network.

    Store route in state so subsequent turns build conveyors along it.
    Also drop a chain plan marker at the midpoint.
    """
    w = state.w
    goals = _make_goals(state, SearchKind.MIXED)
    if not goals:
        return

    gx = sum(g % w for g in goals) // len(goals)
    gy = sum(g // w for g in goals) // len(goals)
    search = FlowAstar(state, from_pos.x, from_pos.y, goals, 0, hx=gx, hy=gy)
    route = search.compute(lambda: ct.get_cpu_time_elapsed() < 1200)

    if route is None or len(route) < 2:
        return

    # Route goes [from_pos, ..., network]. Store for building.
    state.harvest_route = route

    # Drop chain plan at midpoint
    mid_idx = route[len(route) // 2]
    env = state.env[mid_idx]
    if env not in (
        Environment.WALL,
        Environment.ORE_TITANIUM,
        Environment.ORE_AXIONITE,
    ):
        rnd = ct.get_current_round()
        state.pending_chain_plan = MarkerChainPlan(tile_index=mid_idx, turn=rnd)


def _walk_and_build(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    """Build conveyors along harvest_route back toward network.

    Route is [builder_pos, ..., network]. Conveyors at route[k] point
    toward route[k+1] (toward network). Build from the start (near ore)
    outward toward network.
    """
    route = state.harvest_route
    if route is None:
        return None

    w = state.w
    pos = state.pos

    # Find the first unbuilt conveyor in the route
    for k in range(len(route) - 1):
        x, y = route[k] % w, route[k] // w
        nx, ny = route[k + 1] % w, route[k + 1] // w

        if _already_connected(state, route[k], x, y, nx, ny, SearchKind.MIXED):
            continue

        build_at = Position(x, y)
        action = _build_action(build_at, nx, ny, SearchKind.MIXED)

        if pos.distance_squared(build_at) <= 2:
            # Build and move toward network (forward along route)
            if k + 1 < len(route):
                move = pos.direction_to(Position(nx, ny))
            else:
                move = Direction.CENTRE
            return move, action

        # Not adjacent — walk toward build site
        return move_toward_with_road(state, ct, build_at)

    # Route fully built — done, clear state
    state.harvest_route = None
    return None


def _pick_and_walk(
    state: State,
    ct: Controller,
    unharvested: set[int],
) -> tuple[Direction, Action | None] | None:
    """Pick best ore and walk toward it. No building yet."""
    pos = state.pos
    w = state.w
    rnd = ct.get_current_round()
    infra = state.my_core_tiles | state.my_transport

    def _score(oi: int) -> int | None:
        ox, oy = oi % w, oi // w
        walk_dist = max(abs(pos.x - ox), abs(pos.y - oy))
        for ut in state.unit_tiles:
            their_dist = max(abs(ox - ut.x), abs(oy - ut.y))
            if their_dist + 3 < walk_dist:
                return None
        if infra:
            conn_dist = min(max(abs(ox - i % w), abs(oy - i // w)) for i in infra)
        else:
            conn_dist = INF
        return walk_dist + conn_dist * 2

    scored = [(s, oi) for oi in unharvested if (s := _score(oi)) is not None]
    scored.sort()

    for _, oi in scored:
        bld = state.building[oi]
        if bld is not None and bld.team != state.my_team:
            continue
        if is_claimed(state, oi, TaskKind.NAV_ORE):
            continue
        ore_pos = Position(oi % w, oi // w)
        adj = cardinal_adjacent(state, pos, ore_pos)
        if adj is None:
            continue
        result = move_toward_with_road(state, ct, adj)
        if result is None:
            continue
        move, build = result
        if move != Direction.CENTRE and build is None:
            new_pos = pos.add(move)
            if new_pos.distance_squared(ore_pos) == 1:
                bid = ct.get_tile_building_id(ore_pos)
                if bid is not None and ct.can_destroy(ore_pos):
                    ct.destroy(ore_pos)
                h_cost, _ = ct.get_harvester_cost()
                ti, _ = ct.get_global_resources()
                if ti >= h_cost:
                    build = PlaceHarvester(ore_pos)
                    _plan_route_back(state, ct, new_pos)
        state.claim = MarkerTaskClaim(TaskKind.NAV_ORE, oi, rnd)
        return move, build

    return None
