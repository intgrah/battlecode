from __future__ import annotations

from typing import Final

from cambc import Environment, Position

_REFLECT_BUDGET: Final[int] = 25


def update_reflect(builder) -> None:
    """
    Drain the reflect queue. No-op if symmetry isn't resolved yet —
    `update_vision` still enqueues new observations, they just sit until
    symmetry is known. Once resolved, `_REFLECT_BUDGET` tiles per turn
    have their mirrored env populated and the passable-neighbour /
    cost-grid / routability flags refreshed. Reflected tiles are NOT
    re-enqueued: the mirror of a mirror is the original, which by
    definition is already set.
    """
    sym = builder.symmetry
    if sym is None:
        return
    w = builder.state.width
    h = builder.state.height
    n = min(len(builder.reflect_queue), 25)
    for _ in range(n):
        i = builder.reflect_queue.pop(0) if builder.reflect_queue else None
        t = Position(x=int(i % 50), y=int(i // 50))
        m = sym.action(t, w, h)
        mi = int(m.y) * 50 + int(m.x)
        if builder.env[mi] is not None:
            continue
        env = builder.env[i]
        builder.env[mi] = env
        match env:
            case Environment.WALL:
                cost, buildable = (1000000, False)
            case Environment.EMPTY:
                cost, buildable = (3, True)
            case _:
                cost, buildable = (3, False)
        builder.cost_grid[mi] = cost
        if builder.buildable[mi] != buildable:
            builder.buildable[mi] = buildable
            builder.ti_routable[mi] = buildable and not builder.ti_leakage[mi]
            builder.ax_routable[mi] = buildable and not builder.ax_leakage[mi]
        builder.update_pnb(mi)
