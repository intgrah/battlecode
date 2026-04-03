"""Place sentinels to defend infrastructure.

Uses approach flow analysis to score sentinel placements. Coverage
tracking prevents overlap. Diminishing returns limit total sentinels.

Does NOT handle ammo routing — FEED_TURRET handles that separately.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from building import (
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
)
from cambc import Controller, Direction, Environment, Position
from util import DIR8, DIR8_DELTA, INF, Symmetry

from .action import Action, PlaceSentinel
from .helpers import move_toward_with_road, step_off_and_build

if TYPE_CHECKING:
    from .state import State

_ATTACK_RANGE_SQ = 32
_DEFENSE_RANGE_SQ = 49


# ---------------------------------------------------------------------------
# Precomputed sentinel attack arcs per facing direction
# ---------------------------------------------------------------------------


def _precompute_arcs() -> dict[Direction, list[tuple[int, int]]]:
    arcs: dict[Direction, list[tuple[int, int]]] = {}
    for d in DIR8:
        fdx, fdy = d.delta()
        line: list[tuple[int, int]] = []
        for t in range(1, 7):
            lx, ly = t * fdx, t * fdy
            if lx * lx + ly * ly > _ATTACK_RANGE_SQ:
                break
            line.append((lx, ly))
        tiles: list[tuple[int, int]] = []
        for dx in range(-6, 7):
            for dy in range(-6, 7):
                if dx == 0 and dy == 0:
                    continue
                if dx * dx + dy * dy > _ATTACK_RANGE_SQ:
                    continue
                for lx, ly in line:
                    if max(abs(dx - lx), abs(dy - ly)) <= 1:
                        tiles.append((dx, dy))
                        break
        arcs[d] = tiles
    return arcs


SENTINEL_ARCS: dict[Direction, list[tuple[int, int]]] = _precompute_arcs()


# ---------------------------------------------------------------------------
# Enemy core candidates
# ---------------------------------------------------------------------------


def _get_enemy_core_candidates(state: State) -> list[Position]:
    if state.symmetry is not None and state.en_core_pos is not None:
        return [state.en_core_pos]
    w, h = state.w, state.h
    cx, cy = state.my_core.x, state.my_core.y
    sources: list[Position] = []
    for sym in state.sym_candidates:
        match sym:
            case Symmetry.ROT:
                sources.append(Position(w - 1 - cx, h - 1 - cy))
            case Symmetry.HOR:
                sources.append(Position(cx, h - 1 - cy))
            case Symmetry.VER:
                sources.append(Position(w - 1 - cx, cy))
    if not sources and state.en_core_pos is not None:
        sources = [state.en_core_pos]
    return sources


# ---------------------------------------------------------------------------
# Enemy distance BFS
# ---------------------------------------------------------------------------


def _compute_enemy_dist(state: State) -> list[int]:
    w, h = state.w, state.h
    n = w * h
    dist = [INF] * n

    from .state_helpers import mirror

    passable = [True] * n
    for i in range(n):
        env = state.env[i]
        if env == Environment.WALL:
            passable[i] = False
        elif env is None and state.symmetry is not None:
            mx, my = mirror(state, Position(i % w, i // w))
            mi = my * w + mx
            if state.env[mi] == Environment.WALL:
                passable[i] = False

    q: deque[int] = deque()
    sources = _get_enemy_core_candidates(state)
    for src in sources:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = src.x + dx, src.y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = ny * w + nx
                    if dist[ni] == INF:
                        dist[ni] = 0
                        q.append(ni)

    while q:
        ci = q.popleft()
        nd = dist[ci] + 1
        cx, cy = ci % w, ci // w
        for ddx, ddy in DIR8_DELTA:
            nx, ny = cx + ddx, cy + ddy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = ny * w + nx
            if dist[ni] != INF:
                continue
            if not passable[ni]:
                continue
            dist[ni] = nd
            q.append(ni)

    return dist


def _ensure_enemy_dist(state: State) -> list[int] | None:
    if state.en_core_pos is None and not state.sym_candidates:
        return None
    if state.enemy_dist is None:
        state.enemy_dist = _compute_enemy_dist(state)
    return state.enemy_dist


# ---------------------------------------------------------------------------
# Coverage tracking
# ---------------------------------------------------------------------------


def _build_coverage(state: State) -> set[int]:
    w = state.w
    covered: set[int] = set()
    for ti in state.my_turrets:
        bld = state.building[ti]
        match bld:
            case BuildingSentinel(direction=d, team=team) if team == state.my_team:
                tx, ty = ti % w, ti // w
                for dx, dy in SENTINEL_ARCS[d]:
                    nx, ny = tx + dx, ty + dy
                    if 0 <= nx < w and 0 <= ny < state.h:
                        covered.add(ny * w + nx)
            case _:
                pass
    return covered


# ---------------------------------------------------------------------------
# Sentinel placement
# ---------------------------------------------------------------------------


def _count_friendly_sentinels(state: State) -> int:
    count = 0
    for ti in state.my_turrets:
        match state.building[ti]:
            case BuildingSentinel(team=team) if team == state.my_team:
                count += 1
    return count


def _score_placement(
    state: State,
    sx: int,
    sy: int,
    facing: Direction,
    vuln: list[float],
    covered: set[int],
) -> float:
    """Score by uncovered vulnerability in arc facing the enemy approach."""
    w, h = state.w, state.h
    enemy_dist = state.enemy_dist
    si_ed = enemy_dist[sy * w + sx] if enemy_dist is not None else INF
    total = 0.0
    for dx, dy in SENTINEL_ARCS[facing]:
        nx, ny = sx + dx, sy + dy
        if not (0 <= nx < w and 0 <= ny < h):
            continue
        ni = ny * w + nx
        if ni in covered:
            continue
        if enemy_dist is not None and enemy_dist[ni] >= si_ed:
            continue
        total += vuln[ni]
    n_sentinels = _count_friendly_sentinels(state)
    return total / (n_sentinels + 1)


def _find_best_placement(
    state: State,
    vuln: list[float],
    covered: set[int],
) -> tuple[Position, Direction] | None:
    w = state.w
    cx, cy = state.my_core.x, state.my_core.y
    eg, es, eb, el = (
        state.en_gunner,
        state.en_sentinel,
        state.en_breach,
        state.en_launcher,
    )

    best: tuple[Position, Direction] | None = None
    best_score = 1.5

    f = state.flow
    seen_candidates: set[int] = set()
    for ti in state.my_transport | state.my_harvesters:
        # Only place near Ti-flowing transport or harvesters (Ti sources)
        if ti in state.my_transport and f.ti[ti] < 0.01:
            continue
        tx, ty = ti % w, ti // w
        if (cx - tx) ** 2 + (cy - ty) ** 2 > _DEFENSE_RANGE_SQ:
            continue

        for dx, dy in DIR8_DELTA:
            sx, sy = tx + dx, ty + dy
            if not state.in_bounds(sx, sy):
                continue
            si = sy * w + sx
            if si in seen_candidates:
                continue
            seen_candidates.add(si)

            if eg[si] + es[si] + eb[si] + el[si] > 0:
                continue

            env = state.env[si]
            if env in (
                Environment.WALL,
                Environment.ORE_TITANIUM,
                Environment.ORE_AXIONITE,
            ):
                continue
            sbld = state.building[si]
            match sbld:
                case None | BuildingRoad() | BuildingMarker():
                    pass
                case _:
                    continue

            for facing in DIR8:
                score = _score_placement(state, sx, sy, facing, vuln, covered)
                if score > best_score:
                    best_score = score
                    best = (Position(sx, sy), facing)

    return best


# ---------------------------------------------------------------------------
# Approach flow (for vulnerability scoring)
# ---------------------------------------------------------------------------

_DETOUR_DELTA = 10


def _compute_our_dist(state: State) -> list[int]:
    w, h = state.w, state.h
    n = w * h
    dist = [INF] * n
    cx, cy = state.my_core.x, state.my_core.y
    q: deque[int] = deque()
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                dist[ni] = 0
                q.append(ni)
    while q:
        ci = q.popleft()
        nd = dist[ci] + 1
        ccx, ccy = ci % w, ci // w
        for ddx, ddy in DIR8_DELTA:
            nx, ny = ccx + ddx, ccy + ddy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ni = ny * w + nx
            if dist[ni] != INF:
                continue
            env = state.env[ni]
            if env == Environment.WALL:
                continue
            dist[ni] = nd
            q.append(ni)
    return dist


def _compute_approach_flow(state: State, enemy_dist: list[int]) -> list[float]:
    w, h = state.w, state.h
    n = w * h
    our_dist = state.our_dist
    if our_dist is None:
        return [0.0] * n

    cx, cy = state.my_core.x, state.my_core.y
    shortest = enemy_dist[cy * w + cx]

    approach = [0.0] * n
    candidates = _get_enemy_core_candidates(state)
    seed = 1.0 / max(1, len(candidates) * 9)
    for pos in candidates:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                nx, ny = pos.x + dx, pos.y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    approach[ny * w + nx] = seed

    order = sorted(
        (i for i in range(n) if 0 <= enemy_dist[i] < INF),
        key=lambda i: enemy_dist[i],
    )
    for i in order:
        if approach[i] <= 0:
            continue
        ix, iy = i % w, i // w
        ed = enemy_dist[i]
        for dx, dy in DIR8_DELTA:
            nx, ny = ix + dx, iy + dy
            if 0 <= nx < w and 0 <= ny < h:
                ni = ny * w + nx
                if enemy_dist[ni] != ed + 1:
                    continue
                if (
                    our_dist[ni] >= INF
                    or enemy_dist[ni] + our_dist[ni] > shortest + _DETOUR_DELTA
                ):
                    continue
                approach[ni] += approach[i]

    # Normalize per distance layer
    layer_totals: dict[int, float] = {}
    for i in range(n):
        ed = enemy_dist[i]
        if ed < INF and approach[i] > 0:
            layer_totals[ed] = layer_totals.get(ed, 0.0) + approach[i]
    for i in range(n):
        ed = enemy_dist[i]
        total = layer_totals.get(ed, 0.0)
        if total > 0:
            approach[i] /= total

    return approach


def _ensure_approach_flow(state: State, enemy_dist: list[int]) -> list[float]:
    if state.approach_flow is None:
        state.approach_flow = _compute_approach_flow(state, enemy_dist)
    return state.approach_flow


# ---------------------------------------------------------------------------
# Main task
# ---------------------------------------------------------------------------


def defend_core(
    state: State,
    ct: Controller,
) -> tuple[Direction, Action | None] | None:
    s_cost, _ = ct.get_sentinel_cost()
    ti, _ = ct.get_global_resources()
    if ti < s_cost:
        return None

    enemy_dist = _ensure_enemy_dist(state)
    if enemy_dist is None:
        return None

    if state.our_dist is None:
        state.our_dist = _compute_our_dist(state)

    vuln = _ensure_approach_flow(state, enemy_dist)
    covered = _build_coverage(state)

    placement = _find_best_placement(state, vuln, covered)
    if placement is None:
        return None

    sentinel_pos, sentinel_facing = placement
    pos = state.pos

    # Place sentinel
    if pos == sentinel_pos:
        return step_off_and_build(ct, PlaceSentinel(sentinel_pos, sentinel_facing))

    if pos.distance_squared(sentinel_pos) <= 2:
        bid = ct.get_tile_building_id(sentinel_pos)
        if bid is not None and ct.can_destroy(sentinel_pos):
            ct.destroy(sentinel_pos)
        return Direction.CENTRE, PlaceSentinel(sentinel_pos, sentinel_facing)

    result = move_toward_with_road(state, ct, sentinel_pos)
    if result is None:
        return None
    move, build = result
    if move != Direction.CENTRE and build is None:
        new_pos = pos.add(move)
        if new_pos.distance_squared(sentinel_pos) <= 2 and new_pos != sentinel_pos:
            bid = ct.get_tile_building_id(sentinel_pos)
            if bid is not None and ct.can_destroy(sentinel_pos):
                ct.destroy(sentinel_pos)
            build = PlaceSentinel(sentinel_pos, sentinel_facing)
    ct.draw_indicator_line(state.pos, sentinel_pos, 0, 255, 0)
    return move, build
