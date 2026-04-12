from __future__ import annotations

import argparse
from pathlib import Path

from bench_nav.bench import bench_plot, bench_spsp, bench_sssp, bench_table
from bench_nav.common import N_PAIRS


def _add_common_args(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "--algos",
        nargs="*",
        help="Algorithm names to include (exact match, default: all)",
    )
    sub.add_argument(
        "--list",
        action="store_true",
        help="List available algorithms and exit",
    )
    sub.add_argument(
        "-n",
        "--samples",
        type=int,
        default=N_PAIRS,
        help=f"Number of random samples per map (default: {N_PAIRS})",
    )


def _csv_path_arg(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "csv",
        nargs="?",
        type=Path,
        default=Path("bench_nav.csv"),
        help="Path to bench_nav.csv (default: ./bench_nav.csv)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Navigation benchmark")
    subs = parser.add_subparsers(dest="command", required=True)

    sp_spsp = subs.add_parser("spsp", help="Run SPSP (point-to-point) benchmark")
    _add_common_args(sp_spsp)

    sp_sssp = subs.add_parser("sssp", help="Run SSSP (single-source) benchmark")
    _add_common_args(sp_sssp)

    sp_table = subs.add_parser("table", help="Print SPSP results as a terminal table")
    _csv_path_arg(sp_table)

    sp_plot = subs.add_parser("plot", help="Plot SPSP results to PNG")
    _csv_path_arg(sp_plot)

    args = parser.parse_args()
    match args.command:
        case "spsp":
            bench_spsp(args)
        case "sssp":
            bench_sssp(args)
        case "table":
            bench_table(args)
        case "plot":
            bench_plot(args)


if __name__ == "__main__":
    main()
