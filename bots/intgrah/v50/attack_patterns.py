"""Precomputed attack-pattern offsets for each turret type and direction.

Each pattern is a tuple of (dx, dy) offsets relative to the turret position.
Used for incremental threat-map maintenance.
"""

from __future__ import annotations

from cambc import Direction, GameConstants

_DIR_DELTA: dict[Direction, tuple[int, int]] = {
    Direction.NORTH: (0, -1),
    Direction.NORTHEAST: (1, -1),
    Direction.EAST: (1, 0),
    Direction.SOUTHEAST: (1, 1),
    Direction.SOUTH: (0, 1),
    Direction.SOUTHWEST: (-1, 1),
    Direction.WEST: (-1, 0),
    Direction.NORTHWEST: (-1, -1),
}


def _gunner_offsets(fdx: int, fdy: int) -> tuple[tuple[int, int], ...]:
    """Gunner: ray along facing direction within r²=13."""
    r_sq = GameConstants.GUNNER_VISION_RADIUS_SQ
    tiles: list[tuple[int, int]] = []
    for t in range(1, 10):
        rx, ry = fdx * t, fdy * t
        if rx * rx + ry * ry > r_sq:
            break
        tiles.append((rx, ry))
    return tuple(tiles)


def _sentinel_offsets(fdx: int, fdy: int) -> tuple[tuple[int, int], ...]:
    """Sentinel: Chebyshev distance 1 from facing ray, within r²=32."""
    r_sq = GameConstants.SENTINEL_VISION_RADIUS_SQ
    tiles: set[tuple[int, int]] = set()
    for t in range(1, 10):
        rx, ry = fdx * t, fdy * t
        if rx * rx + ry * ry > r_sq:
            break
        for dx2 in range(-1, 2):
            for dy2 in range(-1, 2):
                nx, ny = rx + dx2, ry + dy2
                if nx * nx + ny * ny <= r_sq and (nx, ny) != (0, 0):
                    tiles.add((nx, ny))
    return tuple(sorted(tiles))


def _breach_offsets(fdx: int, fdy: int) -> tuple[tuple[int, int], ...]:
    """Breach: 180 degree cone (dot product >= 0) within r²=5."""
    r_sq = GameConstants.BREACH_ATTACK_RADIUS_SQ
    tiles: list[tuple[int, int]] = []
    r = 3
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if (dx, dy) == (0, 0):
                continue
            if dx * dx + dy * dy > r_sq:
                continue
            if dx * fdx + dy * fdy >= 0:
                tiles.append((dx, dy))
    return tuple(sorted(tiles))


def _launcher_offsets() -> tuple[tuple[int, int], ...]:
    """Launcher: picks up adjacent bots (Chebyshev distance 1)."""
    return tuple(
        (dx, dy) for dx in range(-1, 2) for dy in range(-1, 2) if (dx, dy) != (0, 0)
    )


def _build_patterns() -> (
    tuple[
        dict[Direction, tuple[tuple[int, int], ...]],
        dict[Direction, tuple[tuple[int, int], ...]],
        dict[Direction, tuple[tuple[int, int], ...]],
        tuple[tuple[int, int], ...],
    ]
):
    gunner: dict[Direction, tuple[tuple[int, int], ...]] = {}
    sentinel: dict[Direction, tuple[tuple[int, int], ...]] = {}
    breach: dict[Direction, tuple[tuple[int, int], ...]] = {}
    for d, (fdx, fdy) in _DIR_DELTA.items():
        gunner[d] = _gunner_offsets(fdx, fdy)
        sentinel[d] = _sentinel_offsets(fdx, fdy)
        breach[d] = _breach_offsets(fdx, fdy)
    return gunner, sentinel, breach, _launcher_offsets()


GUNNER_OFFSETS, SENTINEL_OFFSETS, BREACH_OFFSETS, LAUNCHER_OFFSETS = _build_patterns()
