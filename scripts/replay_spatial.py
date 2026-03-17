import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay_parse import TEAM, collect, parse


def print_spatial(s: dict) -> None:
    w, h = s["map_size"]
    print(f"Spatial Report  |  {s['total_turns']} turns  |  {w}x{h}")
    print()

    for t in (0, 1):
        label = TEAM[t]

        print(f"--- Team {label} ---")

        spread = s["avg_builder_spread"][t]
        print(f"  Builder avg spread: {spread:.1f} tiles")

        idle = s["builder_idle_turns"][t]
        active = s["builder_active_turns"][t]
        idle_pct = 100 * idle // max(active, 1)
        print(f"  Builder idle: {idle}/{active} unit-turns ({idle_pct}%)")

        builders = s["placed"][t].get("builder_bot", 0)
        print(f"  Builders spawned: {builders}")

        print(f"  Total builder moves: {s['moves'][t]}")

        conveyors = sum(
            s["placed"][t].get(k, 0)
            for k in ("conveyor", "armoured_conveyor", "splitter", "bridge")
        )
        roads = s["placed"][t].get("road", 0)
        roads_lost = s["removed"][t].get("road", 0)
        print(
            f"  Path tiles: {conveyors} transport + {roads} roads ({roads_lost} roads destroyed)",
        )

        if conveyors + roads > 0:
            conv_pct = 100 * conveyors // (conveyors + roads)
            print(f"  Conveyor ratio: {conv_pct}%")

        h_total = s["harvester_count"][t]
        core = s["core_positions"][t]
        if h_total > 0 and core:
            fb = s["first_built"][t]
            if "harvester" in fb:
                print(f"  First harvester: turn {fb['harvester']}")
            if "conveyor" in fb:
                print(f"  First conveyor: turn {fb['conveyor']}")

        print()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    print_spatial(collect(parse(path)))


if __name__ == "__main__":
    main()
