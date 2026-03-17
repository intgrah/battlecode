from __future__ import annotations

import argparse
import sys

from .parse import extract_map_meta, parse
from .scan import scan_replay
from .sections import SECTIONS
from .snapshot import replay_snapshots, sample_turns
from .types import Context


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay analysis")
    parser.add_argument("replay", nargs="?", default="replay.replay26")
    parser.add_argument(
        "-s",
        "--section",
        default=None,
        help="Comma-separated sections (default: all)",
    )
    parser.add_argument(
        "-t",
        "--team",
        type=int,
        choices=[0, 1],
        default=None,
        help="Analyze one team (0=A, 1=B)",
    )
    args = parser.parse_args()

    if args.section:
        section_names = [s.strip() for s in args.section.split(",")]
        for name in section_names:
            if name not in SECTIONS:
                print(f"Unknown section: {name}", file=sys.stderr)
                print(f"Available: {', '.join(sorted(SECTIONS))}", file=sys.stderr)
                sys.exit(1)
    else:
        section_names = list(SECTIONS)

    teams = [args.team] if args.team is not None else [0, 1]

    replay = parse(args.replay)
    meta = extract_map_meta(replay)
    ctx = Context(map_meta=meta, replay_path=args.replay)

    deps: set[str] = set()
    for name in section_names:
        deps |= SECTIONS[name].deps

    if "snapshots" in deps:
        total = len(replay.turns)  # type: ignore[attr-defined]
        ctx.snapshots = replay_snapshots(replay, sample_turns(total))

    if "scan" in deps:
        ctx.scan = scan_replay(replay, meta)

    for name in section_names:
        section = SECTIONS[name]
        print(f"=== {name.upper()} ===")
        result = section.analyze(ctx, teams)
        print(section.render(result, teams))
        print()


if __name__ == "__main__":
    main()
