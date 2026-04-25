from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import Environment, Position
from util.constants import INF, MAX_WIDTH, ROAD_COST

if TYPE_CHECKING:
    from builder import Builder

_REFLECT_BUDGET: Final = 25


def update_reflect(self: Builder) -> None:
    """Drain the reflect queue. No-op if symmetry isn't resolved yet —
    `update_vision` still enqueues new observations, they just sit until
    symmetry is known. Once resolved, `_REFLECT_BUDGET` tiles per turn
    have their mirrored env populated and the passable-neighbour /
    cost-grid / routability flags refreshed. Reflected tiles are NOT
    re-enqueued: the mirror of a mirror is the original, which by
    definition is already set.
    """
    if self.symmetry is None:
        return
    pending = self.reflect_queue
    sym = self.symmetry
    w, h = self.w, self.h
    for _ in range(min(len(pending), _REFLECT_BUDGET)):
        i = pending.popleft()
        t = Position(i % MAX_WIDTH, i // MAX_WIDTH)
        m = sym.action(t, w, h)
        mi = m.y * MAX_WIDTH + m.x
        if self.env[mi] is not None:
            continue
        env = self.env[i]
        self.env[mi] = env
        # Replicate the env-only branch of vision._update_cost: no
        # building at the reflected tile (we don't reflect buildings).
        if env == Environment.WALL:
            cost = INF
            buildable = False
        elif env == Environment.EMPTY:
            cost = ROAD_COST
            buildable = True
        else:
            cost = ROAD_COST
            buildable = False
        self.cost_grid[mi] = cost
        if self.buildable[mi] != buildable:
            self.buildable[mi] = buildable
            self.ti_routable[mi] = buildable and not self.ti_leakage[mi]
            self.ax_routable[mi] = buildable and not self.ax_leakage[mi]
        self.update_pnb(mi)
