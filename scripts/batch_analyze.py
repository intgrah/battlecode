import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))

from replay_parse import TEAM, collect, parse


def main() -> None:
    replay_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("replays_v12")
    replays = sorted(replay_dir.glob("*.replay26"))

    if not replays:
        print(f"No replays found in {replay_dir}")
        return

    print(f"Analyzing {len(replays)} replays from {replay_dir}/")
    print()

    wins = 0
    losses = 0
    our_team = 0

    agg = {
        "ti_collected": [],
        "ax_collected": [],
        "harvesters": [],
        "harvesters_connected": [],
        "first_income": [],
        "peak_income": [],
        "final_income": [],
        "self_destructs": [],
        "builder_kills": [],
        "builders_spawned": [],
        "moves": [],
        "idle_pct": [],
        "conveyors": [],
        "roads": [],
        "damage_dealt": [],
        "damage_taken": [],
    }

    opp_agg = {
        "ti_collected": [],
        "harvesters": [],
        "peak_income": [],
    }

    per_opponent = defaultdict(lambda: {"wins": 0, "losses": 0})
    per_map = defaultdict(lambda: {"wins": 0, "losses": 0})

    for rp in replays:
        name = rp.stem
        parts = name.split("_")
        opponent = "_".join(parts[1:-2])
        map_name = parts[-1]

        r = parse(str(rp))
        s = collect(r)

        we_won = s["winner"] == TEAM[our_team]
        if we_won:
            wins += 1
            per_opponent[opponent]["wins"] += 1
            per_map[map_name]["wins"] += 1
        else:
            losses += 1
            per_opponent[opponent]["losses"] += 1
            per_map[map_name]["losses"] += 1

        t = our_team
        e = 1 - t
        rh = s["resource_history"][t]

        if rh:
            agg["ti_collected"].append(rh[-1][3])
            agg["ax_collected"].append(rh[-1][4])

        agg["harvesters"].append(s["harvester_count"][t])
        agg["harvesters_connected"].append(s["harvesters_connected"][t])
        agg["first_income"].append(s["first_resource_turn"][t] or 9999)
        agg["self_destructs"].append(s["self_destructs"][t])
        agg["builder_kills"].append(s["builder_kills"][t])
        agg["builders_spawned"].append(s["placed"][t].get("builder_bot", 0))
        agg["moves"].append(s["moves"][t])
        agg["damage_dealt"].append(s["total_damage"][t])
        agg["damage_taken"].append(s["total_damage"][e])

        conveyors = sum(
            s["placed"][t].get(k, 0)
            for k in ("conveyor", "armoured_conveyor", "splitter", "bridge")
        )
        agg["conveyors"].append(conveyors)
        agg["roads"].append(s["placed"][t].get("road", 0))

        ir = s["income_rate"][t]
        if ir:
            agg["peak_income"].append(max(r for _, r in ir))
            agg["final_income"].append(ir[-1][1])
        else:
            agg["peak_income"].append(0)
            agg["final_income"].append(0)

        active = s["builder_active_turns"][t]
        idle = s["builder_idle_turns"][t]
        agg["idle_pct"].append(100 * idle / max(active, 1))

        rh_e = s["resource_history"][e]
        if rh_e:
            opp_agg["ti_collected"].append(rh_e[-1][3])
        opp_agg["harvesters"].append(s["harvester_count"][e])
        ir_e = s["income_rate"][e]
        if ir_e:
            opp_agg["peak_income"].append(max(r for _, r in ir_e))
        else:
            opp_agg["peak_income"].append(0)

    def avg(lst: list) -> float:
        return sum(lst) / len(lst) if lst else 0

    def med(lst: list) -> float:
        if not lst:
            return 0
        s = sorted(lst)
        n = len(s)
        return s[n // 2]

    total = wins + losses
    print(f"=== Overall: {wins}W-{losses}L ({100 * wins / total:.0f}% win rate) ===")
    print()

    print("Per Opponent:")
    for opp in sorted(
        per_opponent,
        key=lambda o: -(per_opponent[o]["wins"] + per_opponent[o]["losses"]),
    ):
        d = per_opponent[opp]
        print(f"  {opp}: {d['wins']}W-{d['losses']}L")
    print()

    print("Per Map:")
    for m in sorted(per_map):
        d = per_map[m]
        t = d["wins"] + d["losses"]
        print(f"  {m}: {d['wins']}W-{d['losses']}L ({100 * d['wins'] / t:.0f}%)")
    print()

    print("=== Our Stats (avg / median) ===")
    print(
        f"  Ti collected:      {avg(agg['ti_collected']):>8.0f} / {med(agg['ti_collected']):>8.0f}",
    )
    print(
        f"  Ax collected:      {avg(agg['ax_collected']):>8.0f} / {med(agg['ax_collected']):>8.0f}",
    )
    print(
        f"  Harvesters:        {avg(agg['harvesters']):>8.1f} / {med(agg['harvesters']):>8.0f}",
    )
    print(
        f"  Harvs connected:   {avg(agg['harvesters_connected']):>8.1f} / {med(agg['harvesters_connected']):>8.0f}",
    )
    print(
        f"  First income:      t{avg(agg['first_income']):>7.0f} / t{med(agg['first_income']):>7.0f}",
    )
    print(
        f"  Peak income:       {avg(agg['peak_income']):>8.1f} / {med(agg['peak_income']):>8.1f}/t",
    )
    print(
        f"  Final income:      {avg(agg['final_income']):>8.1f} / {med(agg['final_income']):>8.1f}/t",
    )
    print(
        f"  Builders spawned:  {avg(agg['builders_spawned']):>8.1f} / {med(agg['builders_spawned']):>8.0f}",
    )
    print(f"  Builder moves:     {avg(agg['moves']):>8.0f} / {med(agg['moves']):>8.0f}")
    print(f"  Builder idle%:     {avg(agg['idle_pct']):>8.1f}%")
    print(
        f"  Self-destructs:    {avg(agg['self_destructs']):>8.1f} / {med(agg['self_destructs']):>8.0f}",
    )
    print(
        f"  Builder kills:     {avg(agg['builder_kills']):>8.1f} / {med(agg['builder_kills']):>8.0f}",
    )
    print(
        f"  Conveyors placed:  {avg(agg['conveyors']):>8.0f} / {med(agg['conveyors']):>8.0f}",
    )
    print(f"  Roads placed:      {avg(agg['roads']):>8.0f} / {med(agg['roads']):>8.0f}")
    print(
        f"  Damage dealt:      {avg(agg['damage_dealt']):>8.0f} / {med(agg['damage_dealt']):>8.0f}",
    )
    print(
        f"  Damage taken:      {avg(agg['damage_taken']):>8.0f} / {med(agg['damage_taken']):>8.0f}",
    )
    print()

    print("=== Opponent Stats (avg) ===")
    print(f"  Ti collected:      {avg(opp_agg['ti_collected']):>8.0f}")
    print(f"  Harvesters:        {avg(opp_agg['harvesters']):>8.1f}")
    print(f"  Peak income:       {avg(opp_agg['peak_income']):>8.1f}/t")


if __name__ == "__main__":
    main()
