"""Shared helpers for astar_test bot."""

from __future__ import annotations

from cambc import Controller, Direction, Position


def in_bounds(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def try_move_smart(ct: Controller, pos: Position, direction: Direction) -> bool:
    """Move in direction. Uses existing walkable tile if possible, else builds road."""
    if direction == Direction.CENTRE:
        return True

    target = pos.add(direction)
    if not in_bounds(ct, target):
        return False

    if ct.can_move(direction):
        ct.move(direction)
        return True
    if ct.can_build_road(target):
        ct.build_road(target)
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False
