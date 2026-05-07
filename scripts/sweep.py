"""Streamlined head-to-head sweep: BOT_A vs BOT_B, both sides per map.

Designed to run on a remote box (hetzner / aws) over an already-built
workspace. Args are paths relative to the repo root, resolved into the
expected `target/release/lib<bot>.so` cdylib for Rust bots.

Usage:
    python3 scripts/sweep.py drewfett_v1000 v56          # Rust bots → libdrewfett_v1000.so vs libv56.so
    python3 scripts/sweep.py drewfett_v1000 v56 --workers 60
    python3 scripts/sweep.py drewfett_v1000 v56 --maps galaxy.map26,corridors.map26

Prints WR + condition breakdown + Ti-decided / Ax-decided loss split.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

LIBRE = "./target/release/cambc-libre"

WINNER_RE = re.compile(r"Winner: ([a-zA-Z0-9_]+)")
COND_RE = re.compile(r"\(([a-z_]+), turn (\d+)\)")
TI_RE = re.compile(r"Titanium\s+(\d+)\s+\((\d+)\)\s+(\d+)\s+\((\d+)\)")
AX_RE = re.compile(r"Axionite\s+(\d+)\s+\((\d+)\)\s+(\d+)\s+\((\d+)\)")


def run_one(
    bot_a_so: str, bot_b_so: str, name_a: str, name_b: str, map_path: str, seed: int
) -> dict:
    proc = subprocess.run(
        [LIBRE, "run", bot_a_so, bot_b_so, map_path, "--seed", str(seed)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = proc.stdout + proc.stderr
    w = WINNER_RE.search(out)
    cond = COND_RE.search(out)
    ti = TI_RE.search(out)
    ax = AX_RE.search(out)
    winner = w.group(1) if w else ""
    return {
        "map": Path(map_path).name,
        "name_a": name_a,
        "name_b": name_b,
        "winner": winner,
        "condition": cond.group(1) if cond else "",
        # Bracketed value is delivered (used in resources tiebreak).
        "ti_a_delivered": int(ti.group(2)) if ti else 0,
        "ti_b_delivered": int(ti.group(4)) if ti else 0,
        "ax_a_delivered": int(ax.group(2)) if ax else 0,
        "ax_b_delivered": int(ax.group(4)) if ax else 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bot_a", help="Rust bot crate name → target/release/lib<name>.so")
    ap.add_argument("bot_b", help="Rust bot crate name → target/release/lib<name>.so")
    ap.add_argument("--workers", type=int, default=60)
    ap.add_argument("--maps", help="comma-separated map names; default: all maps/")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    so_a = f"target/release/lib{args.bot_a}.so"
    so_b = f"target/release/lib{args.bot_b}.so"
    for so in (so_a, so_b):
        if not Path(so).exists():
            msg = f"missing: {so}  (run cargo build --release -p ...)"
            raise SystemExit(msg)

    if args.maps:
        maps = [
            f"maps/{m}" if not m.startswith("maps/") else m
            for m in args.maps.split(",")
        ]
    else:
        maps = sorted(str(p) for p in Path("maps").glob("*.map26"))

    jobs = []
    for m in maps:
        jobs.append((so_a, so_b, args.bot_a, args.bot_b, m, args.seed))
        jobs.append((so_b, so_a, args.bot_b, args.bot_a, m, args.seed))
    print(f"Maps: {len(maps)}  Jobs: {len(jobs)}  Workers: {args.workers}", flush=True)

    rows = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, *j) for j in jobs]
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 50 == 0 or i == len(jobs):
                el = time.perf_counter() - t0
                eta = el * (len(jobs) - i) / max(i, 1)
                print(f"  [{i}/{len(jobs)}] {el:.0f}s  ETA {eta:.0f}s", flush=True)
    print(f"Done in {time.perf_counter() - t0:.0f}s", flush=True)

    # Tally: from each row's perspective, was bot_a (the first arg) the winner?
    a_name = args.bot_a
    a_wins = sum(1 for r in rows if r["winner"] == a_name)
    b_wins = sum(1 for r in rows if r["winner"] == args.bot_b)
    total = len(rows)
    cond_count: dict[str, int] = {}
    for r in rows:
        cond_count[r["condition"]] = cond_count.get(r["condition"], 0) + 1
    print()
    print(
        f"== {a_name} vs {args.bot_b}: {a_wins}-{b_wins} (n={total}, WR={100 * a_wins / total:.1f}%) =="
    )
    print("Conditions:")
    for k, v in sorted(cond_count.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<20} {v}")

    # Resources-tiebreak loss breakdown for bot_a.
    ax_loss = ti_loss = tied = 0
    for r in rows:
        if r["condition"] != "resources" or r["winner"] != args.bot_b:
            continue
        # Was a_name on side A or B in this row?
        a_on_left = r["name_a"] == a_name
        if a_on_left:
            our_ax, their_ax = r["ax_a_delivered"], r["ax_b_delivered"]
            our_ti, their_ti = r["ti_a_delivered"], r["ti_b_delivered"]
        else:
            our_ax, their_ax = r["ax_b_delivered"], r["ax_a_delivered"]
            our_ti, their_ti = r["ti_b_delivered"], r["ti_a_delivered"]
        if their_ax > our_ax:
            ax_loss += 1
        elif their_ax == our_ax and their_ti > our_ti:
            ti_loss += 1
        else:
            tied += 1
    res_loss = ax_loss + ti_loss + tied
    if res_loss:
        print(
            f"Resources losses ({res_loss}): Ax-decided {ax_loss}, Ti-decided {ti_loss}, deeper-tiebreak {tied}"
        )


if __name__ == "__main__":
    main()
