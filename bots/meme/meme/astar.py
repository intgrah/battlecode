import heapq

_CARDINALS: tuple[tuple[int, int], ...] = ((0, 1), (0, -1), (1, 0), (-1, 0))
_DIAGONALS: tuple[tuple[int, int], ...] = ((2, 2), (2, -2), (-2, 2), (-2, -2))
_DIAGONAL_BONUS: int = 20


def run(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]]:
    """Return the lowest-cost path from start to goal.

    Grid is indexed grid[y][x]. Walls (env=1) cost 100; all other tiles cost 1.
    Returns an empty list if no path exists or start == goal.
    """
    if start == goal:
        return []

    h = len(grid)
    w = len(grid[0]) if h else 0

    def cost(x: int, y: int) -> int:
        row = grid[y] if y < len(grid) else []
        return 100 if (x < len(row) and row[x] == 1) else 1

    def heuristic(x: int, y: int) -> int:
        return abs(x - goal[0]) + abs(y - goal[1])

    sx, sy = start

    open_heap: list[tuple[int, int, int, int, int, int]] = [
        (heuristic(sx, sy), 0, sx, sy, -1, -1)
    ]
    best_g: dict[tuple[int, int], int] = {start: 0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}

    while open_heap:
        _f, g, x, y, px, py = heapq.heappop(open_heap)

        if g > best_g.get((x, y), g + 1):
            continue

        if (px, py) != (-1, -1):
            came_from[(x, y)] = (px, py)

        if (x, y) == goal:
            path: list[tuple[int, int]] = []
            cur: tuple[int, int] = (x, y)
            while cur != start:
                path.append(cur)
                cur = came_from[cur]
            path.append(start)
            path.reverse()
            return path

        for dx, dy in _CARDINALS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ng = g + cost(nx, ny)
            if ng < best_g.get((nx, ny), ng + 1):
                best_g[(nx, ny)] = ng
                heapq.heappush(open_heap, (ng + heuristic(nx, ny), ng, nx, ny, x, y))

        for dx, dy in _DIAGONALS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            ng = g + cost(nx, ny) + _DIAGONAL_BONUS
            if ng < best_g.get((nx, ny), ng + 1):
                best_g[(nx, ny)] = ng
                heapq.heappush(open_heap, (ng + heuristic(nx, ny), ng, nx, ny, x, y))

    return []
