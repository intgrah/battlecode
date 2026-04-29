"""Relieve an overcapacity junction by destroying one of its immediate
friendly feeders. The removed feeder's upstream chain becomes dangling
at the old feeder tile; subsequent extend-chain tasks reroute it to a
less-saturated sink. Candidate junctions come from `congested_junctions`
(populated empirically by `update_economy_reachability`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from util.constants import MAX_WIDTH
from util.debug import debug as log
from util.metrics import chebyshev

from builder.helpers import make_move
from builder.tasks.rejected import Reason, TaskRejectedError

if TYPE_CHECKING:
    from cambc import Controller, Position

    from builder import Builder


class TaskRejectedNoCongestedJunctionError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "no congested junction in range"


class TaskRejectedNoFriendlyFeederError(TaskRejectedError):
    @override
    def reason(self) -> Reason:
        return "congested junction has no friendly feeder to remove"


class TaskRejectedCannotApproachError(TaskRejectedError):
    def __init__(self, target: Position) -> None:
        self.target = target

    @override
    def reason(self) -> Reason:
        return "cannot approach feeder {target}", {"target": self.target}


def resolve_congestion(self: Builder, ct: Controller) -> None:
    """Relieve an overcapacity junction by destroying one of its
    immediate feeders. The feeder's upstream chain becomes dangling at
    the old feeder tile; the normal extend-chain tasks then reroute it
    to an uncongested sink.
    """
    if not self.congested_junctions:
        raise TaskRejectedNoCongestedJunctionError
    log(
        "resolve_congestion: {n} congested junctions visible: {js}",
        n=len(self.congested_junctions),
        js=sorted(self.congested_junctions),
    )

    targets: list[Position] = []
    for j in self.congested_junctions:
        for feeder in self.in_edges[j.y * MAX_WIDTH + j.x]:
            fb = self.buildings[feeder.y * MAX_WIDTH + feeder.x]
            if fb is None or fb.team != self.my_team:
                continue
            targets.append(feeder)

    if not targets:
        log("resolve_congestion: no friendly feeders to remove")
        raise TaskRejectedNoFriendlyFeederError
    log(
        "resolve_congestion: {n} candidate feeders: {fs}",
        n=len(targets),
        fs=targets,
    )

    for feeder in targets:
        if ct.can_destroy(feeder):
            log("resolve_congestion: DESTROY feeder {feeder}", feeder=feeder)
            ct.destroy(feeder)
            self.apply_local_destroy(feeder)
            return

    nearest = min(targets, key=lambda p: chebyshev(self.my_pos, p))
    log("resolve_congestion: walking toward nearest feeder {feeder}", feeder=nearest)
    if make_move(self, ct, nearest):
        return
    log("resolve_congestion: could not approach {feeder}", feeder=nearest)
    raise TaskRejectedCannotApproachError(nearest)
