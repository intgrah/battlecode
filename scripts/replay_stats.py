import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay_parse import TEAM, collect, parse


def print_stats(s: dict) -> None:
    w, h = s["map_size"]
    print(f"Winner: Team {s['winner']}  |  Turns: {s['total_turns']}  |  Map: {w}x{h}")
    print()

    for t in (0, 1):
        label = TEAM[t]
        rh = s["resource_history"][t]
        final_ti = rh[-1][1] if rh else 0
        final_ax = rh[-1][2] if rh else 0
        final_ti_col = rh[-1][3] if rh else 0
        final_ax_col = rh[-1][4] if rh else 0

        print(f"--- Team {label} ---")
        print(
            f"  Ti={final_ti} Ax={final_ax}  collected Ti={final_ti_col} Ax={final_ax_col}",
        )
        frt = s["first_resource_turn"][t]
        h_conn = s["harvesters_connected"][t]
        h_total = s["harvester_count"][t]
        print(
            f"  Harvesters: {h_total} built, {h_conn} connected  |  First income: {'t' + str(frt) if frt else 'never'}",
        )

        ir = s["income_rate"][t]
        if ir:
            peak_rate = max(r for _, r in ir)
            final_rate = ir[-1][1] if ir else 0
            print(f"  Income: peak={peak_rate:.1f}/t  final={final_rate:.1f}/t")

        print(
            f"  Damage: {s['total_damage'][t]}  Kills: {s['kills'][t]}  Self-destructs: {s['self_destructs'][t]}",
        )
        print(f"  Built: {dict(s['placed'][t])}")
        print(f"  Lost:  {dict(s['removed'][t])}")

        milestones = [
            f"{k}@{s['first_built'][t][k]}"
            for k in [
                "harvester",
                "conveyor",
                "foundry",
                "gunner",
                "sentinel",
                "breach",
                "launcher",
            ]
            if k in s["first_built"][t]
        ]
        if milestones:
            print(f"  Firsts: {', '.join(milestones)}")
        print()

    total_conv = sum(s["conveyor_moves_per_turn"])
    n = s["total_turns"]
    avg_conv = total_conv / n if n else 0
    peak_conv = max(s["conveyor_moves_per_turn"]) if s["conveyor_moves_per_turn"] else 0
    print(f"Conveyor: {total_conv} total  avg={avg_conv:.1f}/t  peak={peak_conv}/t")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    print_stats(collect(parse(path)))


if __name__ == "__main__":
    main()
