"""Interactive map rating + linear fit for spawn-rate tuning.

Walk all official maps (default/, sprint1-4/, intl_qual/), open the
preview PNG in a viewer window, prompt for a 1-5 rating of "how many
builders should this map spawn." Save ratings to a JSON file (resumable
across runs). After rating is done (or on `q`/EOF), fit a linear model
mapping per-map features to your rating.

Features computed at post_init time (whatever Core sees on turn 0):
  - width, height, area
  - num_walls, num_ores, num_ti_ores, num_ax_ores
  - dist core->en_core (chebyshev; ground-truth used as a proxy for
    en_core_guess since the regression is offline)
  - dist core->map center (chebyshev)
  - core eccentricity (max(dx, dy) / max(w, h))
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MAPS_ROOT = Path("/home/intgrah/git/intgrah/battlecode/maps")
OFFICIAL_DIRS = ("default", "sprint1", "sprint2", "sprint3", "sprint4", "intl_qual")
RATINGS_PATH = Path("/tmp/map_spawn_ratings.json")


def _chebyshev(ax: int, ay: int, bx: int, by: int) -> int:
    dx = abs(ax - bx)
    dy = abs(ay - by)
    return max(dy, dx)


def collect_maps() -> list[tuple[str, Path, Path | None]]:
    """Return list of (map_name, map_file, preview_path_or_None)."""
    out: list[tuple[str, Path, Path | None]] = []
    for d in OFFICIAL_DIRS:
        dir_path = MAPS_ROOT / d
        if not dir_path.is_dir():
            continue
        for map_file in sorted(dir_path.glob("*.map26")):
            name = map_file.stem
            preview = dir_path / "preview" / f"{name}.png"
            out.append((name, map_file, preview if preview.exists() else None))
    return out


_CORE_VISION_R2: int = 36


def parse_map(map_file: Path) -> dict[str, float]:
    """Parse a .map26 file and extract features the Core can see at
    `post_init` time. The Core's vision is r²<=36 from its position;
    anything outside that is unknown.
    """
    sys.path.insert(0, "/home/intgrah/git/intgrah/battlecode")
    from proto.cambc_pb2 import Map

    m = Map()
    m.ParseFromString(map_file.read_bytes())
    w, h = m.width, m.height
    cores = sorted(
        [(c.team, c.position.x, c.position.y) for c in m.cores],
        key=lambda p: p[0],
    )
    if len(cores) < 2:
        return {}
    cx, cy = cores[0][1], cores[0][2]

    # Vision-restricted tile counts. r²<=36 around core (a 13x13 box
    # cropped). Includes the core's own 9 tiles.
    vis_walls = 0
    vis_ti = 0
    vis_ax = 0
    vis_passable = 0
    vis_total = 0
    nearest_ti_d2 = _CORE_VISION_R2 + 1
    nearest_ax_d2 = _CORE_VISION_R2 + 1
    nearest_wall_d2 = _CORE_VISION_R2 + 1
    for dy in range(-6, 7):
        for dx in range(-6, 7):
            d2 = dx * dx + dy * dy
            if d2 > _CORE_VISION_R2:
                continue
            x, y = cx + dx, cy + dy
            if not (0 <= x < w and 0 <= y < h):
                continue
            vis_total += 1
            t = m.rows[y].tiles[x]
            if t == 1:
                vis_walls += 1
                nearest_wall_d2 = min(nearest_wall_d2, d2)
            else:
                vis_passable += 1
                if t == 2:
                    vis_ti += 1
                    nearest_ti_d2 = min(nearest_ti_d2, d2)
                elif t == 3:
                    vis_ax += 1
                    nearest_ax_d2 = min(nearest_ax_d2, d2)

    centre_dist = _chebyshev(cx, cy, w // 2, h // 2)
    eccentricity = centre_dist / max(w, h, 1)
    edge_dist = min(cx, cy, w - 1 - cx, h - 1 - cy)
    aspect = min(w, h) / max(w, h, 1)

    # Cardinal exits from the 3x3 core: count of cardinal-adjacent
    # tiles (those at chebyshev distance 2 from the core centre, on
    # cardinals) that are passable. Range 0-4.
    cardinal_exits = 0
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        x, y = cx + dx, cy + dy
        if 0 <= x < w and 0 <= y < h and m.rows[y].tiles[x] != 1:
            cardinal_exits += 1

    # BFS from core within vision radius. Counts tiles in core's
    # connected passable component (within r²<=36) — fraction of
    # nearby passable space that's reachable.
    visited: set[tuple[int, int]] = {(cx, cy)}
    frontier: list[tuple[int, int]] = [(cx, cy)]
    while frontier:
        nxt: list[tuple[int, int]] = []
        for x, y in frontier:
            for ddx, ddy in (
                (-1, 0),
                (1, 0),
                (0, -1),
                (0, 1),
                (-1, -1),
                (-1, 1),
                (1, -1),
                (1, 1),
            ):
                nx, ny = x + ddx, y + ddy
                if (nx, ny) in visited:
                    continue
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                d2 = (nx - cx) * (nx - cx) + (ny - cy) * (ny - cy)
                if d2 > _CORE_VISION_R2:
                    continue
                if m.rows[ny].tiles[nx] == 1:
                    continue
                visited.add((nx, ny))
                nxt.append((nx, ny))
        frontier = nxt
    reach_in_vision = len(visited)

    # Inner-ring (r²<=8) vs outer-ring (8 < r²<=36) wall and ore density.
    inner_walls = 0
    inner_total = 0
    outer_walls = 0
    outer_total = 0
    near_ores = 0  # chebyshev <= 4 of core
    ore_dxs: list[int] = []
    ore_dys: list[int] = []
    for dy in range(-6, 7):
        for dx in range(-6, 7):
            d2 = dx * dx + dy * dy
            if d2 > _CORE_VISION_R2:
                continue
            x, y = cx + dx, cy + dy
            if not (0 <= x < w and 0 <= y < h):
                continue
            t = m.rows[y].tiles[x]
            if d2 <= 8:
                inner_total += 1
                if t == 1:
                    inner_walls += 1
            else:
                outer_total += 1
                if t == 1:
                    outer_walls += 1
            if t in (2, 3):
                ore_dxs.append(dx)
                ore_dys.append(dy)
                if max(abs(dx), abs(dy)) <= 4:
                    near_ores += 1

    inner_wall_density = inner_walls / max(inner_total, 1)
    outer_wall_density = outer_walls / max(outer_total, 1)

    # Angular spread of ore positions around core. Use variance of the
    # unit-vector components (atan2 alternative without trig, since
    # we just want a "are ores all on one side?" signal).
    if len(ore_dxs) >= 2:
        n = len(ore_dxs)
        mean_dx = sum(ore_dxs) / n
        mean_dy = sum(ore_dys) / n
        ore_polar_variance = (
            sum(
                (dx - mean_dx) ** 2 + (dy - mean_dy) ** 2
                for dx, dy in zip(ore_dxs, ore_dys, strict=False)
            )
            / n
        )
    else:
        ore_polar_variance = 0.0

    return {
        "w": float(w),
        "h": float(h),
        "area": float(w * h),
        "aspect": float(aspect),
        "core_to_centre": float(centre_dist),
        "eccentricity": float(eccentricity),
        "edge_dist": float(edge_dist),
        "vis_total": float(vis_total),
        "vis_walls": float(vis_walls),
        "vis_passable": float(vis_passable),
        "vis_ti_ores": float(vis_ti),
        "vis_ax_ores": float(vis_ax),
        "vis_ores": float(vis_ti + vis_ax),
        "vis_wall_density": vis_walls / max(vis_total, 1),
        "vis_ore_density": (vis_ti + vis_ax) / max(vis_total, 1),
        "nearest_ti_d2": float(nearest_ti_d2),
        "nearest_ax_d2": float(nearest_ax_d2),
        "nearest_wall_d2": float(nearest_wall_d2),
        "cardinal_exits": float(cardinal_exits),
        "reach_in_vision": float(reach_in_vision),
        "inner_wall_density": float(inner_wall_density),
        "outer_wall_density": float(outer_wall_density),
        "near_ores": float(near_ores),
        "ore_polar_variance": float(ore_polar_variance),
    }


def open_preview(path: Path) -> subprocess.Popen | None:
    return subprocess.Popen(
        ["xdg-open", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def load_ratings() -> dict[str, int]:
    if RATINGS_PATH.exists():
        return json.loads(RATINGS_PATH.read_text())
    return {}


def save_ratings(ratings: dict[str, int]) -> None:
    RATINGS_PATH.write_text(json.dumps(ratings, indent=2, sort_keys=True))


def fit(ratings: dict[str, int], features: dict[str, dict[str, float]]) -> None:
    """Linear regression: features -> rating. Print coefficients."""
    names = sorted(set(ratings) & set(features))
    if not names:
        print("no rated maps with features; skipping fit")
        return
    feat_keys = sorted(next(iter(features.values())).keys())
    n = len(names)
    p = len(feat_keys) + 1  # + bias
    # X (n x p), y (n)
    X = [[1.0] + [features[name][k] for k in feat_keys] for name in names]
    y = [float(ratings[name]) for name in names]

    # Solve normal equations: (X^T X) beta = X^T y. p is small (~12).
    XTX = [
        [sum(X[i][a] * X[i][b] for i in range(n)) for b in range(p)] for a in range(p)
    ]
    XTy = [sum(X[i][a] * y[i] for i in range(n)) for a in range(p)]
    beta = _solve(XTX, XTy)

    print()
    print(f"=== Linear fit (n={n}) ===")
    print(f"  bias: {beta[0]:+.4f}")
    for i, k in enumerate(feat_keys, start=1):
        print(f"  {k:>20s}: {beta[i]:+.6f}")

    # Print residuals.
    yhat = [sum(X[i][a] * beta[a] for a in range(p)) for i in range(n)]
    ssr = sum((y[i] - yhat[i]) ** 2 for i in range(n))
    sst = sum((y[i] - sum(y) / n) ** 2 for i in range(n))
    r2 = 1.0 - ssr / sst if sst > 0 else 0.0
    print(f"  R² = {r2:.4f}")
    print()
    print("predictions:")
    for i, name in enumerate(names):
        print(f"  {name:30s} actual={int(y[i])} predicted={yhat[i]:.2f}")


def _solve(A: list[list[float]], b: list[float]) -> list[float]:
    """Gauss-Jordan elimination. Mutates A and b."""
    n = len(A)
    for i in range(n):
        # Pivot
        max_row = i
        for k in range(i + 1, n):
            if abs(A[k][i]) > abs(A[max_row][i]):
                max_row = k
        A[i], A[max_row] = A[max_row], A[i]
        b[i], b[max_row] = b[max_row], b[i]
        if abs(A[i][i]) < 1e-12:
            return [0.0] * n
        # Normalise
        pivot = A[i][i]
        for j in range(n):
            A[i][j] /= pivot
        b[i] /= pivot
        # Eliminate
        for k in range(n):
            if k == i:
                continue
            factor = A[k][i]
            for j in range(n):
                A[k][j] -= factor * A[i][j]
            b[k] -= factor * b[i]
    return b


def main() -> None:
    maps = collect_maps()
    if not maps:
        print("no maps found")
        return
    ratings = load_ratings()
    features: dict[str, dict[str, float]] = {}
    for name, map_file, _ in maps:
        f = parse_map(map_file)
        if f:
            features[name] = f

    print(f"Found {len(maps)} maps. Already rated: {len(ratings)}.")
    print("Enter rating 1-5 (1 = spawn fewer, 5 = spawn many).")
    print(
        "Type 'q' to quit and fit, 's' to skip a map, 'b' to back up, 'f' to fit now."
    )
    print()

    viewer: subprocess.Popen | None = None
    i = 0
    while i < len(maps):
        name, map_file, preview = maps[i]
        if name in ratings:
            i += 1
            continue
        feat = features.get(name, {})
        if viewer is not None:
            viewer.terminate()
            viewer = None
        if preview is not None:
            viewer = open_preview(preview)
        sz = f"{int(feat.get('w', 0))}x{int(feat.get('h', 0))}" if feat else "?"
        print(f"[{i + 1}/{len(maps)}] {name} ({sz})")
        if preview is None:
            print("  no preview")
        try:
            line = input("  rating: ").strip().lower()
        except EOFError:
            break
        if line == "q":
            break
        if line == "s":
            i += 1
            continue
        if line == "f":
            fit(ratings, features)
            continue
        if line == "b":
            i = max(0, i - 1)
            continue
        try:
            v = int(line)
        except ValueError:
            print("  invalid input")
            continue
        if not (1 <= v <= 5):
            print("  out of range")
            continue
        ratings[name] = v
        save_ratings(ratings)
        i += 1

    if viewer is not None:
        viewer.terminate()

    fit(ratings, features)


if __name__ == "__main__":
    main()
