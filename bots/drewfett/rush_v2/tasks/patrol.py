"""Fallback: revisit stale friendly infrastructure.

Navigates to the least-recently-seen tile that has friendly infrastructure
(harvesters, transport, or core). Keeps the builder's belief about its own
network fresh and detects enemy disruption.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Position
from util import INF

from ._helpers import move_toward

if TYPE_CHECKING:
    from cambc import Controller
    from state import State
    from turn import Turn


def run(state: State, ct: Controller) -> Turn | None:
    """Move toward the least recently seen friendly infrastructure tile."""
    infra: set[int] = state.my_transport | state.my_harvesters | state.my_core_tiles
    if not infra:
        return None

    w = state.w
    pos = state.pos
    best_idx: int = -1
    best_freshness: int = INF

    for i in infra:
        seen = state.last_seen[i]
        if seen < best_freshness:
            best_freshness = seen
            best_idx = i

    if best_idx < 0:
        return None

    target = Position(best_idx % w, best_idx // w)

    # Already standing on the stalest tile — nothing to do
    if target == pos:
        return None

    return move_toward(state, ct, target)
