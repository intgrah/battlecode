"""Per-turn patrol bookkeeping. Refresh `last_seen[i]` for tiles in
our own vision plus (transitively) the vision disc of one trusted
friendly builder — chosen as the farthest visible friend, since its
vision disc is maximally disjoint from ours and so contributes the
most fresh information per offset enumerated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from util.constants import MAX_WIDTH

if TYPE_CHECKING:
    from builder import Builder


def update_patrol(self: Builder) -> None:
    rnd = self.round
    last_seen = self.last_seen

    for pos in self.nearby_tiles:
        last_seen[pos.y * MAX_WIDTH + pos.x] = rnd

    friends = self.friendly_bots
    if not friends:
        return

    my_pos = self.my_pos
    mx = my_pos.x
    my = my_pos.y
    best_d = -1
    best_pos = None
    for f in friends:
        d = (f.x - mx) * (f.x - mx) + (f.y - my) * (f.y - my)
        if d > best_d or (
            d == best_d and self.rng.random() < 0.5  # random tiebreak
        ):
            best_d = d
            best_pos = f
    if best_pos is None:
        return

    fx = best_pos.x
    fy = best_pos.y
    w = self.w
    h = self.h
    base = fy * MAX_WIDTH + fx
    if 4 <= fx < w - 4 and 4 <= fy < h - 4:
        for _, _, off in self._vision_offsets:
            last_seen[base + off] = rnd
    else:
        for dx, dy, off in self._vision_offsets:
            nx = fx + dx
            ny = fy + dy
            if 0 <= nx < w and 0 <= ny < h:
                last_seen[base + off] = rnd
