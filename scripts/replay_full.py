"""Run all analysis sections on a replay."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analysis.parse import extract_map_meta, parse
from analysis.scan import scan_replay
from analysis.sections import SECTIONS
from analysis.snapshot import replay_snapshots, sample_turns
from analysis.types import Context


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: replay_full.py <replay_path>")
        sys.exit(1)

    replay_path = sys.argv[1]
    replay = parse(replay_path)
    meta = extract_map_meta(replay)

    total = len(replay.turns)
    ctx = Context(
        map_meta=meta,
        replay_path=replay_path,
        snapshots=replay_snapshots(replay, sample_turns(total)),
        scan=scan_replay(replay, meta),
    )

    teams = [0, 1]
    for name in SECTIONS:
        section = SECTIONS[name]
        print(f"=== {name.upper()} ===")
        result = section.analyze(ctx, teams)
        print(section.render(result, teams))
        print()


if __name__ == "__main__":
    main()
