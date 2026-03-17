import sys
from pathlib import Path

from .bots import analyze_bots
from .defense import defense_analysis
from .network import analyze_network
from .snapshot import parse, replay_snapshots, full_replay, GameState, CONVEYOR_KINDS
from .spatial import analyze_spatial


TEAM = {0: "A", 1: "B"}


def sample_turns(total: int) -> list[int]:
    key = [0, 50, 100, 200, 300, 500, 750, 1000, 1250, 1500, 1750, total - 1]
    return sorted(set(t for t in key if 0 <= t < total))


def print_header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_section(title: str):
    print(f"\n--- {title} ---")


def fmt_pct(v: float) -> str:
    return f"{v:.1f}%"


def fmt_pos(p: tuple[int, int]) -> str:
    return f"({p[0]},{p[1]})"


def print_network_report(states: list[GameState], team: int, label: str):
    print_section(f"Network: Team {label}")

    for state in states:
        n = analyze_network(state, team)
        t = state.turn
        if n["total_conveyors"] == 0 and n["harvesters_connected"] == 0:
            continue

        print(f"\n  Turn {t}:")
        print(f"    Harvesters: {n['harvesters_connected']} connected, {n['harvesters_disconnected']} disconnected")
        if n["disconnected_positions"]:
            print(f"      disconnected at: {', '.join(fmt_pos(p) for p in n['disconnected_positions'])}")

        print(f"    Conveyors: {n['total_conveyors']} total, {n['dead_conveyors']} dead (unused)")
        if n["dead_positions"]:
            print(f"      dead at: {', '.join(fmt_pos(p) for p in n['dead_positions'][:5])}")

        print(f"    Max flow: {n['max_flow']:.2f} stacks/turn (theoretical {n['theoretical_max_flow']:.2f}, utilization {fmt_pct(n['flow_utilization'] * 100)})")

        if n["steiner_approx"] is not None:
            print(f"    Steiner tree: {n['steiner_approx']} edges optimal vs {n['steiner_actual']} actual (waste ratio {n['steiner_waste_ratio']:.1f}x)")

        if n["diameter"] is not None:
            print(f"    Network diameter: {n['diameter']}")

        if n["betweenness_top5"]:
            print(f"    Betweenness centrality (top bottlenecks):")
            for pos, bc in n["betweenness_top5"]:
                print(f"      {fmt_pos(pos)}: {bc:.3f}")

        if n["single_points_of_failure"]:
            print(f"    Single points of failure:")
            for pos, impact in n["single_points_of_failure"]:
                print(f"      {fmt_pos(pos)}: cuts {impact} harvester(s)")

        if n["path_lengths"]:
            lengths = [v for v in n["path_lengths"].values() if v is not None]
            if lengths:
                print(f"    Path lengths: min={min(lengths)} avg={sum(lengths)/len(lengths):.1f} max={max(lengths)}")


def print_spatial_report(states: list[GameState], team: int, label: str):
    print_section(f"Spatial: Team {label}")
    result = analyze_spatial(states, team)

    print(f"\n  Vision coverage over time:")
    for v in result["vision_timeline"]:
        print(f"    t{v['turn']:>5d}: current {fmt_pct(v['current_coverage_pct']):>6s}  cumulative {fmt_pct(v['cumulative_coverage_pct']):>6s} ({v['cumulative_tiles']} tiles)")

    print(f"\n  Ore discovery:")
    for o in result["ore_timeline"]:
        print(f"    t{o['turn']:>5d}: {o['discovered']}/{o['total_ore']} discovered ({fmt_pct(o['discovery_pct'])}), {o['harvested']} harvested ({fmt_pct(o['harvest_pct'])}), {o['undiscovered']} unseen")

    final_ore = result["ore_timeline"][-1] if result["ore_timeline"] else None
    if final_ore and final_ore["undiscovered_positions"]:
        print(f"    undiscovered ore at: {', '.join(fmt_pos(p) for p in final_ore['undiscovered_positions'][:10])}")

    ctrl = result["map_control"]
    if ctrl:
        print(f"\n  Map control (final):")
        print(f"    Team A exclusive: {ctrl['team_a_exclusive']} tiles")
        print(f"    Team B exclusive: {ctrl['team_b_exclusive']} tiles")
        print(f"    Contested: {ctrl['contested']} tiles")
        print(f"    Dark (unseen): {ctrl['dark']} tiles")


def print_defense_report(state: GameState, team: int, label: str):
    print_section(f"Defense: Team {label}")
    d = defense_analysis(state, team)

    if d["turret_count"] == 0 and d["harvesters_total"] == 0:
        print("  (no infrastructure)")
        return

    print(f"  Turrets: {d['turret_count']} ({', '.join(f'{v} {k}' for k, v in d['turret_types'].items())})")
    print(f"  Core defended: {'yes' if d['core_defended'] else 'NO'}")
    print(f"  Harvesters defended: {d['harvesters_defended']}/{d['harvesters_total']} ({fmt_pct(d['harvester_defense_pct'])})")
    print(f"  Conveyors defended: {d['conveyors_defended']}/{d['conveyors_total']} ({fmt_pct(d['conveyor_defense_pct'])})")
    if d["undefended_harvesters"]:
        print(f"    undefended at: {', '.join(fmt_pos(p) for p in d['undefended_harvesters'])}")
    print(f"  Exposed to enemy turrets: {d['harvesters_exposed_to_enemy']} harv, {d['conveyors_exposed_to_enemy']} conv")


def print_bot_report(states: list[GameState], team: int, label: str):
    print_section(f"Bots: Team {label}")
    result = analyze_bots(states, team)

    print(f"\n  Clustering over time:")
    for c in result["clustering_timeline"]:
        if c["bot_count"] == 0:
            continue
        print(f"    t{c['turn']:>5d}: {c['bot_count']} bots  sep={c['avg_separation']:.1f} (min={c['min_separation']:.1f} max={c['max_separation']:.1f})  core_dist={c['avg_core_dist']:.1f} (max={c['max_core_dist']:.1f})")

    p = result["patrol"]
    print(f"\n  Patrol analysis ({p['total_bots_tracked']} bots tracked):")
    print(f"    Patrolling (5+ unique tiles): {p['patrol_bots']}")
    print(f"    Stuck (<=2 tiles, 10+ samples): {p['stuck_bots']}")
    print(f"    Avg unique tiles per bot: {p['avg_unique_tiles']:.1f}")


def report(path: str, team: int | None = None):
    replay = parse(path)
    total = len(replay.turns)
    w, h = replay.map.width, replay.map.height

    winner = TEAM.get(replay.winner, "?") if replay.HasField("winner") else "draw"
    print_header(f"Game Analysis: {Path(path).name}")
    print(f"  Map: {w}x{h}  Turns: {total}  Winner: Team {winner}")

    turns = sample_turns(total)
    states = replay_snapshots(replay, turns)

    teams = [team] if team is not None else [0, 1]

    for t in teams:
        label = TEAM[t]
        print_network_report(states, t, label)
        print_spatial_report(states, t, label)
        print_defense_report(states[-1], t, label)
        print_bot_report(states, t, label)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deep game analysis with real graph algorithms")
    parser.add_argument("replay", nargs="?", default="replay.replay26")
    parser.add_argument("-t", "--team", type=int, choices=[0, 1], default=None, help="Analyze only one team (0=A, 1=B)")
    args = parser.parse_args()
    report(args.replay, args.team)


if __name__ == "__main__":
    main()
