"""Standalone profiler for the BFS _bfs_compute inner loop.

Builds a synthetic padded grid (all-passable) and runs two implementations
of the BFS hot loop against it for benchmarking.

Run:
    python3 bots/adgato/bfs_test/profile_compute.py
"""

from __future__ import annotations

import time

INF = 1_000_000

W, H = 50, 50
PW = W + 2
N = PW * (H + 2)

OFFSETS = (
    -PW + 1,  # NE
    PW + 1,   # SE
    PW - 1,   # SW
    -PW - 1,  # NW
    -PW,      # N
    1,        # E
    PW,       # S
    -1,       # W
)


def build_pnb() -> tuple[list[list[int]], list[list[int]]]:
    """Build pnb tables for an all-passable interior grid."""
    pnb_push: list[list[int]] = [[]] * N
    pnb_set: list[list[int]] = [[]] * N
    ne, se, sw, nw, n, e, s, w = OFFSETS
    for ry in range(H):
        for rx in range(W):
            pi = (ry + 1) * PW + (rx + 1)
            pnb_push[pi] = [pi + ne, pi + se, pi + sw, pi + nw]
            pnb_set[pi] = [pi + n, pi + e, pi + s, pi + w]
    return pnb_push, pnb_set


def compute1(
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    dist: list[int],
    q: list[int],
    cur_idx: int,
) -> None:
    """Run backwards BFS to completion (one level past the agent)."""
    stop_at = INF
    for node in q:
        d = dist[node] + 1
        if node == cur_idx:
            stop_at = d
        if d > stop_at:
            return
        for ni in pnb_push[node]:
            if d < dist[ni]:
                dist[ni] = d
                q.append(ni)
        for ni in pnb_set[node]:
            if d < dist[ni]:
                if ni == cur_idx:
                    stop_at = d + 1
                dist[ni] = d


def compute2(
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
    dist: list[int],
    q: list[int],
    cur_idx: int,
) -> None:
    """Run backwards BFS to completion (one level past the agent)."""
    stop_at = INF
    for node in q:
        d = dist[node] + 1
        if node == cur_idx:
            stop_at = d
        if d > stop_at:
            return
        for ni in pnb_push[node]:
            if d < dist[ni]:
                dist[ni] = d
                q.append(ni)
        for ni in pnb_set[node]:
            if d < dist[ni]:
                if ni == cur_idx:
                    stop_at = d + 1
                dist[ni] = d


def fresh_state() -> tuple[list[int], list[int], int]:
    dist = [INF] * N
    gi = 1 * PW + 1
    cur_idx = H * PW + W
    dist[gi] = 0
    q = [gi]
    return dist, q, cur_idx


def run_once(
    fn: object,
    pnb_push: list[list[int]],
    pnb_set: list[list[int]],
) -> int:
    dist, q, cur_idx = fresh_state()
    fn(pnb_push, pnb_set, dist, q, cur_idx)  # type: ignore[operator]
    return dist[cur_idx]


def main() -> None:
    pnb_push, pnb_set = build_pnb()
    iters = 2000

    t0 = time.perf_counter()
    arr1 = [run_once(compute1, pnb_push, pnb_set) for _ in range(iters)]
    elapsed = time.perf_counter() - t0
    print(f"compute1: {elapsed * 1000:.3f} ms ({iters} runs on {W}x{H})")

    t0 = time.perf_counter()
    arr2 = [run_once(compute2, pnb_push, pnb_set) for _ in range(iters)]
    elapsed = time.perf_counter() - t0
    print(f"compute2: {elapsed * 1000:.3f} ms ({iters} runs on {W}x{H})")

    print("match:", arr1 == arr2)


if __name__ == "__main__":
    main()
