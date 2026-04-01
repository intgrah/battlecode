from __future__ import annotations

import argparse
import json

from replay_common import pos_text, trace_entity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Trace one entity through a .replay26 file."
    )
    parser.add_argument("replay", help="Path to a .replay26 file")
    parser.add_argument(
        "--entity",
        "--bot",
        type=int,
        required=True,
        dest="entity_id",
        help="Entity id to trace",
    )
    parser.add_argument(
        "--turn-from", type=int, default=1, help="First turn to include (1-based)"
    )
    parser.add_argument(
        "--turn-to", type=int, help="Last turn to include (default: end of replay)"
    )
    parser.add_argument(
        "--only-events",
        action="store_true",
        help="Show only turns with events for this entity",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    trace = trace_entity(
        args.replay,
        args.entity_id,
        turn_from=args.turn_from,
        turn_to=args.turn_to,
        only_events=args.only_events,
    )
    if args.json:
        print(json.dumps(trace, indent=2, sort_keys=True))
        return 0

    print(f"Replay: {trace['path']}")
    print(f"Entity: {trace['entity_id']}")
    print(f"Window: {trace['turn_from']}..{trace['turn_to']}")
    for record in trace["records"]:
        flags: list[str] = []
        if record["spawned"]:
            flags.append("spawn")
        if record["moved"]:
            flags.append(f"move->{pos_text(record['pos_after'])}")
        if record["hp_delta"]:
            flags.append(f"hp_delta={record['hp_delta']}")
        if record["tled"]:
            flags.append("TLE")
        if record["builder_attack"]:
            flags.append("builder_attack")
        if record["indicator_lines"]:
            flags.append(f"lines={record['indicator_lines']}")
        if record["indicator_dots"]:
            flags.append(f"dots={record['indicator_dots']}")
        if record["removed"]:
            flags.append("removed")
        if record["stdout"]:
            flags.append(f"stdout={len(record['stdout'])}")
        extra = ", ".join(flags) if flags else "idle"
        print(
            f"turn={record['turn']} present={record['present']} kind={record['kind']} "
            f"pos={pos_text(record['pos_after'])} hp={record['hp_after']} "
            f"acd={record['action_cooldown']} mcd={record['move_cooldown']} "
            f"exec_us={record['exec_time_us']} {extra}"
        )
        for line in record["stdout"]:
            print(f"  stdout: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
