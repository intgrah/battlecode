import sys

from scripts.replay import load_replay


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    team = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    r = load_replay(path)

    entity_team: dict[int, int] = {}
    times: list[int] = []
    for turn in r.turns:
        for u in turn.updates:
            for fd, val in u.ListFields():
                if fd.name == "place_entity":
                    entity_team[val.entity.id] = val.entity.team
            if u.HasField("bot_output"):
                bo = u.bot_output
                if entity_team.get(bo.id) == team:
                    times.append(bo.exec_time_us)

    if not times:
        print(f"No bot outputs found for team {team}")
        return

    times.sort()
    n = len(times)
    print(f"n={n}")
    print(f"p50={times[n // 2]}us")
    print(f"p90={times[int(n * 0.9)]}us")
    print(f"p99={times[int(n * 0.99)]}us")
    print(f"p100={times[-1]}us")


if __name__ == "__main__":
    main()
