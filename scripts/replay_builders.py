import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proto.cambc_pb2 import Entity, Replay

TEAM = {0: "A", 1: "B"}
TRANSPORT_KINDS = {"conveyor", "armoured_conveyor", "splitter", "bridge"}


def entity_kind(e: Entity) -> str:
    return e.WhichOneof("kind") or "unknown"


def parse(path: str) -> Replay:
    with Path(path).open("rb") as f:
        r = Replay()
        r.ParseFromString(f.read())
        return r


def analyze_builders(r: Replay) -> None:
    total_turns = len(r.turns)
    w, h = r.map.width, r.map.height

    entities = {}
    entity_pos = {}
    entity_team = {}

    core_pos = {0: None, 1: None}
    for c in r.map.cores:
        core_pos[c.team] = (c.position.x, c.position.y)

    builder_born = {}
    builder_death = {}
    builder_pos_history = defaultdict(list)
    builder_actions = defaultdict(list)

    for turn_idx, turn in enumerate(r.turns):
        acted_this_turn = set()

        for u in turn.updates:
            k = u.WhichOneof("kind")
            if k == "place_entity":
                e = u.place_entity.entity
                ek = entity_kind(e)
                pos = (e.position.x, e.position.y)
                entities[e.id] = (e.team, ek)
                entity_pos[e.id] = pos
                entity_team[e.id] = e.team

                if ek == "builder_bot":
                    builder_born[e.id] = turn_idx
                    builder_pos_history[e.id].append((turn_idx, pos))
                    builder_actions[e.id].append((turn_idx, "spawn"))
                    acted_this_turn.add(e.id)
                elif ek in TRANSPORT_KINDS:
                    for bid in builder_born:
                        if bid not in builder_death and entity_pos.get(bid) is not None:
                            bp = entity_pos[bid]
                            dx = abs(bp[0] - pos[0])
                            dy = abs(bp[1] - pos[1])
                            if dx <= 1 and dy <= 1 and dx + dy <= 2:
                                builder_actions[bid].append((turn_idx, f"build_{ek}"))
                                acted_this_turn.add(bid)
                                break
                elif ek == "harvester":
                    for bid in builder_born:
                        if bid not in builder_death and entity_pos.get(bid) is not None:
                            bp = entity_pos[bid]
                            dx = abs(bp[0] - pos[0])
                            dy = abs(bp[1] - pos[1])
                            if dx <= 1 and dy <= 1 and dx + dy <= 2:
                                builder_actions[bid].append(
                                    (turn_idx, "build_harvester"),
                                )
                                acted_this_turn.add(bid)
                                break
                elif ek == "road":
                    for bid in builder_born:
                        if bid not in builder_death and entity_pos.get(bid) is not None:
                            bp = entity_pos[bid]
                            dx = abs(bp[0] - pos[0])
                            dy = abs(bp[1] - pos[1])
                            if dx <= 1 and dy <= 1 and dx + dy <= 2:
                                builder_actions[bid].append((turn_idx, "build_road"))
                                acted_this_turn.add(bid)
                                break
            elif k == "move_builder_bot":
                mb = u.move_builder_bot
                new = (mb.to.x, mb.to.y)
                entity_pos[mb.id] = new
                builder_pos_history[mb.id].append((turn_idx, new))
                builder_actions[mb.id].append((turn_idx, "move"))
                acted_this_turn.add(mb.id)
            elif k == "remove_entity":
                eid = u.remove_entity.id
                if eid in builder_born and eid not in builder_death:
                    builder_death[eid] = turn_idx
                    builder_actions[eid].append((turn_idx, "die"))
                    acted_this_turn.add(eid)

        for bid in builder_born:
            if bid not in builder_death and bid not in acted_this_turn:
                builder_actions[bid].append((turn_idx, "idle"))

    print(f"Builder Analysis  |  {total_turns} turns  |  {w}x{h}")
    print()

    for t in (0, 1):
        label = TEAM[t]
        team_builders = [bid for bid in builder_born if entity_team.get(bid) == t]

        print(f"--- Team {label} ({len(team_builders)} builders) ---")

        action_counts = defaultdict(int)
        total_actions = 0
        for bid in team_builders:
            for _, act in builder_actions[bid]:
                action_counts[act] += 1
                total_actions += 1

        if total_actions > 0:
            print("  Action breakdown:")
            for act in sorted(action_counts, key=lambda a: -action_counts[a]):
                pct = 100 * action_counts[act] / total_actions
                print(f"    {act}: {action_counts[act]} ({pct:.1f}%)")

        stuck_events = 0
        stuck_builders = 0
        max_idle_streaks = []
        for bid in team_builders:
            actions = builder_actions[bid]
            consecutive_idle = 0
            max_idle = 0
            was_stuck = False
            for _, act in actions:
                if act == "idle":
                    consecutive_idle += 1
                    if consecutive_idle >= 10:
                        if not was_stuck:
                            stuck_builders += 1
                            was_stuck = True
                        if consecutive_idle == 10:
                            stuck_events += 1
                else:
                    max_idle = max(max_idle, consecutive_idle)
                    consecutive_idle = 0
            max_idle = max(max_idle, consecutive_idle)
            max_idle_streaks.append(max_idle)

        avg_max_idle = sum(max_idle_streaks) / max(len(max_idle_streaks), 1)
        print(
            f"  Stuck: {stuck_builders}/{len(team_builders)} builders stuck (10+ consecutive idle turns)",
        )
        print(f"  Stuck events: {stuck_events}")
        print(f"  Avg longest idle streak: {avg_max_idle:.0f} turns")

        lifetimes = []
        builds_per_life = []
        for bid in team_builders:
            born = builder_born[bid]
            death = builder_death.get(bid, total_turns)
            lifetime = death - born
            lifetimes.append(lifetime)
            build_count = sum(
                1 for _, act in builder_actions[bid] if act.startswith("build_")
            )
            builds_per_life.append(build_count)

        if lifetimes:
            avg_life = sum(lifetimes) / len(lifetimes)
            avg_builds = sum(builds_per_life) / len(builds_per_life)
            print(f"  Avg lifetime: {avg_life:.0f} turns")
            print(f"  Avg builds per builder: {avg_builds:.1f}")

        if core_pos[t]:
            cp = core_pos[t]
            max_dists = []
            for bid in team_builders:
                positions = builder_pos_history[bid]
                if positions:
                    max_d = max(
                        ((p[0] - cp[0]) ** 2 + (p[1] - cp[1]) ** 2) ** 0.5
                        for _, p in positions
                    )
                    max_dists.append(max_d)
            if max_dists:
                avg_max = sum(max_dists) / len(max_dists)
                overall_max = max(max_dists)
                print(f"  Avg max distance from core: {avg_max:.1f}")
                print(f"  Furthest builder from core: {overall_max:.1f}")

        round_trips = 0
        for bid in team_builders:
            if not core_pos[t]:
                break
            cp = core_pos[t]
            positions = builder_pos_history[bid]
            left_core = False
            for _, pos in positions:
                d = abs(pos[0] - cp[0]) + abs(pos[1] - cp[1])
                if d > 3:
                    left_core = True
                elif left_core and d <= 3:
                    round_trips += 1
                    left_core = False

        print(f"  Round trips to core: {round_trips}")
        print()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    analyze_builders(parse(path))


if __name__ == "__main__":
    main()
