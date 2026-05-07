"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/destroy_dead_bridge.py`.

Tear down a friendly bridge whose downstream chain has become
unreachable. BFS upstream from each `unreachable_dangling` tile through
`in_edges` to find a friendly bridge; if found and within range, destroy
it (freeing the Ti scaling) so the upstream chain can be re-routed by the
extend-chain tasks. Otherwise approach the bridge.
"""

from __future__ import annotations

from typing import Final

from cambc import EntityType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller, ControllerApi, Position
if TYPE_CHECKING:
    from builder import Builder
from builder.helpers import make_move
from builder.tasks.rejected import TaskRejected

if TYPE_CHECKING:
    from builder.tasks.rejected import TaskResult
from util.constants import MAX_WIDTH
from util.metrics import chebyshev

UPSTREAM_SEARCH_CAP: Final[int] = 80


def find_upstream_bridge(self_, start):
    """
    BFS backwards from `start` through `in_edges` until a friendly
    bridge is found. Returns the bridge position or None.
    """
    visited: set[Position] = set()
    visited.add(start)
    queue: list[Position] = [start]
    while (cur := (queue.pop() if queue else None)) is not None:
        if len(visited) >= 80:
            break
        for u in self_.in_edges[int(cur.y) * 50 + int(cur.x)]:
            if u in visited:
                continue
            visited.add(u)
            if (
                self_.building_kind[self_.idx(u)] == EntityType.BRIDGE
                and self_.building_team[self_.idx(u)] == self_.my_team
            ):
                return u
            queue.append(u)
    return None


def destroy_dead_bridge(self_, ct):
    if not self_.unreachable_dangling:
        return TaskRejected("no unreachable dangling")
    my_pos = self_.my_pos
    target = (
        min(self_.unreachable_dangling, key=lambda p: (chebyshev(my_pos, p), p.y, p.x))
        if self_.unreachable_dangling
        else None
    )
    bridge = find_upstream_bridge(self_, target)
    if bridge is None:
        return TaskRejected.from_string(
            f"no bridge upstream of unreachable dangling {target!r}"
        )
    if ct.can_destroy(bridge):
        ct.destroy(bridge)
        self_.apply_local_destroy(bridge)
        return None
    if make_move(self_, ct, bridge):
        return None
    return TaskRejected.from_string(f"cannot destroy or approach bridge {bridge!r}")
