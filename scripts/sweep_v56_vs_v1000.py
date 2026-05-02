"""Sweep v56 (rust) vs drewfett/v1000 (rust) — both sides per map, parallel on hetzner.

Output: /tmp/sweep_v56_v1000.csv
"""
from __future__ import annotations

import csv
import re
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

V56 = "target/release/libv56.so"
V1000 = "target/release/libdrewfett_v1000.so"
LIBRE = "./target/release/cambc-libre"
N_WORKERS = 28

WINNER_RE = re.compile(r"Winner: ([a-zA-Z0-9_]+)")
COND_RE = re.compile(r"\(([a-z_]+), turn (\d+)\)")
TI_RE = re.compile(r"Titanium\s+(\d+)\s+\((\d+)\)\s+(\d+)\s+\((\d+)\)")
AX_RE = re.compile(r"Axionite\s+(\d+)\s+\((\d+)\)\s+(\d+)\s+\((\d+)\)")
UNITS_RE = re.compile(r"Units\s+(\d+)\s+(\d+)")
BLD_RE = re.compile(r"Buildings\s+(\d+)\s+(\d+)")


@dataclass
class Job:
    map_path: str
    seed: int
    side: str
    bot_a_path: str
    bot_b_path: str
    bot_a_name: str
    bot_b_name: str


def run_match(job: Job) -> dict:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [LIBRE, "run", job.bot_a_path, job.bot_b_path, job.map_path, "--seed", str(job.seed)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    wall = time.perf_counter() - t0
    out = proc.stdout + proc.stderr
    w = WINNER_RE.search(out)
    cond = COND_RE.search(out)
    ti = TI_RE.search(out)
    ax = AX_RE.search(out)
    units = UNITS_RE.search(out)
    bld = BLD_RE.search(out)
    return {
        "map": Path(job.map_path).name,
        "seed": job.seed,
        "side": job.side,
        "bot_a": job.bot_a_name,
        "bot_b": job.bot_b_name,
        "winner": w.group(1) if w else "",
        "condition": cond.group(1) if cond else "",
        "turns": int(cond.group(2)) if cond else 0,
        "ti_a": int(ti.group(1)) if ti else 0,
        "ti_a_mined": int(ti.group(2)) if ti else 0,
        "ti_b": int(ti.group(3)) if ti else 0,
        "ti_b_mined": int(ti.group(4)) if ti else 0,
        "units_a": int(units.group(1)) if units else 0,
        "units_b": int(units.group(2)) if units else 0,
        "buildings_a": int(bld.group(1)) if bld else 0,
        "buildings_b": int(bld.group(2)) if bld else 0,
        "wall_time_s": round(wall, 2),
    }


def main() -> None:
    maps = sorted(Path("maps").glob("*.map26"))
    jobs: list[Job] = []
    for m in maps:
        for s in [1]:
            jobs.append(Job(str(m), s, "v56A", V56, V1000, "v56", "v1000"))
            jobs.append(Job(str(m), s, "v56B", V1000, V56, "v1000", "v56"))
    print(f"Maps: {len(maps)}  Jobs: {len(jobs)}", flush=True)

    out_path = Path("/tmp/sweep_v56_v1000.csv")
    fields = [
        "map", "seed", "side", "bot_a", "bot_b", "winner", "condition", "turns",
        "ti_a", "ti_a_mined", "ti_b", "ti_b_mined",
        "units_a", "units_b", "buildings_a", "buildings_b", "wall_time_s",
    ]
    completed = 0
    t_start = time.perf_counter()
    with out_path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        with ProcessPoolExecutor(max_workers=N_WORKERS) as pool:
            futures = {pool.submit(run_match, j): j for j in jobs}
            for fut in as_completed(futures):
                row = fut.result()
                writer.writerow(row)
                f.flush()
                completed += 1
                if completed % 50 == 0 or completed == len(jobs):
                    elapsed = time.perf_counter() - t_start
                    eta = elapsed / completed * (len(jobs) - completed)
                    print(f"[{completed}/{len(jobs)}] {elapsed:.0f}s elapsed, ETA {eta:.0f}s", flush=True)
    print(f"\nDone in {time.perf_counter() - t_start:.0f}s. Rows: {completed}")


if __name__ == "__main__":
    main()
