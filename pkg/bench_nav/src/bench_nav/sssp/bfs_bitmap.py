from bench_nav.common import INF


def build_bitmap_ctx(
    w: int, h: int, cost: list[int]
) -> tuple[int, int, int, int, int]:
    """Return (passable_mask, not_east_edge, not_west_edge, not_north_edge, not_south_edge).

    Masks prevent shift wrap-around. Tile i has bit 1 << i.
    """
    n = w * h
    passable = 0
    for i in range(n):
        if cost[i] < INF:
            passable |= 1 << i
    # not_east_edge: bit set except for tiles on the east edge (x = w-1)
    not_east = 0
    for y in range(h):
        for x in range(w):
            if x != w - 1:
                not_east |= 1 << (y * w + x)
    not_west = 0
    for y in range(h):
        for x in range(w):
            if x != 0:
                not_west |= 1 << (y * w + x)
    return passable, not_east, not_west, n, w


def bfs_bitmap(
    passable: int,
    not_east: int,
    not_west: int,
    n: int,
    w: int,
    start: int,
) -> int:
    """Level-sync 8-connected BFS using bigint bitmaps. Returns visited mask."""
    frontier = 1 << start
    visited = frontier
    while frontier:
        # Shift frontier in 8 directions, mask walls/edges, dedupe with visited.
        # North: >> w. South: << w. East: << 1 (not east edge). West: >> 1.
        e = (frontier & not_east) << 1
        w_ = (frontier & not_west) >> 1
        n_ = frontier >> w
        s_ = (frontier << w) & ((1 << n) - 1)
        ne = (n_ & not_east) << 1
        nw = (n_ & not_west) >> 1
        se = (s_ & not_east) << 1
        sw = (s_ & not_west) >> 1
        expanded = e | w_ | n_ | s_ | ne | nw | se | sw
        frontier = expanded & passable & ~visited
        visited |= frontier
    return visited
