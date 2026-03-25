import itertools
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from proto.cambc_pb2 import Replay

ROOT = Path(__file__).resolve().parent.parent
BOTS_DIR = ROOT / "bots"
MAPS_DIR = ROOT / "maps"
RESULTS_DIR = ROOT / "results"


def versioned_bots() -> list[tuple[int, Path]]:
    results = []
    for d in BOTS_DIR.iterdir():
        m = re.fullmatch(r"v(\d+)", d.name)
        if m and d.is_dir() and (d / "main.py").exists():
            results.append((int(m.group(1)), d))
    return sorted(results)


def latest_version() -> tuple[int, Path] | None:
    bots = versioned_bots()
    return bots[-1] if bots else None


def list_bots() -> list[str]:
    return sorted(
        d.name for d in BOTS_DIR.iterdir() if d.is_dir() and (d / "main.py").exists()
    )


def list_maps() -> list[str]:
    return sorted(str(m) for m in MAPS_DIR.glob("*.map26"))


def run_match(bot_a: str, bot_b: str, map_path: str, replay_path: str) -> str | None:
    subprocess.run(
        [
            str(ROOT / ".venv/bin/cambc"),
            "run",
            bot_a,
            bot_b,
            map_path,
            "--replay",
            replay_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
        check=False,
    )
    replay = Path(replay_path)
    if not replay.exists():
        return None
    r = Replay()
    r.ParseFromString(replay.read_bytes())
    if r.HasField("winner"):
        return "A" if r.winner == 0 else "B"
    return "draw"


def round_robin(bots: list[str], maps: list[str]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / timestamp
    run_dir.mkdir()

    wins = defaultdict(int)
    losses = defaultdict(int)
    draws = defaultdict(int)
    results = []

    pairs = list(itertools.combinations(bots, 2))
    total = len(pairs) * len(maps)
    i = 0

    for bot_a, bot_b in pairs:
        for map_path in maps:
            i += 1
            map_name = Path(map_path).stem
            replay_path = str(run_dir / f"{bot_a}_vs_{bot_b}_{map_name}.replay26")
            print(
                f"[{i}/{total}] {bot_a} vs {bot_b} on {map_name}...",
                end=" ",
                flush=True,
            )

            winner = run_match(bot_a, bot_b, map_path, replay_path)

            if winner == "A":
                wins[bot_a] += 1
                losses[bot_b] += 1
                print(f"{bot_a} wins")
            elif winner == "B":
                wins[bot_b] += 1
                losses[bot_a] += 1
                print(f"{bot_b} wins")
            else:
                draws[bot_a] += 1
                draws[bot_b] += 1
                print("draw")

            results.append(
                {
                    "bot_a": bot_a,
                    "bot_b": bot_b,
                    "map": map_name,
                    "winner": winner,
                    "replay": replay_path,
                },
            )

    print("\n=== Standings ===\n")
    all_bots = sorted(set(wins) | set(losses) | set(draws), key=lambda b: -wins[b])
    print(f"{'Bot':<20} {'W':>4} {'L':>4} {'D':>4} {'Win%':>6}")
    print("-" * 40)
    for b in all_bots:
        total_games = wins[b] + losses[b] + draws[b]
        pct = 100 * wins[b] / total_games if total_games else 0
        print(f"{b:<20} {wins[b]:>4} {losses[b]:>4} {draws[b]:>4} {pct:>5.1f}%")

    summary = {
        "timestamp": timestamp,
        "bots": bots,
        "maps": [Path(m).stem for m in maps],
        "results": results,
        "standings": {
            b: {"wins": wins[b], "losses": losses[b], "draws": draws[b]}
            for b in all_bots
        },
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nResults saved to {run_dir}")


def snapshot() -> None:
    cur = latest_version()
    if cur is None:
        print("No versioned bots found. Creating v1 from bots/basic/")
        src = BOTS_DIR / "basic"
        if not src.exists():
            print("bots/basic/ not found either")
            return
        dest = BOTS_DIR / "v1"
        shutil.copytree(src, dest)
        print("Created bots/v1/")
        return

    num, path = cur
    next_num = num + 1
    dest = BOTS_DIR / f"v{next_num}"
    shutil.copytree(path, dest)
    print(f"v{num} frozen, working copy is now v{next_num}")


def prune(keep: int = 5) -> None:
    bots = versioned_bots()
    if len(bots) <= keep:
        print(f"{len(bots)} versions, nothing to prune (keep={keep})")
        return
    to_remove = bots[:-keep]
    for num, path in to_remove:
        shutil.rmtree(path)
        print(f"Removed v{num}")
    print(f"Kept v{bots[-keep][0]}..v{bots[-1][0]}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print(
            "  tournament.py run [bot1 bot2 ...]   -- round robin (all bots if none specified)",
        )
        print(
            "  tournament.py snapshot              -- freeze latest version, bump to next",
        )
        print("  tournament.py latest                -- print latest version name")
        print("  tournament.py list                  -- list available bots")
        print(
            "  tournament.py prune [keep=5]        -- delete old versions, keep latest N",
        )
        return

    cmd = sys.argv[1]
    if cmd == "run":
        bots = sys.argv[2:] if len(sys.argv) > 2 else list_bots()
        if len(bots) < 2:
            print("Need at least 2 bots")
            return
        maps = list_maps()
        if not maps:
            print("No maps found")
            return
        round_robin(bots, maps)
    elif cmd == "snapshot":
        snapshot()
    elif cmd == "latest":
        cur = latest_version()
        if cur:
            print(cur[1].name)
        else:
            print("No versioned bots")
    elif cmd == "prune":
        keep = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        prune(keep)
    elif cmd == "list":
        for b in list_bots():
            print(f"  {b}")
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
