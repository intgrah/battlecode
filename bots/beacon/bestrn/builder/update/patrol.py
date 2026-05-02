"""
Per-turn patrol bookkeeping. Refresh `last_seen[i]` for tiles in
our own vision plus (transitively) the vision disc of one trusted
friendly builder — chosen as the farthest visible friend, since its
vision disc is maximally disjoint from ours and so contributes the
most fresh information per offset enumerated.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from builder import Builder
from util.constants import MAX_WIDTH
from util.debug import debug as log
from util.visualiser import auto_wrap_position

def update_patrol(builder):
    rnd = builder.state.round
    own_count: int = 0
    nearby = list(builder.state.nearby_tiles)
    for pos in nearby:
        builder.last_seen[int(pos.y) * 50 + int(pos.x)] = rnd
        own_count += 1
    if (not builder.state.friendly_bots):
        args = {}
        args[str("n")] = own_count
        log("patrol: refreshed {n} own-vision tiles, no friends in vision", args)
        return
    my_pos = builder.state.my_pos
    mx = my_pos.x
    my = my_pos.y
    best_key: tuple[int, int, int] = (1, 1 << 30, 1 << 30)
    best_pos = None
    friends: list[object] = list(builder.state.friendly_bots)
    for f in friends:
        d = (f.x - mx) * (f.x - mx) + (f.y - my) * (f.y - my)
        key = (-d, f.y, f.x)
        if key < best_key:
            best_key = key
            best_pos = f
    best_d = -best_key[0]
    best = best_pos
    if best is None:
        args = {}
        args[str("n")] = own_count
        log("patrol: refreshed {n} own-vision tiles, no farthest friend selected", args)
        return
    fx = best.x
    fy = best.y
    w = builder.state.width
    h = builder.state.height
    base = fy * int(50) + fx
    transitive_count: int = 0
    offsets: list[tuple[int, int, int]] = list(builder._vision_offsets)
    if (fx in range(4, w - 4)) and (fy in range(4, h - 4)):
        for _, _, off in offsets:
            builder.last_seen[int(base + off)] = rnd
            transitive_count += 1
    else:
        for dx, dy, off in offsets:
            nx = fx + dx
            ny = fy + dy
            if (nx in range(0, w)) and (ny in range(0, h)):
                builder.last_seen[int(base + off)] = rnd
                transitive_count += 1
    nf = int(len(friends))
    args = {}
    args[str("own")] = own_count
    args[str("trans")] = transitive_count
    args[str("friend")] = auto_wrap_position(best)
    args[str("d")] = best_d
    args[str("nf")] = nf
    log("patrol: refreshed own={own} + transitive={trans} via farthest friend {friend} (d²={d}, total friends={nf})", args)
