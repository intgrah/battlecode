"""Run many trials of v54.6.0 vs nothing/2000 on a map with different SOLVER_SEED
values; pick the seed whose replay completes the blueprint earliest.

Usage:
    uv run --no-project python scripts/solve_blueprint.py <map> [-n trials] [-j workers]

Writes the best seed to pkg/blueprint/books/<map>.seed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS_DIR = ROOT / "pkg" / "blueprint" / "books"

# Add the project packages to sys.path. Order matters: the blueprint package
# at pkg/blueprint/src must win over the single-file blueprint.py in the bot
# directory. We add proto + hardcode-bearing bot first, then the blueprint
# package LAST so it's at the *front* of sys.path after the insertions.
for sub in ("bots/intgrah/v54.6.0", "pkg/proto/src", "pkg/blueprint/src"):
    sys.path.insert(0, str(ROOT / sub))

from blueprint.known import KnownMap  # noqa: E402
from hardcode.blueprints._generated import (
    BLUEPRINTS,  # type: ignore[import-not-found]
)
from proto import cambc_pb2  # type: ignore[attr-defined]  # noqa: E402


def earliest_complete_turn(
    replay_path: Path, expected: set[tuple[int, int, int]]
) -> int | None:
    """Scan replay; return earliest turn index at which `expected` ⊆ team-A placed buildings.

    Expected entries are `(x, y, entity_type_int)`.
    """
    replay = cambc_pb2.Replay()
    replay.ParseFromString(replay_path.read_bytes())
    placed: set[tuple[int, int, int]] = set()
    # Map Entity oneof to our expected ints (Entity.kind enum number in blueprint)
    for turn_idx, turn in enumerate(replay.turns):
        for upd in turn.updates:
            if upd.WhichOneof("kind") != "place_entity":
                continue
            e = upd.place_entity.entity
            if e.team != 0:  # team A only
                continue
            kind = _entity_type(e)
            if kind is None:
                continue
            placed.add((e.position.x, e.position.y, kind))
            if expected.issubset(placed):
                return turn_idx
    return None


def _entity_type(entity) -> int | None:  # noqa: ANN001
    # oneof `kind` inside Entity — map to cambc.EntityType enum number (matches
    # blueprint.Entity values: CONVEYOR=4, SPLITTER=5, ... — see blueprint/__init__.py).
    kind = entity.WhichOneof("kind")
    mapping = {
        "conveyor": 4,
        "splitter": 5,
        "armoured_conveyor": 6,
        "bridge": 7,
        "harvester": 8,
        "foundry": 9,
        "gunner": 10,
        "sentinel": 11,
        "launcher": 12,
        "breach": 13,
        "barrier": 14,
        "road": 15,
    }
    return mapping.get(kind)


def run_trial(
    map_name: str,
    seed: int,
    our_bot: str,
    opp_bot: str,
    expected: set[tuple[int, int, int]],
    trial_dir: Path,
) -> tuple[int, int | None]:
    replay = trial_dir / f"{seed}.replay26"
    env = os.environ.copy()
    env["SOLVER_SEED"] = str(seed)
    # Shorter max turns? cambc may not expose that. Let it run, parse, kill early is harder.
    subprocess.run(
        [
            "cambc",
            "run",
            our_bot,
            opp_bot,
            f"maps/{map_name}.map26",
            "--replay",
            str(replay),
        ],
        env=env,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if not replay.exists():
        return seed, None
    turn = earliest_complete_turn(replay, expected)
    return seed, turn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("map", help="map stem (e.g. coffee)")
    ap.add_argument("-n", type=int, default=32, help="trials")
    ap.add_argument("-j", type=int, default=8, help="parallel workers")
    ap.add_argument("--our-bot", default="intgrah/v54.6.0")
    ap.add_argument("--opp-bot", default="nothing/2000")
    ap.add_argument("--keep-replays", action="store_true")
    args = ap.parse_args()

    km = KnownMap(args.map)
    entries = BLUEPRINTS[km]
    expected: set[tuple[int, int, int]] = {
        (e.pos[0], e.pos[1], int(e.kind)) for e in entries
    }
    print(
        f"map={args.map} entries={len(entries)} trials={args.n} workers={args.j}",
        file=sys.stderr,
    )

    trial_dir = ROOT / "tmp" / "solve" / args.map
    trial_dir.mkdir(parents=True, exist_ok=True)

    best: tuple[int, int] | None = None  # (turn, seed)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.j) as pool:
        futures = [
            pool.submit(
                run_trial,
                args.map,
                seed,
                args.our_bot,
                args.opp_bot,
                expected,
                trial_dir,
            )
            for seed in range(1, args.n + 1)
        ]
        done = 0
        for f in as_completed(futures):
            seed, turn = f.result()
            done += 1
            if turn is None:
                print(f"  seed={seed}: incomplete", file=sys.stderr)
            else:
                print(f"  seed={seed}: done at turn {turn}", file=sys.stderr)
                if best is None or turn < best[0]:
                    best = (turn, seed)
                    print(f"  *** best: seed={seed} turn={turn}", file=sys.stderr)

    elapsed = time.time() - t0
    print(f"elapsed: {elapsed:.1f}s", file=sys.stderr)
    if best is None:
        print("no trial completed the blueprint", file=sys.stderr)
        sys.exit(1)

    turn, seed = best
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    out = BOOKS_DIR / f"{args.map}.seed"
    out.write_text(f"{seed}\n# turn {turn}\n")
    print(f"wrote {out.relative_to(ROOT)}: seed={seed} turn={turn}")


if __name__ == "__main__":
    main()
