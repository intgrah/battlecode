from action import ActionOnly, MoveAction, MoveOnly, PlaceBarrier, Turn
from cambc import Controller, Environment, Position
from util import DIR4_DELTA

from .helpers import move_toward_with_road, nearest_reachable_around
from .state import State

_IMPASSABLE_ENV = frozenset(
    (Environment.WALL, Environment.ORE_TITANIUM, Environment.ORE_AXIONITE),
)


def _find_exposed_harvesters(state: State) -> list[tuple[int, list[int]]]:
    w = state.w
    results: list[tuple[int, list[int]]] = []
    for hi in state.my_harvesters:
        hx, hy = hi % w, hi // w
        exposed: list[int] = []
        for dx, dy in DIR4_DELTA:
            nx, ny = hx + dx, hy + dy
            if not state.in_bounds(nx, ny):
                continue
            ni = ny * w + nx
            if state.building[ni] is not None:
                continue
            env = state.env[ni]
            if env is not None and env in _IMPASSABLE_ENV:
                continue
            exposed.append(ni)
        if exposed:
            results.append((hi, exposed))
    return results


def barrier_harvester(
    state: State,
    ct: Controller,
) -> Turn | None:
    w = state.w
    candidates = _find_exposed_harvesters(state)
    if not candidates:
        return None

    candidates.sort(key=lambda x: (-len(x[1]), x[0]))

    pos = state.pos
    for _, exposed in candidates:
        for ni in exposed:
            nx, ny = ni % w, ni // w
            target = Position(nx, ny)

            if pos.distance_squared(target) <= 2:
                b_cost, _ = ct.get_barrier_cost()
                ti, _ = ct.get_global_resources()
                if ti >= b_cost and ct.can_build_barrier(target):
                    print(f"    barrier_harvester: place at ({nx},{ny})")
                    return ActionOnly(PlaceBarrier(target))
                continue

            adj = nearest_reachable_around(state, target)
            if adj is None:
                continue
            result = move_toward_with_road(state, ct, adj)
            if result is None:
                continue
            match result:
                case MoveOnly(move):
                    new_pos = pos.add(move)
                    if new_pos.distance_squared(target) <= 2:
                        b_cost, _ = ct.get_barrier_cost()
                        ti, _ = ct.get_global_resources()
                        if ti >= b_cost:
                            result = MoveAction(move, PlaceBarrier(target))
            print(f"    barrier_harvester: nav to ({nx},{ny})")
            ct.draw_indicator_dot(target, 128, 128, 128)
            return result

    return None
