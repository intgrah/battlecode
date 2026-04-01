from __future__ import annotations

import argparse
import json

from replay_common import summarize_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize a .replay26 file using the repo-local proto schema.")
    parser.add_argument("replay", help="Path to a .replay26 file")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary = summarize_replay(args.replay)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    print(f"Replay: {summary['path']}")
    print(f"Map: {summary['map']['width']}x{summary['map']['height']}")
    print(f"Turns: {summary['turns']}")
    print(f"Winner: {summary['winner'] or 'UNKNOWN'}")
    print("Cores:")
    for core in summary["map"]["cores"]:
        print(f"  {core['team']}: id={core['id']} pos={tuple(core['pos'])}")

    print("Final Resources:")
    players = summary["players"] or {}
    for team in ("TEAM_A", "TEAM_B"):
        player = players.get(team)
        if player is None:
            print(f"  {team}: unavailable")
            continue
        print(
            f"  {team}: titanium={player['titanium']} axionite={player['axionite']} "
            f"ti_collected={player['titanium_collected']} ax_collected={player['axionite_collected']}"
        )

    print("Final Living Entities:")
    for team in ("TEAM_A", "TEAM_B"):
        counts = summary["final_entities"].get(team, {})
        parts = [f"{kind}={count}" for kind, count in counts.items()]
        print(f"  {team}: {' '.join(parts) if parts else 'none'}")

    bot_outputs = summary["bot_outputs"]
    print("Execution:")
    print(
        f"  bot_output_events={bot_outputs['events']} stdout_events={bot_outputs['stdout_events']} "
        f"tles_total={bot_outputs['tles_total']} first_tle_turn={bot_outputs['first_tle_turn']}"
    )
    if bot_outputs["tles_by_team"]:
        teams = " ".join(f"{team}={count}" for team, count in bot_outputs["tles_by_team"].items())
        print(f"  TLE by team: {teams}")
    print("  Worst entities:")
    for stat in bot_outputs["top_exec_entities"]:
        print(
            f"    id={stat['id']} team={stat['team']} kind={stat['kind']} "
            f"tles={stat['tle_count']} max_exec_us={stat['max_exec_us']} avg_exec_us={stat['avg_exec_us']}"
        )

    indicators = summary["indicators"]
    print(f"Indicators: lines={indicators['lines']} dots={indicators['dots']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
