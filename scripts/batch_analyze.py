import sys
from collections import defaultdict
from pathlib import Path

from scripts.analysis.constants import TEAM_LABEL
from scripts.analysis.parse import extract_map_meta, parse
from scripts.analysis.scan import scan_replay


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

    agg: dict[str, list] = {
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

    opp_agg: dict[str, list] = {
        "ti_collected": [],
        "harvesters": [],
        "peak_income": [],
    }

    per_opponent: dict[str, dict[str, int]] = defaultdict(
        lambda: {"wins": 0, "losses": 0},
    )
    per_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {"wins": 0, "losses": 0},
    )

    for rp in replays:
        name = rp.stem
        parts = name.split("_")
        opponent = "_".join(parts[1:-2])
        map_name = parts[-1]

        r = parse(str(rp))
        meta = extract_map_meta(r)
        s = scan_replay(r, meta)

        we_won = s.winner == TEAM_LABEL[our_team]
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
        rh = s.resource_history.get(t, [])

        if rh:
            agg["ti_collected"].append(rh[-1].titanium_collected)
            agg["ax_collected"].append(rh[-1].axionite_collected)

        agg["harvesters"].append(s.harvester_count.get(t, 0))
        agg["harvesters_connected"].append(s.harvesters_connected.get(t, 0))
        agg["first_income"].append(s.first_resource_turn.get(t) or 9999)
        agg["self_destructs"].append(s.self_destructs.get(t, 0))
        agg["builder_kills"].append(s.builder_kills.get(t, 0))
        agg["builders_spawned"].append(
            s.entities_placed.get(t, {}).get("builder_bot", 0),
        )
        agg["moves"].append(s.total_moves.get(t, 0))
        agg["damage_dealt"].append(s.total_damage.get(t, 0))
        agg["damage_taken"].append(s.total_damage.get(e, 0))

        conveyors = sum(
            s.entities_placed.get(t, {}).get(k, 0)
            for k in ("conveyor", "armoured_conveyor", "splitter", "bridge")
        )
        agg["conveyors"].append(conveyors)
        agg["roads"].append(s.entities_placed.get(t, {}).get("road", 0))

        ir = s.income_rate.get(t, [])
        if ir:
            agg["peak_income"].append(max(r for _, r in ir))
            agg["final_income"].append(ir[-1][1])
        else:
            agg["peak_income"].append(0)
            agg["final_income"].append(0)

        active = s.builder_presence_turns.get(t, 0)
        idle = s.builder_idle_turns.get(t, 0)
        agg["idle_pct"].append(100 * idle / max(active, 1))

        rh_e = s.resource_history.get(e, [])
        if rh_e:
            opp_agg["ti_collected"].append(rh_e[-1].titanium_collected)
        opp_agg["harvesters"].append(s.harvester_count.get(e, 0))
        ir_e = s.income_rate.get(e, [])
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
        if n % 2 == 1:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2

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
    for label, key in [
        ("Ti collected", "ti_collected"),
        ("Ax collected", "ax_collected"),
        ("Harvesters", "harvesters"),
        ("Harvs connected", "harvesters_connected"),
        ("Peak income", "peak_income"),
        ("Final income", "final_income"),
        ("Builders spawned", "builders_spawned"),
        ("Builder moves", "moves"),
        ("Self-destructs", "self_destructs"),
        ("Builder kills", "builder_kills"),
        ("Conveyors placed", "conveyors"),
        ("Roads placed", "roads"),
        ("Damage dealt", "damage_dealt"),
        ("Damage taken", "damage_taken"),
    ]:
        print(f"  {label + ':':20s} {avg(agg[key]):>8.1f} / {med(agg[key]):>8.0f}")
    print(
        f"  {'First income:':20s} t{avg(agg['first_income']):>7.0f} / t{med(agg['first_income']):>7.0f}",
    )
    print(f"  {'Builder idle%:':20s} {avg(agg['idle_pct']):>8.1f}%")
    print()

    print("=== Opponent Stats (avg) ===")
    print(f"  Ti collected:      {avg(opp_agg['ti_collected']):>8.0f}")
    print(f"  Harvesters:        {avg(opp_agg['harvesters']):>8.1f}")
    print(f"  Peak income:       {avg(opp_agg['peak_income']):>8.1f}/t")


if __name__ == "__main__":
    main()
