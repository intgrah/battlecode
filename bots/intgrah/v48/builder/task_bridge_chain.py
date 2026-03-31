"""Greedy bridge chain builder, modeled on trollbot_expand's _bridge().

Finds harvesters with excess (disconnected from core), then greedily
builds a bridge chain from harvester toward core by scanning r²≤9 tiles
and picking the best target closest to core. Builder follows the chain
tip, building bridges one hop at a time.
"""

from building import (
    BuildingBarrier,
    BuildingBridge,
    BuildingCore,
    BuildingLauncher,
    BuildingMarker,
    BuildingRoad,
)
from cambc import Controller, Direction, Environment, Position
from util import DIR4_DELTA, DIR8_DELTA, INF

from .build import Action, PlaceBridge, PlaceLauncher
from .helpers import move_toward_with_road
from .state import State

BRIDGE_RANGE_SQ = 9


def _find_disconnected_harvester(state: State) -> Position | None:
    """Find nearest harvester with excess flow (not connected to core)."""
    pos = state.pos
    best: Position | None = None
    best_dist = INF
    for p in state.my_harvesters:
        i = state.idx(p.x, p.y)
        if state.my_flow.excess[i] < 0.01:
            continue
        dist = abs(pos.x - p.x) + abs(pos.y - p.y)
        if dist < best_dist:
            best_dist = dist
            best = p
    return best


def _pick_bridge_start(state: State, harvester: Position) -> Position | None:
    """Pick the best cardinal-adjacent tile to start a bridge chain.
    Prefers the side closest to core.
    """
    cx, cy = state.my_core
    best: Position | None = None
    best_dist = INF
    for dx, dy in DIR4_DELTA:
        nx, ny = harvester.x + dx, harvester.y + dy
        if not state.in_bounds(nx, ny):
            continue
        ni = state.idx(nx, ny)
        env = state.env[ni]
        if env in (
            Environment.WALL,
            Environment.ORE_TITANIUM,
            Environment.ORE_AXIONITE,
        ):
            continue
        bld = state.building[ni]
        match bld:
            case None | BuildingRoad() | BuildingBarrier() | BuildingMarker():
                pass
            case BuildingBridge(team=team) if team == state.my_team:
                pass  # Existing bridge is fine as start
            case _:
                continue
        dist = abs(nx - cx) + abs(ny - cy)
        if dist < best_dist:
            best_dist = dist
            best = Position(nx, ny)
    return best


def _is_buildable(state: State, x: int, y: int) -> bool:
    if not state.in_bounds(x, y):
        return False
    i = state.idx(x, y)
    env = state.env[i]
    if env is None:
        return False
    if env in (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
        return False
    bld = state.building[i]
    match bld:
        case None | BuildingRoad() | BuildingBarrier() | BuildingMarker():
            return True
    return False


def _chebyshev(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def _has_launcher_adjacent(state: State, pos: Position) -> bool:
    for dx, dy in DIR8_DELTA:
        nx, ny = pos.x + dx, pos.y + dy
        if not state.in_bounds(nx, ny):
            continue
        ni = state.idx(nx, ny)
        bld = state.building[ni]
        if isinstance(bld, BuildingLauncher) and bld.team == state.my_team:
            return True
    return False


def bridge_chain(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    """Build bridge chain from disconnected harvester to core, greedy style."""
    harvester = _find_disconnected_harvester(state)
    if harvester is None:
        return None

    start = _pick_bridge_start(state, harvester)
    if start is None:
        return None

    # Follow existing bridge chain to find the tip
    chain_tip = start
    visited: set[Position] = {start}
    goal_tiles = state.my_econ_targets or state.my_core_tiles
    core = state.my_core

    for _ in range(50):
        i = state.idx(chain_tip.x, chain_tip.y)
        bld = state.building[i]
        match bld:
            case BuildingBridge(team=team, target=bt) if team == state.my_team:
                target_pos = Position(bt.x, bt.y)
                if target_pos in visited:
                    break
                visited.add(target_pos)
                if target_pos in goal_tiles:
                    return None  # Chain complete!
                chain_tip = target_pos
            case _:
                break

    pos = state.pos
    ti_i = state.idx(chain_tip.x, chain_tip.y)
    tip_bld = state.building[ti_i]
    match tip_bld:
        case BuildingCore(team=team) if team == state.my_team:
            return None

    # Opportunistic launcher: if we're near a bridge without launcher, place one
    if pos.distance_squared(chain_tip) <= 8:
        for bp in visited:
            bi = state.idx(bp.x, bp.y)
            bbld = state.building[bi]
            if not isinstance(bbld, BuildingBridge) or bbld.team != state.my_team:
                continue
            if _has_launcher_adjacent(state, bp):
                continue
            for dx, dy in DIR8_DELTA:
                adj = Position(bp.x + dx, bp.y + dy)
                if ct.can_build_launcher(adj):
                    return Direction.CENTRE, PlaceLauncher(adj)
            break  # Only try first undefended bridge

    # Navigate to chain_tip if not adjacent
    if pos.distance_squared(chain_tip) > 2:
        move, build = move_toward_with_road(state, ct, chain_tip)
        state.debug_target = (chain_tip, 0, 128, 255)
        return move, build

    # At chain_tip: scan r²≤9 for best bridge target
    core_target: Position | None = None
    bridge_candidates: list[tuple[int, Position]] = []
    empty_candidates: list[tuple[int, Position]] = []

    for dx in range(-3, 4):
        for dy in range(-3, 4):
            tx, ty = chain_tip.x + dx, chain_tip.y + dy
            dsq = dx * dx + dy * dy
            if dsq > BRIDGE_RANGE_SQ or dsq == 0:
                continue
            if not state.in_bounds(tx, ty):
                continue
            t = Position(tx, ty)
            ti = state.idx(tx, ty)
            bld = state.building[ti]

            if t in goal_tiles:
                core_target = t
                continue

            match bld:
                case BuildingBridge(team=team) if team == state.my_team:
                    d = _chebyshev(t, core)
                    if d < _chebyshev(chain_tip, core):
                        bridge_candidates.append((d, t))
                    continue

            if _is_buildable(state, tx, ty):
                d = _chebyshev(t, core)
                empty_candidates.append((d, t))

    # Destroy building on chain_tip to place bridge
    bid = ct.get_tile_building_id(chain_tip)
    if bid is not None and ct.can_destroy(chain_tip):
        ct.destroy(chain_tip)

    # Priority 1: bridge directly to core
    if core_target is not None and ct.can_build_bridge(chain_tip, core_target):
        state.debug_target = (core_target, 0, 255, 0)
        return Direction.CENTRE, PlaceBridge(chain_tip, core_target)

    # Priority 2: bridge to existing friendly bridge closer to core
    bridge_candidates.sort()
    for _, target in bridge_candidates:
        if ct.can_build_bridge(chain_tip, target):
            state.debug_target = (target, 0, 200, 255)
            return Direction.CENTRE, PlaceBridge(chain_tip, target)

    # Priority 3: bridge to closest empty tile to core, then navigate there
    empty_candidates.sort()
    for _, target in empty_candidates:
        if ct.can_build_bridge(chain_tip, target):
            state.debug_target = (target, 0, 128, 255)
            return Direction.CENTRE, PlaceBridge(chain_tip, target)

    # Can't build — move closer
    move, build = move_toward_with_road(state, ct, chain_tip)
    state.debug_target = (chain_tip, 128, 128, 255)
    return move, build
