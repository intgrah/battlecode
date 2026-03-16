import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay_parse import TEAM, collect, parse


def print_economy(s: dict) -> None:
    w, h = s["map_size"]
    print(f"Economy Report  |  {s['total_turns']} turns  |  {w}x{h}")
    print()

    for t in (0, 1):
        label = TEAM[t]
        rh = s["resource_history"][t]
        if not rh:
            print(f"--- Team {label}: no data ---\n")
            continue

        final_ti_col = rh[-1][3]
        final_ax_col = rh[-1][4]

        print(f"--- Team {label} ---")

        frt = s["first_resource_turn"][t]
        print(f"  First income: {'turn ' + str(frt) if frt else 'never'}")

        h_conn = s["harvesters_connected"][t]
        h_total = s["harvester_count"][t]
        pct = 100 * h_conn // max(h_total, 1)
        print(f"  Harvesters: {h_total} built, {h_conn} connected ({pct}%)")

        ir = s["income_rate"][t]
        if ir:
            peak_rate = max(r for _, r in ir)
            final_rate = ir[-1][1]
            print(f"  Income rate: peak={peak_rate:.1f}/t  final={final_rate:.1f}/t")

            if len(ir) >= 4:
                quartiles = [ir[len(ir) * i // 4] for i in range(1, 4)]
                print("  Income @25/50/75%: " + "  ".join(f"t{t_}:{r:.1f}" for t_, r in quartiles))

        total_spent = final_ti_col + final_ax_col - rh[-1][1] - rh[-1][2] + 1000
        print(f"  Collected: Ti={final_ti_col} Ax={final_ax_col}  Spent: ~{total_spent}")

        conveyors = s["placed"][t].get("conveyor", 0)
        roads = s["placed"][t].get("road", 0)
        print(f"  Infrastructure: {conveyors} conveyors, {roads} roads")

        if rh and len(rh) >= 5:
            step = max(1, len(rh) // 6)
            samples = [rh[i] for i in range(0, len(rh), step)]
            if rh[-1] not in samples:
                samples.append(rh[-1])
            print("  Ti curve: " + " -> ".join(f"t{r[0]}:{r[1]}" for r in samples))

        print()

    total_conv = sum(s["conveyor_moves_per_turn"])
    n = s["total_turns"]
    avg_conv = total_conv / n if n else 0
    peak_conv = max(s["conveyor_moves_per_turn"]) if s["conveyor_moves_per_turn"] else 0
    print(f"Conveyor flow (global): {total_conv} total  avg={avg_conv:.1f}/t  peak={peak_conv}/t")
    if s["top_flow_tiles"]:
        print(f"Hottest tiles: {', '.join(f'({x},{y}):{c}' for (x,y),c in s['top_flow_tiles'])}")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    print_economy(collect(parse(path)))


if __name__ == "__main__":
    main()
