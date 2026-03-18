#!/usr/bin/env python3
"""Continuous integration runner on VPS.

Usage: python scripts/remote_ci.py [--interval 60] [--bots v29a,v29b,v25,rug]

Runs in a loop:
1. rsync bots/scripts/maps to VPS
2. Run round-robin tournament
3. Print results
4. Sleep and repeat
"""

import argparse
import subprocess
import time
from itertools import combinations

VPS = "chi"
VPS_DIR = "~/battlecode"
CAMBC = f"{VPS_DIR}/.venv/bin/cambc"
PYTHON = f"{VPS_DIR}/.venv/bin/python"
MAPS = ["maps/default_large1.map26", "maps/default_medium1.map26"]


def ssh(cmd: str, timeout: int = 120) -> str:
    r = subprocess.run(
        ["ssh", VPS, cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return r.stdout + r.stderr


def sync() -> None:
    for d in ["bots", "maps", "scripts", "proto"]:
        subprocess.run(
            ["rsync", "-a", "--delete", f"{d}/", f"{VPS}:{VPS_DIR}/{d}/"],
            capture_output=True,
        )


def run_match(a: str, b: str, map_path: str) -> str:
    replay = f"replays/{a}_vs_{b}_{map_path.rsplit('/', maxsplit=1)[-1]}.replay26"
    ssh(f"mkdir -p {VPS_DIR}/replays")
    ssh(
        f"cd {VPS_DIR} && {CAMBC} run bots/{a} bots/{b} {map_path} --replay {replay} 2>&1"
        f" | grep -v '^Completed turn\\|^Update available\\|^$'",
        timeout=300,
    )
    return ssh(
        f"cd {VPS_DIR}/scripts && {PYTHON} -m analysis ../{replay} -s summary 2>&1",
    )


def run_round(bots: list[str], maps: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {b: {"wins": 0, "losses": 0} for b in bots}
    for map_path in maps:
        for a, b in combinations(bots, 2):
            summary = run_match(a, b, map_path)
            print(f"\n--- {a} vs {b} ({map_path.split('/')[-1]}) ---")
            print(summary)
            if "Winner: Team A" in summary:
                results[a]["wins"] += 1
                results[b]["losses"] += 1
            elif "Winner: Team B" in summary:
                results[b]["wins"] += 1
                results[a]["losses"] += 1
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="Seconds between rounds (0 = run once)",
    )
    parser.add_argument(
        "--bots",
        default="v29a,v25,rug",
        help="Comma-separated bot list",
    )
    parser.add_argument(
        "--maps",
        default=",".join(MAPS),
        help="Comma-separated map list",
    )
    args = parser.parse_args()

    bots = args.bots.split(",")
    maps = args.maps.split(",")

    while True:
        print(f"\n{'=' * 60}")
        print(f"CI round at {time.strftime('%H:%M:%S')}")
        print(f"Bots: {bots}")
        print(f"{'=' * 60}")

        sync()
        results = run_round(bots, maps)

        print(f"\n{'=' * 40}")
        print("STANDINGS")
        print(f"{'=' * 40}")
        for bot in sorted(results, key=lambda b: results[b]["wins"], reverse=True):
            r = results[bot]
            print(f"  {bot:>10}: {r['wins']}W {r['losses']}L")

        if args.interval <= 0:
            break
        print(f"\nNext round in {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
