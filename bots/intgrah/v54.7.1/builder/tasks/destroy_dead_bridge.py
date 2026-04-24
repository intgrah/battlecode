from __future__ import annotations

from typing import TYPE_CHECKING, override

from building import BuildingBridge
from util.constants import MAX_WIDTH
from util.metrics import chebyshev

from builder.helpers import make_move
from builder.tasks.rejected import TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoUnreachableDanglingError(TaskRejectedError):
    @override
    def __str__(self) -> str:
        return "no unreachable dangling"


class TaskRejectedNoBridgeUpstreamError(TaskRejectedError):
    def __init__(self, dangling: Position) -> None:
        self.dangling = dangling

    @override
    def __str__(self) -> str:
        return f"no bridge upstream of unreachable dangling {self.dangling}"


class TaskRejectedCannotActError(TaskRejectedError):
    def __init__(self, bridge: Position) -> None:
        self.bridge = bridge

    @override
    def __str__(self) -> str:
        return f"cannot destroy or approach bridge {self.bridge}"


_UPSTREAM_SEARCH_CAP = 80


def _find_upstream_bridge(self: Builder, start: Position) -> Position | None:
    """BFS backwards from `start` through `in_edges` until a friendly
    bridge is found. Returns the bridge position or None."""
    visited: set[Position] = {start}
    queue: list[Position] = [start]
    while queue and len(visited) < _UPSTREAM_SEARCH_CAP:
        cur = queue.pop()
        for u in self.in_edges[cur.y * MAX_WIDTH + cur.x]:
            if u in visited:
                continue
            visited.add(u)
            bld = self.get_building(u)
            if isinstance(bld, BuildingBridge) and bld.team == self.my_team:
                return u
            queue.append(u)
    return None


def destroy_dead_bridge(self: Builder, ct: Controller) -> None:
    if not self.unreachable_dangling:
        raise TaskRejectedNoUnreachableDanglingError
    target = min(
        self.unreachable_dangling,
        key=lambda p: (chebyshev(self.my_pos, p), p.y, p.x),
    )
    bridge = _find_upstream_bridge(self, target)
    if bridge is None:
        raise TaskRejectedNoBridgeUpstreamError(target)
    if ct.can_destroy(bridge):
        ct.destroy(bridge)
        return
    if make_move(self, ct, bridge):
        return
    raise TaskRejectedCannotActError(bridge)
