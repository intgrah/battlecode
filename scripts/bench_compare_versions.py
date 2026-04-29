"""Compare per-case A* timings across two bot versions on the same captured
benchmark cases. Useful for finding cases where the previous version ran slow
and confirming the new version improves them.

Usage:
    python scripts/bench_compare_versions.py \
        --bot-old intgrah/v54.7.6 --bot-new intgrah/v54.7.9 \
        --repeats 20 --top 15

Loads cases from the same `.bench_econ_astar_cases.json` produced by
`bench_econ_astar.py`. Takes the MIN of `repeats` timings per case (eliminates
noise from GC/scheduler), then reports the worst slow cases under the old bot
and the achieved speedups.
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
from importlib import import_module
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[1]
ENGINE_SRC: Path = ROOT / "pkg" / "cambcpypy" / "src"
PROTO_SRC: Path = ROOT / "pkg" / "proto" / "src"
for site_packages in sorted((ROOT / ".venv" / "lib").glob("python*/site-packages")):
    if str(site_packages) not in sys.path:
        sys.path.insert(0, str(site_packages))
if str(PROTO_SRC) not in sys.path:
    sys.path.insert(0, str(PROTO_SRC))
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))



def _load_modules() -> tuple:
    bench_mod = import_module("bench_econ_astar")
    cambc_mod = import_module("cambc")
    engine_mod = import_module("cambcpypy.engine")
    return bench_mod, cambc_mod, engine_mod


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-old", default="intgrah/v54.7.6")
    parser.add_argument("--bot-new", default="intgrah/v54.7.9")
    parser.add_argument("--cases", type=Path, default=ROOT / ".bench_econ_astar_cases.json")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--validate-paths", action="store_true",
                        help="Require new bot to produce identical path tile sequence (default: cost-only).")
    return parser.parse_args()


def time_one(search, start, target, resource, fake_ct, repeats: int):
    """Returns (min_ns, nodes_expanded, path_tuples, path_cost)."""
    bench_mod = sys.modules["bench_econ_astar"]
    best_ns = 10**18
    last_path = None
    last_nodes = 0
    for _ in range(repeats):
        bench_mod.reset_search(search)
        t0 = time.perf_counter_ns()
        result = search.search(fake_ct, start, target, resource)
        elapsed = time.perf_counter_ns() - t0
        if result is None:
            return None, 0, None, 0
        best_ns = min(best_ns, elapsed)
        last_path = result
        last_nodes = int(getattr(search, "last_nodes_expanded", 0))
    path_tuples = [(p.x, p.y) for p in last_path] if last_path else []
    return best_ns, last_nodes, path_tuples, len(path_tuples)


def main() -> None:
    args = parse_args()
    bench_mod, _cambc_mod, engine_mod = _load_modules()

    cases = bench_mod.load_cases(args.cases)
    print(f"Loaded {len(cases)} cases from {args.cases}")


    def _runners_for(bot_name: str):
        player_cls = engine_mod._load_player_class(str(ROOT / "bots" / bot_name / "main.py"))
        astar_cls = bench_mod.resolve_astar_class(player_cls)
        return bench_mod.prepare_runners(astar_cls, cases)

    print(f"Loading {args.bot_old} (old)...")
    old_runners = _runners_for(args.bot_old)
    print(f"Loading {args.bot_new} (new)...")
    new_runners = _runners_for(args.bot_new)

    fake_ct = bench_mod.FakeController()
    gc.disable()
    try:
        results = []
        for old_r, new_r in zip(old_runners, new_runners, strict=False):
            old_ns, old_nodes, old_path, _ = time_one(
                old_r.search, old_r.start, old_r.target, old_r.resource, fake_ct, args.repeats
            )
            new_ns, new_nodes, new_path, _ = time_one(
                new_r.search, new_r.start, new_r.target, new_r.resource, fake_ct, args.repeats
            )
            if old_ns is None or new_ns is None:
                print(f"Case {old_r.case.case_id}: search returned None")
                continue
            same_path = old_path == new_path
            results.append({
                "case_id": old_r.case.case_id,
                "round": old_r.case.round,
                "old_ns": old_ns,
                "new_ns": new_ns,
                "old_nodes": old_nodes,
                "new_nodes": new_nodes,
                "speedup": old_ns / new_ns if new_ns > 0 else 0.0,
                "same_path": same_path,
                "path_len": len(old_path) if old_path else 0,
            })
    finally:
        gc.enable()

    if not results:
        print("No results")
        return

    # Aggregate.
    old_total = sum(r["old_ns"] for r in results)
    new_total = sum(r["new_ns"] for r in results)
    old_sorted = sorted(r["old_ns"] for r in results)
    new_sorted = sorted(r["new_ns"] for r in results)

    def pct(arr, p):
        idx = int((len(arr) - 1) * p)
        return arr[idx]

    print("\n=== Aggregate (min-of-repeats) ===")
    print(f"  count:        {len(results)}")
    print(f"  total old:    {old_total/1000:.1f}us")
    print(f"  total new:    {new_total/1000:.1f}us")
    print(f"  total ratio:  {old_total/new_total:.2f}x")
    print(f"  p50 old/new:  {pct(old_sorted, 0.50)/1000:.1f}us / {pct(new_sorted, 0.50)/1000:.1f}us")
    print(f"  p95 old/new:  {pct(old_sorted, 0.95)/1000:.1f}us / {pct(new_sorted, 0.95)/1000:.1f}us")
    print(f"  p99 old/new:  {pct(old_sorted, 0.99)/1000:.1f}us / {pct(new_sorted, 0.99)/1000:.1f}us")
    print(f"  max old/new:  {pct(old_sorted, 1.0)/1000:.1f}us / {pct(new_sorted, 1.0)/1000:.1f}us")

    # Top slowest cases under old version.
    by_old = sorted(results, key=lambda r: r["old_ns"], reverse=True)
    print(f"\n=== Top {args.top} slowest cases under {args.bot_old} ===")
    print(f"{'case':>5} {'rd':>4} {'plen':>5} {'old_us':>8} {'new_us':>8} {'speedup':>8} {'oldN':>5} {'newN':>5} {'samePath':>9}")
    for r in by_old[: args.top]:
        print(f"{r['case_id']:>5} {r['round']:>4} {r['path_len']:>5} "
              f"{r['old_ns']/1000:>8.1f} {r['new_ns']/1000:>8.1f} "
              f"{r['speedup']:>7.2f}x {r['old_nodes']:>5} {r['new_nodes']:>5} {r['same_path']!s:>9}")

    # Cases where speedup is worst (regressions).
    by_speedup = sorted(results, key=lambda r: r["speedup"])
    print(f"\n=== Bottom {min(5, args.top)} cases by speedup (potential regressions) ===")
    for r in by_speedup[: min(5, args.top)]:
        print(f"{r['case_id']:>5} {r['round']:>4} {r['path_len']:>5} "
              f"{r['old_ns']/1000:>8.1f} {r['new_ns']/1000:>8.1f} "
              f"{r['speedup']:>7.2f}x")


if __name__ == "__main__":
    main()
