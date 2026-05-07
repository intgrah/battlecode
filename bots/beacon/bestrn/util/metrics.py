"""Translation of `bots/intgrah/v54.7.9/util/metrics.py`."""

from __future__ import annotations


def manhattan(p1, p2):
    """L-1 distance."""
    return abs(p1.x - p2.x) + abs(p1.y - p2.y)


def euclidean_sq(p1, p2):
    """L-2 distance, squared."""
    dx = p1.x - p2.x
    dy = p1.y - p2.y
    return dx * dx + dy * dy


def chebyshev(p1, p2):
    """L-infinity distance."""
    dx = abs(p1.x - p2.x)
    dy = abs(p1.y - p2.y)
    return max(dy, dx)


def reachable_path_end(path, current_pos, max_range):
    """
    Walk `path` from the end and return the furthest position whose squared
    distance from `current_pos` is `<= max_range^2`. Falls back to
    `current_pos` if every path position is out of range.
    """
    limit = max_range * max_range
    for pos in reversed(path):
        if euclidean_sq(current_pos, pos) <= limit:
            return pos
    return current_pos


def closest(target, positions):
    """
    Returns the position in `positions` closest to `target` (by squared
    Euclidean distance). `None` for an empty iterator. Distance ties are
    broken by `(y, x)` lex order so the result is deterministic
    regardless of the iterator's source ordering.
    """
    return (
        min(positions, key=lambda p: (euclidean_sq(target, p), p.y, p.x))
        if positions
        else None
    )


def claims_by_proximity(my_pos, my_id, target, friendlies) -> bool:
    """
    Returns `true` iff `my_id` at `my_pos` is the rightful claimant of `target`
    over all `friendlies` (by Chebyshev distance, with smaller id as tiebreak).

    `friendlies` should be an iterator of `(position, id)` pairs for OTHER
    friendly builders. See the Python source for the full reasoning.
    """
    my_d = chebyshev(my_pos, target)
    for fb_pos, fb_id in friendlies:
        fb_d = chebyshev(fb_pos, target)
        if fb_d < my_d or (fb_d == my_d and fb_id < my_id):
            return False
    return True
