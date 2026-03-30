"""Simulate a builder navigating from allied core to enemy core with
incremental map discovery.  Measures per-turn time for HPA* (with
incremental rebuild) and plain A* (Chebyshev heuristic) as baseline.

Each turn:
  1. Reveal tiles within builder vision (r²=20)
  2. Update belief state and dirty changed clusters
  3. Rebuild HPA* (incremental or full)
  4. Find path from current position to enemy core
  5. Move one step along path
  6. Validate path correctness against current belief

Usage:
    python -m scripts.bench_hpastar_sim [--cluster-size 7]
"""

import argparse
import heapq
import importlib.util
import sys
import time
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------
_cambc = types.ModuleType("cambc")


class _Env:
    EMPTY = 0
    WALL = 1
    ORE_TITANIUM = 2
    ORE_AXIONITE = 3


class _Pos:
    __slots__ = ("x", "y")

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __eq__(self, o: object) -> bool:
        return isinstance(o, _Pos) and self.x == o.x and self.y == o.y

    def __hash__(self) -> int:
        return hash((self.x, self.y))


_cambc.Environment = _Env  # type: ignore[attr-defined]
_cambc.Position = _Pos  # type: ignore[attr-defined]
sys.modules["cambc"] = _cambc

_util = types.ModuleType("util")
_util.Symmetry = type(  # type: ignore[attr-defined]
    "SymEnum",
    (),
    {
        "ROT": type("S", (), {"name": "ROT"})(),
        "HOR": type("S", (), {"name": "HOR"})(),
        "VER": type("S", (), {"name": "VER"})(),
    },
)()
sys.modules["util"] = _util

_v50 = str(Path(__file__).resolve().parent.parent / "bots" / "intgrah" / "v50")
if _v50 not in sys.path:
    sys.path.insert(0, _v50)

_spec = importlib.util.spec_from_file_location(
    "hpastar", Path(_v50) / "algorithms" / "hpastar.py"
)
_hmod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_hmod)  # type: ignore[union-attr]
GatewayGraph = _hmod.GatewayGraph

from hardcode.known import KnownMap  # noqa: E402
from hardcode.map import CORE_A, CORE_B, DIMENSIONS, TILES, decode  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_INF = 1_000_000
_COST_EMPTY = 10
_COST_UNSEEN = 12  # slightly penalise unseen tiles (matches bot code)
_DIR8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
_VISION_RSQ = 20  # builder vision radius squared


def _vision_offsets(rsq: int) -> list[tuple[int, int]]:
    """All (dx, dy) within squared distance rsq."""
    import math

    r = math.isqrt(rsq)
    return [
        (dx, dy)
        for dx in range(-r, r + 1)
        for dy in range(-r, r + 1)
        if dx * dx + dy * dy <= rsq
    ]


_VIS_OFFSETS = _vision_offsets(_VISION_RSQ)


# ---------------------------------------------------------------------------
# Belief state
# ---------------------------------------------------------------------------


class Belief:
    """What a single builder knows about the map."""

    __slots__ = ("env", "h", "n", "true_env", "w")

    def __init__(self, w: int, h: int, true_tiles: list[int]) -> None:
        self.w = w
        self.h = h
        self.n = w * h
        # None = unseen.  0 = empty, 1 = wall, 2 = ore_ti, 3 = ore_ax.
        self.env: list[int | None] = [None] * self.n
        self.true_env: list[int] = true_tiles

    def reveal(self, bx: int, by: int) -> list[tuple[int, int, bool]]:
        """Reveal tiles in vision from (bx, by).  Returns list of
        (x, y, passability_changed) for tiles whose cost changed."""
        w, h = self.w, self.h
        changed: list[tuple[int, int, bool]] = []
        for dx, dy in _VIS_OFFSETS:
            x, y = bx + dx, by + dy
            if 0 <= x < w and 0 <= y < h:
                i = y * w + x
                true_val = self.true_env[i]
                old_val = self.env[i]
                if old_val is None:
                    self.env[i] = true_val
                    # Unseen was treated as passable (COST_UNSEEN).
                    # Passability changes only if the true tile is a wall.
                    changed.append((x, y, true_val == 1))
                elif old_val != true_val:
                    old_pass = old_val != 1
                    new_pass = true_val != 1
                    self.env[i] = true_val
                    changed.append((x, y, old_pass != new_pass))
        return changed

    def tile_cost(self, x: int, y: int) -> int:
        i = y * self.w + x
        v = self.env[i]
        if v is None:
            return _COST_UNSEEN
        if v == 1:  # wall
            return _INF
        return _COST_EMPTY


# ---------------------------------------------------------------------------
# A* baseline (Chebyshev heuristic, on belief state)
# ---------------------------------------------------------------------------


def astar_belief(
    belief: Belief,
    sx: int,
    sy: int,
    gx: int,
    gy: int,
) -> list[int] | None:
    """A* on the belief state.  Returns tile path or None."""
    w, h = belief.w, belief.h
    si = sy * w + sx
    gi = gy * w + gx
    if si == gi:
        return [si]

    g: dict[int, int] = {si: 0}
    parent: dict[int, int | None] = {si: None}
    heap: list[tuple[int, int, int]] = [
        (max(abs(sx - gx), abs(sy - gy)) * _COST_EMPTY, 0, si)
    ]

    while heap:
        f, _, node = heapq.heappop(heap)
        if node == gi:
            path: list[int] = []
            cur: int | None = gi
            while cur is not None:
                path.append(cur)
                cur = parent.get(cur)
            path.reverse()
            return path
        g_node = g.get(node, _INF)
        if f > g_node + max(abs(node % w - gx), abs(node // w - gy)) * _COST_EMPTY:
            continue
        cx, cy = node % w, node // w
        for dx, dy in _DIR8:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h:
                c = belief.tile_cost(nx, ny)
                if c >= _INF:
                    continue
                if dx != 0 and dy != 0:
                    c += 1
                nd = g_node + c
                ni = ny * w + nx
                if nd < g.get(ni, _INF):
                    g[ni] = nd
                    parent[ni] = node
                    hv = max(abs(nx - gx), abs(ny - gy)) * _COST_EMPTY
                    heapq.heappush(heap, (nd + hv, hv, ni))

    return None


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def validate_path(
    belief: Belief, path: list[int], sx: int, sy: int, gx: int, gy: int
) -> str | None:
    """Returns error string or None if valid."""
    w = belief.w
    if not path:
        return "empty"
    if path[0] != sy * w + sx:
        return "start mismatch"
    if path[-1] != gy * w + gx:
        return "goal mismatch"
    for i in range(len(path) - 1):
        x0, y0 = path[i] % w, path[i] // w
        x1, y1 = path[i + 1] % w, path[i + 1] // w
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx > 1 or dy > 1:
            return f"non-adjacent step {i}: ({x0},{y0})->({x1},{y1})"
        c = belief.tile_cost(x1, y1)
        if c >= _INF:
            return f"impassable step {i}: ({x1},{y1})"
    return None


# ---------------------------------------------------------------------------
# Simulate one map
# ---------------------------------------------------------------------------


def simulate_map(
    km: KnownMap,
    cluster_size: int,
) -> dict | None:
    w, h = DIMENSIONS[km]
    n = w * h
    name = km.value

    env = decode(TILES[km](), n)
    true_tiles = [int(e) for e in env]

    ca, cb = CORE_A[km], CORE_B[km]
    start_x, start_y = ca.x, ca.y
    goal_x, goal_y = cb.x, cb.y

    # Check cores are passable.
    if true_tiles[start_y * w + start_x] == 1 or true_tiles[goal_y * w + goal_x] == 1:
        return None

    Belief(w, h, true_tiles)

    # -- HPA* simulation --
    hpa_belief = Belief(w, h, true_tiles)
    def cost_fn_hpa(x, y):
        return hpa_belief.tile_cost(x, y)
    gg = GatewayGraph(w, h, cost_fn_hpa, cluster_size=cluster_size)

    bx, by = start_x, start_y
    hpa_turn_times: list[float] = []
    hpa_errors: list[str] = []
    hpa_arrived = False
    max_turns = 500

    for turn in range(max_turns):
        t0 = time.perf_counter()

        # 1. Reveal vision.
        changed = hpa_belief.reveal(bx, by)

        # 2. Dirty changed clusters and rebuild.
        for cx, cy, pass_changed in changed:
            gg.invalidate_tile(cx, cy, passability_changed=pass_changed)
        # Update flat cost array for dirtied tiles.
        if changed:
            gg.rebuild_dirty(cost_fn_hpa)

        # 3. Find path.
        path = gg.find_path(bx, by, goal_x, goal_y)

        elapsed = (time.perf_counter() - t0) * 1e6
        hpa_turn_times.append(elapsed)

        # 4. Validate.
        if path is not None:
            err = validate_path(hpa_belief, path, bx, by, goal_x, goal_y)
            if err is not None:
                hpa_errors.append(f"turn {turn}: {err}")
        elif true_tiles[goal_y * w + goal_x] != 1:
            # Might be a false negative, or might just not know a route yet.
            pass

        # 5. Move one step.
        if path is not None and len(path) >= 2:
            next_tile = path[1]
            bx, by = next_tile % w, next_tile // w
            if bx == goal_x and by == goal_y:
                hpa_arrived = True
                break

    # -- A* simulation (same scenario) --
    astar_belief_state = Belief(w, h, true_tiles)
    bx, by = start_x, start_y
    astar_turn_times: list[float] = []
    astar_errors: list[str] = []
    astar_arrived = False

    for turn in range(max_turns):
        t0 = time.perf_counter()

        # 1. Reveal.
        astar_belief_state.reveal(bx, by)

        # 2. Find path (no precomputation needed).
        path = astar_belief(astar_belief_state, bx, by, goal_x, goal_y)

        elapsed = (time.perf_counter() - t0) * 1e6
        astar_turn_times.append(elapsed)

        # 3. Validate.
        if path is not None:
            err = validate_path(astar_belief_state, path, bx, by, goal_x, goal_y)
            if err is not None:
                astar_errors.append(f"turn {turn}: {err}")

        # 4. Move.
        if path is not None and len(path) >= 2:
            next_tile = path[1]
            bx, by = next_tile % w, next_tile // w
            if bx == goal_x and by == goal_y:
                astar_arrived = True
                break

    def pct(data: list[float], p: float) -> float:
        s = sorted(data)
        idx = min(int(p * len(s)), len(s) - 1)
        return s[idx]

    return {
        "map": name,
        "size": f"{w}x{h}",
        "hpa_turns": len(hpa_turn_times),
        "hpa_arrived": hpa_arrived,
        "hpa_errors": len(hpa_errors),
        "hpa_p50": round(pct(hpa_turn_times, 0.5)),
        "hpa_p95": round(pct(hpa_turn_times, 0.95)),
        "hpa_p99": round(pct(hpa_turn_times, 0.99)),
        "hpa_max": round(max(hpa_turn_times)),
        "hpa_mean": round(sum(hpa_turn_times) / len(hpa_turn_times)),
        "astar_turns": len(astar_turn_times),
        "astar_arrived": astar_arrived,
        "astar_errors": len(astar_errors),
        "astar_p50": round(pct(astar_turn_times, 0.5)),
        "astar_p95": round(pct(astar_turn_times, 0.95)),
        "astar_p99": round(pct(astar_turn_times, 0.99)),
        "astar_max": round(max(astar_turn_times)),
        "astar_mean": round(sum(astar_turn_times) / len(astar_turn_times)),
        "hpa_error_details": hpa_errors[:5],
        "astar_error_details": astar_errors[:5],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-size", type=int, default=7)
    args = parser.parse_args()

    print(
        f"{'Map':<25} {'Size':>6} "
        f"| {'HPA turns':>9} {'ok':>3} {'err':>4} "
        f"| {'HPA p50':>8} {'p95':>8} {'p99':>8} {'max':>8} {'mean':>8} "
        f"| {'A* turns':>8} {'ok':>3} {'err':>4} "
        f"| {'A* p50':>8} {'p95':>8} {'p99':>8} {'max':>8} {'mean':>8}"
    )
    print("=" * 185)

    hpa_all_max: list[int] = []
    astar_all_max: list[int] = []
    total_hpa_err = 0
    total_astar_err = 0

    for km in KnownMap:
        r = simulate_map(km, args.cluster_size)
        if r is None:
            continue

        hpa_ok = "Y" if r["hpa_arrived"] else "N"
        astar_ok = "Y" if r["astar_arrived"] else "N"
        hpa_all_max.append(r["hpa_max"])
        astar_all_max.append(r["astar_max"])
        total_hpa_err += r["hpa_errors"]
        total_astar_err += r["astar_errors"]

        print(
            f"{r['map']:<25} {r['size']:>6} "
            f"| {r['hpa_turns']:>9} {hpa_ok:>3} {r['hpa_errors']:>4} "
            f"| {r['hpa_p50']:>7}u {r['hpa_p95']:>7}u {r['hpa_p99']:>7}u {r['hpa_max']:>7}u {r['hpa_mean']:>7}u "
            f"| {r['astar_turns']:>8} {astar_ok:>3} {r['astar_errors']:>4} "
            f"| {r['astar_p50']:>7}u {r['astar_p95']:>7}u {r['astar_p99']:>7}u {r['astar_max']:>7}u {r['astar_mean']:>7}u"
        )
        if r["hpa_error_details"]:
            for e in r["hpa_error_details"]:
                print(f"  HPA ERR: {e}", file=sys.stderr)
        if r["astar_error_details"]:
            for e in r["astar_error_details"]:
                print(f"  A*  ERR: {e}", file=sys.stderr)

    print("=" * 185)
    print(f"Total HPA* errors: {total_hpa_err}   Total A* errors: {total_astar_err}")
    print(f"HPA* worst max across all maps: {max(hpa_all_max)}us")
    print(f"A*   worst max across all maps: {max(astar_all_max)}us")
    hpa_over_2ms = sum(1 for m in hpa_all_max if m > 2000)
    astar_over_2ms = sum(1 for m in astar_all_max if m > 2000)
    print(f"Maps with any turn >2ms:  HPA*={hpa_over_2ms}  A*={astar_over_2ms}")


if __name__ == "__main__":
    main()
