from __future__ import annotations

import argparse
from pathlib import Path

from bench_nav.bench import (
    DEFAULT_N_QUERIES,
    bench_mpsp,
    bench_spsp,
    bench_sssp,
    bench_stepped,
    bench_table_spsp,
    bench_table_sssp,
)
from bench_nav.types import Command


def _common(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--algos", nargs="*")
    sub.add_argument("--list", action="store_true")
    sub.add_argument("-n", "--samples", type=int, default=DEFAULT_N_QUERIES)


def _csv_arg(sub: argparse.ArgumentParser, default: str) -> None:
    sub.add_argument("csv", nargs="?", type=Path, default=Path(default))


def main() -> None:
    p = argparse.ArgumentParser(description="Navigation benchmark")
    subs = p.add_subparsers(dest="command", required=True)

    sp_spsp = subs.add_parser(Command.SPSP.name.lower())
    _common(sp_spsp)
    sp_spsp.add_argument("--waypoints", type=int, default=1)

    sp_mpsp = subs.add_parser(Command.MPSP.name.lower())
    _common(sp_mpsp)
    sp_mpsp.add_argument("--waypoints", type=int, default=1)

    sp_stepped = subs.add_parser(Command.STEPPED.name.lower())
    _common(sp_stepped)

    sp_sssp = subs.add_parser(Command.SSSP.name.lower())
    _common(sp_sssp)

    sp_table_spsp = subs.add_parser("table-spsp")
    _csv_arg(sp_table_spsp, "bench_nav_spsp.csv")

    sp_table_mpsp = subs.add_parser("table-mpsp")
    _csv_arg(sp_table_mpsp, "bench_nav_mpsp.csv")

    sp_table_sssp = subs.add_parser("table-sssp")
    _csv_arg(sp_table_sssp, "bench_nav_sssp.csv")

    args = p.parse_args()
    match args.command:
        case "spsp":
            bench_spsp(args)
        case "mpsp":
            bench_mpsp(args)
        case "stepped":
            bench_stepped(args)
        case "sssp":
            bench_sssp(args)
        case "table-spsp":
            bench_table_spsp(args)
        case "table-mpsp":
            bench_table_spsp(args)
        case "table-sssp":
            bench_table_sssp(args)


if __name__ == "__main__":
    main()
