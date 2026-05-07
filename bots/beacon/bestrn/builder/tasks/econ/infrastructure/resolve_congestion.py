"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/econ/infrastructure/resolve_congestion.py`.

Relieve an overcapacity junction by destroying one of its immediate
friendly feeders. The removed feeder's upstream chain becomes dangling
at the old feeder tile; subsequent extend-chain tasks reroute it to a
less-saturated sink. Candidate junctions come from `congested_junctions`
(populated empirically by `update_economy_reachability`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Position
from util.debug import debug as log
from util.metrics import chebyshev

from builder.helpers import make_move
from builder.tasks.rejected import TaskRejected


def resolve_congestion(self_, ct):
    if not self_.congested_junctions:
        return TaskRejected("no congested junction in range")
    log(
        f"resolve_congestion: {len(self_.congested_junctions)} congested junctions visible",
        {},
    )
    junctions: list[Position] = list(self_.congested_junctions)
    junctions.sort(key=lambda p: (p.y, p.x))
    targets: list[Position] = []
    for j in junctions:
        for feeder in self_.in_edges[int(j.y) * 50 + int(j.x)]:
            fi = int(feeder.y) * 50 + int(feeder.x)
            if self_.building_kind[fi] is None:
                continue
            if self_.building_team[fi] != self_.my_team:
                continue
            targets.append(feeder)
    targets.sort(key=lambda p: (p.y, p.x))
    targets.__setitem__(
        slice(None),
        [__x for __i, __x in enumerate(targets) if __i == 0 or __x != targets[__i - 1]],
    )
    if not targets:
        log("resolve_congestion: no friendly feeders to remove", {})
        return TaskRejected("congested junction has no friendly feeder to remove")
    log(f"resolve_congestion: {len(targets)} candidate feeders", {})
    for feeder in targets:
        if ct.can_destroy(feeder):
            log(f"resolve_congestion: DESTROY feeder {feeder!r}", {})
            ct.destroy(feeder)
            self_.apply_local_destroy(feeder)
            return None
    my_pos = self_.my_pos
    nearest = (
        min(targets, key=lambda p: (chebyshev(my_pos, p), p.y, p.x))
        if targets
        else None
    )
    log(f"resolve_congestion: walking toward nearest feeder {nearest!r}", {})
    if make_move(self_, ct, nearest):
        return None
    log(f"resolve_congestion: could not approach {nearest!r}", {})
    return TaskRejected.from_string(f"cannot approach feeder {nearest!r}")
